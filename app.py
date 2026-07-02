from datetime import datetime
import os
import uuid
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import cloudinary
import cloudinary.uploader
from flask import Flask, render_template, request, redirect, url_for, session, has_request_context
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, or_, text
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

def normalize_database_url(raw_url):
    if not raw_url:
        return 'sqlite:///items.db'

    if raw_url.startswith('postgres://'):
        raw_url = raw_url.replace('postgres://', 'postgresql://', 1)

    parsed = urlparse(raw_url)
    if parsed.scheme.startswith('postgresql') and 'sslmode=' not in parsed.query:
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query['sslmode'] = 'require'
        parsed = parsed._replace(query=urlencode(query))
        raw_url = urlunparse(parsed)

    return raw_url

app.config['SQLALCHEMY_DATABASE_URI'] = normalize_database_url(os.getenv('DATABASE_URL', 'sqlite:///items.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv('SECRET_KEY', 'dev-only-secret-change-in-production')
db = SQLAlchemy(app)

# --- CLOUDINARY CONFIGURATION ---
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'al1xal1x')
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_IMAGE_DIMENSION = 1600

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    image_urls = db.Column(db.Text, nullable=True) 
    price = db.Column(db.Float, nullable=False)
    discount_price = db.Column(db.Float, nullable=True) 
    summary = db.Column(db.Text, nullable=False)
    etsy_url = db.Column(db.String(500), nullable=True)
    category = db.Column(db.String(50), nullable=False, default='general')
    popularity_score = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<Item {self.name}>'

class ShopProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_summary = db.Column(db.Text, nullable=False, default='Designs are produced in small batches with close quality checks, clean detailing, and practical durability in mind.')
    contact_email = db.Column(db.String(255), nullable=False, default='mom@example.com')
    location = db.Column(db.String(255), nullable=False, default='Orlando, FL')
    contact_details = db.Column(db.Text, nullable=True, default='')

def parse_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback

def parse_optional_float(value):
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return parse_float(trimmed, None)

def parse_int(value, fallback=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback

def get_shop_profile():
    profile = ShopProfile.query.first()
    if profile:
        return profile

    profile = ShopProfile()
    db.session.add(profile)
    db.session.commit()
    return profile

def allowed_image(filename):
    if not filename or '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

# --- NEW CLOUDINARY UPLOAD LOGIC ---
def save_uploaded_images(file_storage_list):
    saved_urls = []

    for file in file_storage_list:
        filename = getattr(file, 'filename', None)
        if not file or not filename:
            continue
        if not allowed_image(filename):
            continue

        try:
            # Cloudinary automatically handles the file stream
            upload_result = cloudinary.uploader.upload(
                file,
                width=MAX_IMAGE_DIMENSION, 
                height=MAX_IMAGE_DIMENSION, 
                crop="limit" 
            )
            saved_urls.append(upload_result['secure_url'])
        except Exception as e:
            print(f"Cloudinary upload failed: {e}")
            continue

    return saved_urls

def parse_image_url_text(image_url_text):
    if not image_url_text:
        return []
    return [url.strip() for url in image_url_text.split(',') if url.strip()]

def build_image_url_field(image_url_text, uploaded_files, existing_urls=None, fallback=''):
    text_urls = parse_image_url_text(image_url_text)
    uploaded_urls = save_uploaded_images(uploaded_files)
    existing_urls = existing_urls or []
    merged = existing_urls + text_urls + uploaded_urls
    if merged:
        return ', '.join(merged)
    return fallback

# --- NEW CLOUDINARY DELETE LOGIC ---
def delete_local_uploads(urls):
    for url in urls:
        if 'res.cloudinary.com' in url:
            try:
                # Extract the public_id to tell Cloudinary which image to delete
                public_id = url.split('/')[-1].split('.')[0]
                cloudinary.uploader.destroy(public_id)
            except Exception as e:
                print(f"Failed to delete from Cloudinary: {e}")

def ensure_schema():
    db.create_all()
    inspector = inspect(db.engine)
    item_columns = {column['name'] for column in inspector.get_columns('item')}

    if 'category' not in item_columns:
        db.session.execute(text("ALTER TABLE item ADD COLUMN category VARCHAR(50) NOT NULL DEFAULT 'general'"))

    if 'popularity_score' not in item_columns:
        db.session.execute(text('ALTER TABLE item ADD COLUMN popularity_score INTEGER NOT NULL DEFAULT 0'))

    if 'created_at' not in item_columns:
        db.session.execute(text('ALTER TABLE item ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP'))

    db.session.commit()
    get_shop_profile()


@app.before_request
def initialize_once():
    if not getattr(app, '_schema_initialized', False):
        ensure_schema()
        app._schema_initialized = True

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None 
    if request.method == 'POST':
        password = request.form['password']
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect('/admin')
        else:
            error = "Incorrect password. Please try again." 
            
    return render_template('login.html', error=error)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('logged_in'):
        return redirect('/login')

    profile = get_shop_profile()

    if request.method == 'POST':
        form_type = request.form.get('form_type', 'add_item')

        if form_type == 'update_profile':
            profile.shop_summary = request.form.get('shop_summary', '').strip() or profile.shop_summary
            profile.contact_email = request.form.get('contact_email', '').strip() or profile.contact_email
            profile.location = request.form.get('location', '').strip() or profile.location
            profile.contact_details = request.form.get('contact_details', '').strip()
            db.session.commit()
            return redirect(url_for('admin'))

        new_item = Item(
            name=request.form['name'].strip(),
            image_urls=build_image_url_field(
                request.form.get('image_urls', ''),
                request.files.getlist('images'),
                existing_urls=[]
            ),
            price=parse_float(request.form.get('price'), 0.0),
            discount_price=parse_optional_float(request.form.get('discount_price', '')),
            summary=request.form['summary'].strip(),
            etsy_url=request.form.get('etsy_url', '').strip(),
            category=request.form.get('category', 'general').strip().lower() or 'general',
            popularity_score=parse_int(request.form.get('popularity_score'), 0)
        )
        db.session.add(new_item)
        db.session.commit()
        return redirect(url_for('admin'))

    all_items = Item.query.order_by(Item.created_at.desc(), Item.id.desc()).all()
    return render_template('admin.html', profile=profile, items=all_items)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect('/')

@app.route('/')
def index():
    profile = get_shop_profile()
    search_query = request.args.get('q', '').strip()
    sort_by = request.args.get('sort', 'new').strip().lower()
    category = request.args.get('category', 'all').strip().lower()

    item_query = Item.query
    if search_query:
        like_query = f"%{search_query}%"
        item_query = item_query.filter(
            or_(Item.name.ilike(like_query), Item.summary.ilike(like_query))
        )

    if category != 'all':
        item_query = item_query.filter(func.lower(Item.category) == category)

    if sort_by == 'popular':
        item_query = item_query.order_by(Item.popularity_score.desc(), Item.created_at.desc())
    elif sort_by == 'price_low':
        item_query = item_query.order_by(func.coalesce(Item.discount_price, Item.price).asc())
    elif sort_by == 'price_high':
        item_query = item_query.order_by(func.coalesce(Item.discount_price, Item.price).desc())
    else:
        sort_by = 'new'
        item_query = item_query.order_by(Item.created_at.desc(), Item.id.desc())

    all_items = item_query.all()
    categories = [
        result[0] for result in db.session.query(Item.category).distinct().order_by(Item.category.asc()).all()
        if result[0]
    ]

    return render_template(
        'index.html',
        items=all_items,
        profile=profile,
        q=search_query,
        sort=sort_by,
        selected_category=category,
        categories=categories
    )

@app.route('/item/<int:item_id>')
def item_detail(item_id):
    item = Item.query.get_or_404(item_id)
    images = []
    if item.image_urls:
        images = [url.strip() for url in item.image_urls.split(',')]
    return render_template('item.html', item=item, images=images)

@app.route('/admin/edit/<int:item_id>', methods=['GET', 'POST'])
def edit_item(item_id):
    if not session.get('logged_in'):
        return redirect('/login')

    item = Item.query.get_or_404(item_id)
    if request.method == 'POST':
        original_urls = parse_image_url_text(item.image_urls or '')
        kept_existing_urls = [url.strip() for url in request.form.getlist('existing_images') if url.strip()]

        item.name = request.form.get('name', item.name).strip()
        item.image_urls = build_image_url_field(
            request.form.get('image_urls', ''),
            request.files.getlist('images'),
            existing_urls=kept_existing_urls,
            fallback=item.image_urls or ''
        )
        item.price = parse_float(request.form.get('price'), item.price)
        item.discount_price = parse_optional_float(request.form.get('discount_price', ''))
        item.summary = request.form.get('summary', item.summary).strip()
        item.etsy_url = request.form.get('etsy_url', '').strip()
        item.category = request.form.get('category', item.category).strip().lower() or 'general'
        item.popularity_score = parse_int(request.form.get('popularity_score'), item.popularity_score)

        removed_urls = [url for url in original_urls if url not in kept_existing_urls]
        delete_local_uploads(removed_urls) # Now deletes from Cloudinary!

        db.session.commit()
        return redirect(url_for('admin'))

    return render_template('edit_item.html', item=item, existing_images=parse_image_url_text(item.image_urls or ''))

@app.route('/delete/<int:item_id>', methods=['POST'])
def delete_item(item_id):
    if not session.get('logged_in'):
        return redirect('/login')
    
    item = Item.query.get_or_404(item_id)
    
    # Optional: Delete the images from Cloudinary before deleting the item from the DB
    if item.image_urls:
        urls_to_delete = parse_image_url_text(item.image_urls)
        delete_local_uploads(urls_to_delete)
        
    db.session.delete(item)
    db.session.commit()
    
    return redirect('/')

if __name__ == '__main__':
    with app.app_context():
        ensure_schema()
    debug_mode = os.getenv('FLASK_DEBUG', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    app.run(host=host, port=port, debug=debug_mode)
