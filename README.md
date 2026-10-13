# ShopSetu

ShopSetu is a mobile-first Django application for Indian small retailers. It provides tenant-scoped shop operations, manual batch stock, FEFO billing, invoices, customer credit, WhatsApp hand-offs, and owner reports. The interface is server-rendered with Django templates, HTMX, and Tailwind CSS via CDN.

## Run locally

1. Install Python 3.11 or newer.
2. Create and activate a virtual environment, then install dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and set a PostgreSQL `DATABASE_URL` and private `SECRET_KEY`. The app no longer supports SQLite. The `.env` file is loaded automatically and must not be committed:

   ```powershell
   Copy-Item .env.example .env
   ```

   Fill in the real PostgreSQL connection URL from your database provider. For Render, set environment variables in the service settings instead.
4. Create the database schema and platform administrator:

   ```powershell
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py runserver
   ```
5. Visit `http://127.0.0.1:8000/platform-admin/`. Create a Shop, then a User with a username and password, and then a UserProfile linking that user to the shop with role `OWNER`. The owner is required to change the initial password and complete the shop setup on first login.
6. To create sample data instead, run `python manage.py create_demo_shop`. The command prints a one-time generated password; the demo user must change it at first login.

The public app has no sign-up page. Platform-created accounts log in at `/login/`. The Django platform administration app is separate at `/platform-admin/`.

## Free deployment (Render + Neon)

1. Create a GitHub repository, add this project, and push the default branch.
2. Create a free PostgreSQL project/database in [Neon](https://neon.tech/). Copy the pooled connection string; it should use PostgreSQL and SSL (Neon supplies the appropriate URL).
3. In Render, choose **New + → Blueprint**, connect the GitHub repository, and deploy the included `render.yaml`. The blueprint runs `build.sh` to migrate the schema and collect static files before starting Gunicorn.
4. In the Render service environment, set:
   - `DATABASE_URL`: Neon connection string.
   - `SECRET_KEY`: a newly generated, private random value (Render can generate one).
   - `DEBUG`: `False`.
   - `ALLOWED_HOSTS`: your exact Render hostname, for example `shopsetu.onrender.com`.
   - `CSRF_TRUSTED_ORIGINS`: `https://shopsetu.onrender.com`.
5. Wait for the deploy to finish. Use the Render shell or a one-off command to run `python manage.py createsuperuser`.
6. Open `https://<your-render-host>/platform-admin/`, create each Shop, owner User, and associated UserProfile. Admin users can also create read-only-in-app Announcements there.
7. Check `https://<your-render-host>/health/`. Point a free uptime monitor at this endpoint if desired. Render's free web services may still spin down; an uptime pinger can reduce, but does not guarantee elimination of, cold starts.

ShopSetu requires PostgreSQL for local and hosted use. Free database limits and availability are controlled by the provider and can change; retain independent backups.

## Tenant and role boundaries

Every shop-owned model includes a `shop` foreign key and a custom queryset supports `for_user(user)` scoping. Shop pages and data services explicitly bind reads and writes to the authenticated profile's shop; public invoice access is limited to an unguessable token. Staff can bill and view inventory, while owner-only actions protect product price edits, corrections, reports, promotions, and staff management. Platform operations use Django admin.

## Included operations

- Password-change gate, inactive/expired-shop gate, and django-axes login throttling.
- Product catalog, manual stock batches, expiry visibility, and mandatory-reason quantity corrections.
- Atomic invoice creation with row-locked batches, FEFO allocation, expired-batch skipping, and stock restoration on cancellation.
- Shareable print invoice (browser print CSS and downloadable PDF), GST split display, public invoice token URL, and wa.me links.
- Customer records, credit statement and reminders, and repeatable opted-in WhatsApp promotions. The promotion Send button opens the selected customer's WhatsApp chat with prefilled text; attach any selected image/PDF in that chat and confirm sending manually. WhatsApp does not allow this free web app to send messages or media directly.
- Platform announcements support optional schedules and shop targeting, managed by the separate private Control Panel.
- Owner reports and CSV exports, PWA manifest/icons, and `/health/` endpoint.

## Tests and checks

```powershell
python manage.py test store
python manage.py check
```
