import io
import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from PIL import Image

import app as app_module


@contextmanager
def isolated_database(app):
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    temp_db.close()
    original_database_uri = app.config['SQLALCHEMY_DATABASE_URI']
    original_testing = app.config.get('TESTING', False)
    original_schema_flag = getattr(app, '_schema_initialized', False)
    original_upload_folder = app.config['UPLOAD_FOLDER']

    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{temp_db.name}'
    app.config['TESTING'] = True
    app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp(prefix='moms_uploads_')
    if hasattr(app, '_schema_initialized'):
        delattr(app, '_schema_initialized')

    try:
        with app.app_context():
            app_module.db.drop_all()
            app_module.db.create_all()
            yield temp_db.name
    finally:
        with app.app_context():
            app_module.db.session.remove()
            app_module.db.drop_all()
        app.config['SQLALCHEMY_DATABASE_URI'] = original_database_uri
        app.config['TESTING'] = original_testing
        app.config['UPLOAD_FOLDER'] = original_upload_folder
        if original_schema_flag:
            app._schema_initialized = True
        elif hasattr(app, '_schema_initialized'):
            delattr(app, '_schema_initialized')
        if os.path.exists(temp_db.name):
            os.unlink(temp_db.name)


class MomsAppTests(unittest.TestCase):
    def setUp(self):
        self.app = app_module.app
        self.client = self.app.test_client()

    def login(self):
        with self.client.session_transaction() as session_data:
            session_data['logged_in'] = True

    def create_test_image(self, color=(200, 0, 0)):
        image = Image.new('RGB', (2000, 1200), color=color)
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG')
        buffer.seek(0)
        return buffer

    def test_normalize_database_url(self):
        self.assertEqual(app_module.normalize_database_url('postgres://user:pass@host/db'), 'postgresql://user:pass@host/db?sslmode=require')
        self.assertEqual(app_module.normalize_database_url('sqlite:///items.db'), 'sqlite:///items.db')

    def test_save_uploaded_images_compresses_and_returns_static_urls(self):
        with isolated_database(self.app):
            upload = self.create_test_image()
            upload.filename = 'sample.jpg'
            saved = app_module.save_uploaded_images([upload])

            self.assertEqual(len(saved), 1)
            self.assertTrue(saved[0].startswith('/static/uploads/'))

            filename = saved[0].split('/static/uploads/', 1)[1]
            local_path = os.path.join(self.app.config['UPLOAD_FOLDER'], filename)
            self.assertTrue(os.path.exists(local_path))
            self.assertLess(os.path.getsize(local_path), 250000)

    def test_build_image_url_field_merges_existing_new_and_uploads(self):
        with isolated_database(self.app):
            upload = self.create_test_image((0, 200, 0))
            upload.filename = 'sample.jpg'
            with patch('app.save_uploaded_images', return_value=['/static/uploads/new.jpg']):
                result = app_module.build_image_url_field('https://example.com/a.jpg, https://example.com/b.jpg', [upload], existing_urls=['/static/uploads/existing.jpg'])
            self.assertEqual(result, '/static/uploads/existing.jpg, https://example.com/a.jpg, https://example.com/b.jpg, /static/uploads/new.jpg')

    def test_admin_profile_update_persists(self):
        with isolated_database(self.app):
            self.login()
            response = self.client.post('/admin', data={
                'form_type': 'update_profile',
                'shop_summary': 'Fresh shop summary',
                'contact_email': 'new@example.com',
                'location': 'Miami, FL',
                'contact_details': 'Instagram @shop',
            }, follow_redirects=False)
            self.assertEqual(response.status_code, 302)

            with self.app.app_context():
                profile = app_module.ShopProfile.query.first()
                self.assertEqual(profile.shop_summary, 'Fresh shop summary')
                self.assertEqual(profile.contact_email, 'new@example.com')
                self.assertEqual(profile.location, 'Miami, FL')
                self.assertEqual(profile.contact_details, 'Instagram @shop')

    def test_add_item_with_uploaded_image(self):
        with isolated_database(self.app):
            self.login()
            upload = self.create_test_image()
            upload.name = 'images'
            upload.seek(0)
            response = self.client.post(
                '/admin',
                data={
                    'form_type': 'add_item',
                    'name': 'Test Print',
                    'image_urls': '',
                    'images': (upload, 'sample.jpg'),
                    'etsy_url': '',
                    'price': '15.25',
                    'discount_price': '',
                    'category': 'decor',
                    'popularity_score': '12',
                    'summary': 'A test item',
                },
                content_type='multipart/form-data',
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)

            with self.app.app_context():
                item = app_module.Item.query.first()
                self.assertIsNotNone(item)
                self.assertEqual(item.name, 'Test Print')
                self.assertEqual(item.category, 'decor')
                self.assertEqual(item.popularity_score, 12)
                self.assertIn('/static/uploads/', item.image_urls)

    def test_edit_item_can_remove_existing_uploaded_image(self):
        with isolated_database(self.app):
            self.login()
            item = app_module.Item(
                name='Edit Me',
                image_urls='/static/uploads/old.jpg, https://example.com/keep.jpg',
                price=10,
                summary='Original',
                category='general',
                popularity_score=1,
            )
            app_module.db.session.add(item)
            app_module.db.session.commit()

            with patch('app.delete_local_uploads') as delete_local_uploads:
                response = self.client.post(
                    f'/admin/edit/{item.id}',
                    data={
                        'name': 'Edit Me',
                        'image_urls': '',
                        'existing_images': 'https://example.com/keep.jpg',
                        'etsy_url': '',
                        'price': '10',
                        'discount_price': '',
                        'category': 'general',
                        'popularity_score': '2',
                        'summary': 'Updated',
                    },
                    follow_redirects=False,
                )
            self.assertEqual(response.status_code, 302)
            delete_local_uploads.assert_called_once_with(['/static/uploads/old.jpg'])

            with self.app.app_context():
                updated = app_module.Item.query.get(item.id)
                self.assertEqual(updated.image_urls, 'https://example.com/keep.jpg')
                self.assertEqual(updated.summary, 'Updated')
                self.assertEqual(updated.popularity_score, 2)

    def test_index_sorting_and_filtering(self):
        with isolated_database(self.app):
            first = app_module.Item(name='Alpha', image_urls='', price=25, summary='Desk item', category='decor', popularity_score=1)
            second = app_module.Item(name='Beta', image_urls='', price=10, summary='Toy item', category='toys', popularity_score=20)
            app_module.db.session.add_all([first, second])
            app_module.db.session.commit()

            response = self.client.get('/?q=toy&category=toys&sort=popular')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Beta', response.data)
            self.assertNotIn(b'Alpha', response.data)

            response = self.client.get('/?sort=price_low')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Beta', response.data)


if __name__ == '__main__':
    unittest.main()
