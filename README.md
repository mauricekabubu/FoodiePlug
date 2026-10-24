# FoodiePlug

## Run FoodiePlug with Docker

The Django project is in `foodplanner/` and uses `config.settings`. It uses
SQLite for local development when `DATABASE_URL` is unset and PostgreSQL when
`DATABASE_URL` is configured. Neon supplies a pooled `DATABASE_URL` for web
requests and `DATABASE_URL_UNPOOLED` for migrations. Docker Compose loads
Neon's generated `.env.local` when present. In SQLite mode, the first Compose
run copies the original `foodplanner/db.sqlite3` to a persistent Docker volume
using SQLite's online backup API and copies `foodplanner/media/` to that volume.
In PostgreSQL mode, it does not seed or use the SQLite database.

The application uses psycopg 3 for PostgreSQL. SQLite remains available for
local development; MySQL is not configured.

### Initial setup

Run these commands in PowerShell from the repository root (the directory
containing this README):

```powershell
Copy-Item .env.example .env
notepad .env
```

Set `SECRET_KEY` in `.env` to a unique random value. For example, generate one
with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Copy the output into `.env`. Do not commit `.env`. Configure `ALLOWED_HOSTS`
for the hostnames you will use. The optional inner `foodplanner/.env` is also
loaded for compatibility with the existing local setup; the root `.env` takes
precedence when it sets the same variable. Optional provider variables are
commented out in `.env.example` so existing Gemini, OAuth, and credential
encryption settings in `foodplanner/.env` remain effective.

Back up the source SQLite database before applying any migration. This creates
a consistent backup without changing the source database:

```powershell
python -c "import sqlite3; src=sqlite3.connect('foodplanner/db.sqlite3'); dst=sqlite3.connect('foodplanner/db.sqlite3.backup'); src.backup(dst); dst.close(); src.close()"
```

Build the app image, apply migrations explicitly, collect static assets, and
start the services:

```powershell
docker compose build
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py collectstatic --noinput
docker compose up -d
```

The migration command is explicit: Compose does not run migrations
automatically. The first `run` seeds the Docker volumes before executing the
management command. Open <http://localhost:8080>. Change `PORT` in `.env`
if that port is also in use.

### Common commands

```powershell
# Create an administrator account
docker compose run --rm web python manage.py createsuperuser

# Follow application and proxy logs
docker compose logs -f --tail=100 web nginx

# Open a Django shell
docker compose run --rm web python manage.py shell

# Restart the services
docker compose restart

# Stop the services without deleting persistent data
docker compose down

# Check service health
docker compose ps
```

Use `docker compose up -d --build` after changing application code or the
Dockerfile. Do not use `docker compose down -v` unless you intentionally want
to delete the persistent database, uploaded media, and collected static-file
volumes.

### Configuration

The root `.env.example` lists the supported environment variables. At minimum,
set a strong `SECRET_KEY`, `DEBUG=False`, and an appropriate comma-separated
`ALLOWED_HOSTS`. Neon CLI writes the pooled `DATABASE_URL` and direct
`DATABASE_URL_UNPOOLED` connection strings to `.env.local` when there is no
root `.env`, or to `.env` otherwise. Keep these files private and uncommitted.
Normal application requests use the pooled URL. Run schema migrations through
the direct URL:

```powershell
docker compose run --rm -e NEON_USE_UNPOOLED_DATABASE=True web python manage.py migrate
```

When running Django directly, set `NEON_USE_UNPOOLED_DATABASE=True` in the
environment for migration commands and remove it afterwards. Without a
`DATABASE_URL`, Django uses the existing SQLite file selected by
`SQLITE_DATABASE_PATH` (default `foodplanner/db.sqlite3`).

