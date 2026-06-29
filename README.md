# Moms 3D Prints

Deployment notes for hosting on Neon + Render:

## Local development
- Create a virtual environment and install dependencies from `requirements-dev.txt` plus your runtime packages.
- Set `DATABASE_URL` if you want to test against Postgres locally; otherwise the app falls back to SQLite.
- Run the Flask app with `python app.py`.

## Neon database
- Create a Neon project and copy the connection string.
- Set the connection string as `DATABASE_URL` in Render.
- The app normalizes `postgres://` to `postgresql://` and adds `sslmode=require` automatically.

## Render web service
- Create a new Web Service from this repo.
- Use `gunicorn app:app` as the start command.
- Add `DATABASE_URL` to environment variables.
- Add `SECRET_KEY` to environment variables.
- Add `ADMIN_PASSWORD` to environment variables.
- Render sets `PORT` automatically; the app will bind to it.
- If you use file uploads in production, note that Render's filesystem is ephemeral. For permanent hosted uploads, store images in object storage such as S3-compatible storage or move image hosting to a persistent service.

## Testing
- Run `python -m pytest` to execute the tests in `tests/test_app.py`.
