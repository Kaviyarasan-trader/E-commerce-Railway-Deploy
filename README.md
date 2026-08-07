# Kavi Bazaar

A Django e-commerce store (products, cart, orders, Razorpay payments, Google sign-in, email OTP login, admin dashboard with Jazzmin).

## Tech Stack

- Python 3.12 / Django 6.0
- SQLite (local) / PostgreSQL (Railway via `DATABASE_URL`)
- Gunicorn + WhiteNoise (static)
- Razorpay (payments, with mock fallback)
- Google Sign-In (OAuth 2.0) + Google Maps
- ReportLab (invoice PDFs)

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (PowerShell)
pip install -r requirements.txt

copy .env.example .env            # then fill in values (see "Environment Variables")
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/.

Optional data seeding:

```bash
python manage.py seed_full_catalog
python manage.py fetch_category_images
python manage.py add_product_images
```

## Environment Variables

All configuration is read from the environment or a local `.env` file (see `.env.example` for names and placeholders). Never commit a real `.env`.

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django secret key. **Required when `DJANGO_DEBUG=False`.** |
| `DJANGO_DEBUG` | `True`/`False`. Production security flags (HSTS, SSL redirect, secure cookies) are enabled automatically when `False`. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames. Defaults to `127.0.0.1,localhost`. |
| `RAILWAY_PUBLIC_DOMAIN` | Set automatically by Railway. Appended to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`. |
| `DATABASE_URL` | Database connection. Defaults to local SQLite. Railway's Postgres plugin provides this automatically. |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | Razorpay credentials. Leave unset for demo/mock payment mode. |
| `GOOGLE_MAPS_API_KEY` | Google Maps/Geocoding key (used server-side). |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google OAuth 2.0 web client credentials. |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Gmail SMTP (App Password). If password is empty the console email backend is used. |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated origins. Defaults to `http://127.0.0.1,http://localhost`. |

## Deploying to Railway

1. **Push the repository to GitHub.**

2. **Create a Railway project** and add a service from the GitHub repo.

3. **Add a PostgreSQL database** (Railway > New > Database > PostgreSQL). Railway sets `DATABASE_URL` automatically and the app will run `migrate` at build.

4. **Set environment variables** in the service's Variables tab (at minimum):
   - `DJANGO_SECRET_KEY` — generate a long random value, e.g. `python -c "import secrets; print(secrets.token_urlsafe(64))"`
   - `DJANGO_DEBUG=False`
   - `CSRF_TRUSTED_ORIGINS` (optional — the Railway public domain is appended automatically)
   - Razorpay / Google / Email values as needed (all optional otherwise)

5. **Deploy settings are already in the repo**:
   - `railway.json` — Nixpacks build (`pip install`, `collectstatic`, `migrate`), gunicorn start command, healthcheck on `/`.
   - `Procfile` — `web: gunicorn kavi_bazaar.wsgi --bind 0.0.0.0:$PORT --log-file -`
   - `requirements.txt` — pinned dependencies.

6. **Create the admin user on the deployed app:**
   ```bash
   railway run python manage.py createsuperuser
   ```

### Google OAuth redirect URIs

The OAuth callback URL is built dynamically from the current request, so no code change is needed. In the Google Cloud Console (APIs & Services > Credentials > your Web OAuth client) add the authorized redirect URI for your deployed domain:

```
https://<your-app>.up.railway.app/google-auth/callback
```

Also add the domain to the JavaScript origins if frontend Google Sign-In is used.

## Limitations

- **Uploaded media is ephemeral on Railway.** Product images, profile pictures, and rating images are stored under `media/` on the local filesystem. Railway's filesystem is not persistent across deploys/restarts, so uploaded files may be lost. For production, configure an external storage backend (e.g. AWS S3, Cloudinary, or similar) — none is wired up yet. Products seeded via `seed_full_catalog` reference seeded images in `shop/static/`.
- **Email/SMS/payment credentials** must be supplied via env vars; the app degrades gracefully (console email backend, Razorpay mock mode) when they are absent.
