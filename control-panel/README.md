# ShopKeeper Control Panel

Private admin-only Django site for managing shopkeeper accounts. It uses server-rendered templates and Tailwind CSS via CDN and requires PostgreSQL. Configure `DATABASE_URL` for the shared PostgreSQL database used by ShopKeeper.

## Database layout

The panel sets `search_path` to `shopkeeper_control,public`. Its own admin, session, axes, migration, and audit tables live in the `shopkeeper_control` schema. ShopKeeper-owned mirror models are unmanaged and read/write the existing public business tables; the shopkeeper login mirror uses `public.auth_user`. ShopKeeper migrations run only from the ShopKeeper project.

## Free PostgreSQL setup (Neon + Render)

Neon currently lists a permanent Free plan. Its published limits include 100 CU-hours per project, 1 GB storage per project, and automatic scale-to-zero after inactivity; check the current [Neon pricing page](https://neon.com/pricing) before deploying.

### 1. Create the database

1. Create/sign in to a Neon account at [console.neon.tech](https://console.neon.tech/).
2. Create a project on the Free plan, select a region near your Render services, and save the database credentials securely.
3. In Neon, use **Connect** to copy the PostgreSQL connection string. Use the same database/project for both apps. Never put the real connection string in source control or chat.

### 2. Point ShopKeeper at Neon

In Render, open the ShopKeeper web service's **Environment** settings. Set `DATABASE_URL` to the Neon connection string and save/redeploy. Keep the ShopKeeper service's other environment variables, such as `SECRET_KEY`, separate and unchanged.

The ShopKeeper build applies ShopKeeper-owned migrations, including the announcement scheduling/targeting migration. Confirm deployment succeeds before connecting the panel.

### 3. Create the separate Control Panel service

Keep the GitHub repository private. Create a separate Render Web Service using the same private repository and set its **Root Directory** to `control-panel`.

- Build command: `bash build.sh`
- Start command: `gunicorn controlpanel.wsgi:application`
- Health check path: `/health/`

Set these environment variables on this Control Panel service:

- `DATABASE_URL`: the same Neon PostgreSQL connection string used by ShopKeeper.
- `SECRET_KEY`: a newly generated, unique value; do not reuse ShopKeeper's secret.
- `DEBUG`: `False`.
- `ALLOWED_HOSTS`: the exact Control Panel Render hostname.
- `ALLOWED_IPS` (optional): comma-separated client IPs, after confirming the proxy's remote-address behavior.

The build creates the panel-only schema, runs only the Control Panel's migrations, and collects static files. The Neon database role must have permission to create a schema and tables. If it cannot create the schema, grant permissions or use a role that can; do not point the panel's migrations into `public`.

### 4. Create the Control Panel superuser

After the Control Panel service deploys successfully, create its superuser from your local PowerShell. This runs panel commands against the same Neon database, so do not accidentally point `DATABASE_URL` at a different project:

```powershell
Set-Location "C:\path\to\your\repository\control-panel"
$env:DATABASE_URL = "paste-the-Neon-connection-string"
$env:SECRET_KEY = "a-long-local-command-secret"
$env:DEBUG = "False"
$env:ALLOWED_HOSTS = "localhost,127.0.0.1"
& "..\.venv\Scripts\python.exe" manage.py ensure_control_schema
& "..\.venv\Scripts\python.exe" manage.py migrate
& "..\.venv\Scripts\python.exe" manage.py createsuperuser
```

Use the repository's virtual environment executable as shown, or create a separate virtual environment inside `control-panel` and install its `requirements.txt`. Keep the same Neon `DATABASE_URL` for the migration and superuser commands. Sign in at `https://<control-panel-host>/login/`.

### Free-tier behavior and cautions

- Neon Free compute scales to zero when idle, so the first request after inactivity may be slow. Free Render web services also spin down when idle. This is suitable for testing/hobby workloads, not a guarantee of always-on availability.
- A Neon database is shared across services, but stays subject to the provider's quotas, suspension, and free-plan changes. Monitor storage/compute and keep independent backups.
- Don't run the ShopKeeper migrations from the Control Panel service. It intentionally mirrors ShopKeeper business models as unmanaged tables.
- Test account creation, password resets, deactivation, and stock-fix controls with a non-production shop before using the panel against live records.

## Local development

```powershell
Set-Location "C:\path\to\your\repository\control-panel"
Copy-Item ".env.example" ".env"
# Fill DATABASE_URL and SECRET_KEY in .env with your PostgreSQL credentials.
& "..\.venv\Scripts\python.exe" manage.py ensure_control_schema
& "..\.venv\Scripts\python.exe" manage.py migrate
& "..\.venv\Scripts\python.exe" manage.py createsuperuser
& "..\.venv\Scripts\python.exe" manage.py runserver
```

Open `http://127.0.0.1:8000/login/`. Only active staff/superuser accounts can sign in; public sign-up is not provided. Sessions expire after 30 minutes of inactivity.

Run tests from `control-panel` with `& "..\.venv\Scripts\python.exe" manage.py test panel`.

Both apps load environment variables from their own local `.env` file using `python-dotenv`. These files are ignored by Git. Render does not receive ignored local files: set the same `DATABASE_URL` separately in each Render service's **Environment** page, with a different `SECRET_KEY` for each service. Never commit or share the populated `.env` files.
