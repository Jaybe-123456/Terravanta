# Deploy the Terravanta API and PostGIS database on Render

The Render Blueprint provisions the FastAPI service and one persistent disk for private evidence files. The existing Render PostgreSQL/PostGIS database is managed separately and must not be replaced by a new database during Blueprint sync. Supabase is used for Auth only. Render PostgreSQL remains the source of truth for farm and cooperative data; Alembic manages its schema.

## Connect the repository

1. Push the reviewed Blueprint to `main` in `Jaybe-123456/Terravanta`.
2. In Render, choose **New → Blueprint**, connect that repository and branch, and review `render.yaml` before confirming.
3. Verify the API and database region match. Configure the requested Supabase values from Terravanta's dedicated project, never VetIOS.
4. Confirm the API service and PostGIS database are ready. Keep the existing evidence disk attached while using the local evidence backend.

The Blueprint leaves both database URLs unsynced. Set `MIGRATIONS_DATABASE_URL` manually to the internal owner connection string for the existing production database (`terravanta-db-dev`); `DATABASE_URL` is a separate restricted runtime login and must not use owner credentials.

## Prepare the restricted runtime login

Do this before deploying migration `0008_tenant_rls` to the existing database. In Windows PowerShell, install the Render CLI with `winget install render.cli`, open a new PowerShell window, run `render login`, authorize it in your browser, then run `render psql <actual-db-name-or-id>`. Use the live resource name/ID shown in the Render Dashboard; existing database names can differ from the `terravanta-db` Blueprint alias. This opens an interactive psql session without putting the database connection string in shell history. Alternatively use the external connection details with an authorized SQL client. Generate a strong password in PowerShell and keep it out of chat, SQL text, source control and local `.env` files.

For Windows PowerShell 5.1, generate 32 random bytes as URL-safe hexadecimal and copy them to the clipboard without printing or saving a file:

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$runtimePassword = ([BitConverter]::ToString($bytes) -replace '-', '').ToLowerInvariant()
Set-Clipboard -Value $runtimePassword
$runtimePassword = $null
$bytes = $null
$rng.Dispose()
```

In the owner psql session, first check for existing roles:

Confirm you are connected as the database owner before changing roles:

```sql
SELECT current_user AS connected_as, pg_get_userbyid(datdba) AS database_owner
FROM pg_database WHERE datname = current_database();
```

If those names differ, stop and reconnect as the database owner. Then check for existing roles:

```sql
SELECT rolname, rolcanlogin, rolbypassrls
FROM pg_roles
WHERE rolname IN ('terravanta_app', 'terravanta_runtime');
```

For each role that does not already exist, run the corresponding `CREATE ROLE` command below. If it exists, use the matching `ALTER ROLE` command instead. Then grant membership and set the runtime password using psql's hidden prompt:

```sql
CREATE ROLE terravanta_app NOLOGIN INHERIT NOBYPASSRLS;
CREATE ROLE terravanta_runtime LOGIN INHERIT NOBYPASSRLS;
GRANT terravanta_app TO terravanta_runtime;
```

In that same interactive psql session, run the psql command separately; it is not SQL:

```text
\password terravanta_runtime
```

When `terravanta_app` exists, use `ALTER ROLE terravanta_app NOLOGIN INHERIT NOBYPASSRLS;` in place of its create command. When `terravanta_runtime` exists, use `ALTER ROLE terravanta_runtime LOGIN INHERIT NOBYPASSRLS;` in place of its create command. Keep the grants and run `\password terravanta_runtime` separately. Paste the clipboard value twice at psql's hidden prompts. This keeps the password out of SQL text and psql history. Render CLI setup and `psql` access are documented by [Render](https://render.com/docs/cli); PostgreSQL documents `\password` as the way to change a role password without exposing it in command history.

Keep the current `DATABASE_URL` while preparing the role. Deploy the commit containing migration `0008_tenant_rls` with `MIGRATIONS_DATABASE_URL` still set to the database owner, then wait for the Render logs to confirm `alembic upgrade head` succeeded. Only then change the API's `DATABASE_URL` to the restricted runtime login and redeploy. This avoids restarting the pre-migration API with a login that does not yet have the migrated table grants and policies.

On the `terravanta-api` service, set:

| Variable | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `MIGRATIONS_DATABASE_URL` | Internal owner URL for the existing `terravanta-db-dev` database |
| `DATABASE_URL` | Internal Render URL using `terravanta_runtime`; format `postgresql+psycopg://terravanta_runtime:<password>@<internal-host>:5432/<database-name>` |
| `SUPABASE_URL` | Dedicated Terravanta Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase publishable/anon key only |
| `PUBLIC_APP_ORIGIN` | `https://terravanta-five.vercel.app` |
| `CORS_ORIGINS` | Exact additional origins, if needed; no wildcard Vercel previews |
| `ENABLE_SYNTHETIC_DATA` | `false` |

Use the internal database URL for a Render-hosted API. Keep the database and API in the same region. The generated hexadecimal password is URL-safe. After setting `DATABASE_URL` in the Render API service, clear the clipboard with `Set-Clipboard -Value ''`. Keep `MIGRATIONS_DATABASE_URL` on the owner URL and never set runtime `DATABASE_URL` to the owner connection string. SQL-created roles are not displayed or rotated through Render's database Credentials UI; rotate their password with psql `\password` and update `DATABASE_URL` together. The API validates that Supabase and both PostgreSQL URLs are configured before production startup. The Blueprint intentionally does not provision a replacement database.

## Verify the API

After deployment, open:

```text
https://terravanta.onrender.com/health
https://terravanta.onrender.com/docs
```

The health endpoint should return `{"status":"ok","service":"terravanta-api"}`. In the deploy logs, confirm `alembic upgrade head` completed and the API connected through the runtime login. A permission error for `SET ROLE terravanta_app` means the runtime login is missing its group membership; correct the database grants instead of switching to the owner URL.

## Supabase Auth and Vercel

The custom email-code sign-in and Resend integration are removed. Supabase Auth handles email/password sign-up, sign-in, confirmation and sessions. In the dedicated Supabase project, set Site URL to `https://terravanta-five.vercel.app`, allow that exact production redirect plus the local development URL, and enable the email/password provider.

Set these Vercel Production variables, then redeploy:

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | `https://terravanta.onrender.com` |
| `NEXT_PUBLIC_AUTH_MODE` | `supabase` |
| `NEXT_PUBLIC_SUPABASE_URL` | Dedicated Terravanta Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Publishable/anon key only |

The API accepts the stable production origin. Add another origin to Render only when it is intentionally trusted to access production farm data. Never expose a service-role key to the browser.

## Evidence storage and live records

The Blueprint attaches a one-instance persistent disk for private evidence files. Do not scale the API horizontally while using local-disk evidence. Before scaling, move to a private S3-compatible bucket, disable public access and test retrieval, deletion and backup. Malware scanning and automatic retention/deletion are not implemented.

Before a cooperative uploads live processor records, obtain written authority for those records and agree on named-user access, purpose, retention, deletion and incident handling. Receivables exports contain the underlying evidence files and must use the cooperative's approved secure transfer channel. The product records each party's position; it does not determine a legal debt or initiate payment.