Gemini configuration is optional; set `GEMINI_API_KEY` and the model settings
to enable the provider. Google sign-in requires `GOOGLE_OAUTH_CLIENT_ID` and
`GOOGLE_OAUTH_CLIENT_SECRET`; register the callback URL
`http://localhost:8080/accounts/google/login/callback/` for local use. Email
uses Django's console backend by default; set SMTP variables and
`EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` to send email.
Password recovery uses Django's one-hour, single-use reset tokens and the same
SMTP backend. For SendGrid SMTP, set the existing `EMAIL_HOST`,
`EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, and
`DEFAULT_FROM_EMAIL` variables (`smtp.sendgrid.net`, port `587`, username
`apikey`, TLS enabled). Put the SendGrid API key only in the ignored local
`.env` or deployment secrets, and set `DEFAULT_FROM_EMAIL` to an address
verified in SendGrid. Configure `SITE_URL` as `http://localhost:8080` locally;
production must use the public HTTPS URL. Reset URLs are built from `SITE_URL`,
not the incoming Host header; non-local HTTP URLs are rejected.
Password reset requests are limited to 3 per email address and 10 per client IP
per hour. Throttle identifiers are HMACed with Django's `SECRET_KEY` before
being stored; submitted email addresses and reset tokens are not stored.
Run `python manage.py migrate` to create the rate-limit table before deploying
the new flow.
For HTTPS deployments, configure TLS termination and set
`CSRF_TRUSTED_ORIGINS`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
`CSRF_COOKIE_SECURE`, and an appropriate `SECURE_HSTS_SECONDS` in `.env`.
For local HTTP, keep both secure-cookie settings false. Nginx forwards the
incoming `Host` including its port and forwards the actual HTTP scheme, so
Django's origin checks use the same origin as the browser.

### Cloudinary image storage

New meal images, Food-library images, and profile avatars use Cloudinary via
the official `cloudinary` Python SDK and Django's storage API. Set
`CLOUDINARY_URL` to the API environment variable from the Cloudinary Console.
The root `.env.example` shows the placeholder format; use the real value only
in your ignored local `.env` or deployment secret settings. For local Django
development, either place it in `foodplanner/.env` or export it before
starting Django; settings load the project-root `.env` as a fallback.

For Render, create a `CLOUDINARY_URL` environment variable on the FoodiePlug
web service using the value from Cloudinary. Do not set individual Cloudinary
credential variables alongside `CLOUDINARY_URL`; the SDK treats those as a
separate configuration style.

Uploads are placed under `foodieplug/avatars` for profile pictures and
`foodieplug/foods` for meal and Food-library images (both existing image
fields use the `foods/` upload path). The profile avatar server validation
matches its existing browser checks: JPEG, PNG, or WebP, no larger than 5 MiB.
Meal images retain their existing formats and 5 MiB limit. Uploads use random
Cloudinary public IDs and never overwrite existing assets. Replacing a photo
does not delete its previous asset; explicitly removing a photo clears its
database reference but leaves the stored file intact.

Existing database image names and local files are not migrated or modified.
Legacy local image paths continue to use `MEDIA_ROOT`/`MEDIA_URL` in local
development. Before deploying existing records to Render, plan a separate,
backed-up migration that uploads each local file, verifies its Cloudinary
asset and URL, and only then updates that record's image name. Do not point
existing records at Cloudinary before their files have been verified there.

### Back up and restore Docker data

Back up the running SQLite database using its online backup API, and copy the
result out of the container:

```powershell
docker compose exec -T web python -c "import sqlite3; from pathlib import Path; p=Path('/data/backups'); p.mkdir(exist_ok=True); src=sqlite3.connect('/data/db.sqlite3'); dst=sqlite3.connect('/data/backups/foodieplug.sqlite3'); src.backup(dst); dst.close(); src.close()"
New-Item -ItemType Directory -Force .\backups | Out-Null
docker compose cp web:/data/backups/foodieplug.sqlite3 .\backups\foodieplug.sqlite3
docker compose cp web:/data/media .\backups\media
```

Restore only while the app is stopped. Keep a separate copy of the current
database before restoring. With the backups at
`.\backups\foodieplug.sqlite3` and `.\backups\media`:

```powershell
docker compose stop web nginx
$backup = (Resolve-Path .\backups\foodieplug.sqlite3).Path
docker compose run --rm --no-deps -v "${backup}:/restore/db.sqlite3:ro" web python -c "import sqlite3; src=sqlite3.connect('file:/restore/db.sqlite3?mode=ro', uri=True); dst=sqlite3.connect('/data/db.sqlite3'); src.backup(dst); dst.close(); src.close()"
$media = (Resolve-Path .\backups\media).Path
docker compose run --rm --no-deps -v "${media}:/restore/media:ro" web python -c "import shutil; shutil.copytree('/restore/media', '/data/media', dirs_exist_ok=True)"
docker compose start web nginx
```

Media restore copies backup files into the persisted media directory and
overwrites same-named files; it does not delete other files already there.
Review and remove any files absent from the backup only if you intend a full
media rollback.

The named `app_data` volume contains the active database and uploads;
`static_files` contains collected static assets. Back up both the database and
media. The initial seed is performed only once and will not merge later
changes from the original `foodplanner/` directory into an existing Docker
volume.