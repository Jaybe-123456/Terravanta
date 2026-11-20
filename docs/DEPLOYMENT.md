# CI/CD and production deployment

## Runtime boundaries

Production uses GitHub Actions for CI, Render for the FastAPI and PostgreSQL/PostGIS services, Vercel for the Next.js app, and a dedicated Supabase project for identity only. Render PostgreSQL remains the canonical store for farm, c ooperative, settlement, receivables and audit records. The browser never connects directly to that database. FastAPI owns the `/api/v1` business API and verifies Supabase JWTs before opening a transaction with a request-scoped user identity for PostgreSQL RLS.

The email-code sign-in flow and its Resend integration have been removed. Supabase Auth manages passwords, email confirmation, sessions and recovery. Set `NEXT_PUBLIC_AUTH_MODE=supabase` in Vercel Production. Supabase email delivery is configured in the Supabase Auth project; no Terravanta API email-code variables are used.

## CI checks

`.github/workflows/ci-cd.yml` runs on pull requests and pushes to `main`:

- `API tests` runs the API suite against an isolated SQLite database.
- `PostGIS migration check` applies every Alembic migration, including the tenant RLS policies, to PostgreSQL/PostGIS, then exercises farmer isolation and the cooperative's consent-limited farm-card projection.
- `Web checks and production build` runs lint, browser-storage tests and a production Next.js build with Supabase auth mode.

CI has no production credentials. Render deploys after checks pass through its Git integration. Vercel creates the production build from the production branch; configure Vercel Deployment Checks to require the three GitHub checks before promotion. GitHub Actions does not need a Render deploy token, Vercel token, SSH key or database secret.

## Supabase Auth setup

Use a dedicated Terravanta Supabase project, separate from VetIOS. In Authentication → URL Configuration, set the Site URL to `https://terravanta-five.vercel.app` and add exact redirect URLs for that production origin and local development (for example `http://localhost:3001`). Keep wildcard preview URLs out of production. Enable email/password sign-in and the email confirmation policy appropriate for the pilot.

Set the following Vercel **Production** variables and redeploy:

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | `https://terravanta.onrender.com` |
| `NEXT_PUBLIC_AUTH_MODE` | `supabase` |
| `NEXT_PUBLIC_SUPABASE_URL` | Dedicated Terravanta Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase publishable/anon key only |

Never use a Supabase service-role key in the browser or Vercel `NEXT_PUBLIC_*` variables. The Next.js session route stores the Supabase refresh token in an HttpOnly, same-origin cookie; FastAPI validates the short-lived bearer JWT and provisions the Terravanta user profile on `/api/v1/auth/onboard`. Self-registration grants only the farmer role. A verified email matching an existing legacy farmer profile is linked to its original Terravanta user UUID by migration `0008_tenant_rls`, preserving farm history; conflicting staff identities require operator review. Staff roles are assigned through the trusted operator workflow.

## Render database roles and environment

Keep `MIGRATIONS_DATABASE_URL` connected as the Render database owner. `DATABASE_URL` must use a separate runtime login that is a member of the non-login `terravanta_app` role created by Alembic. Do not point the API runtime at the owner connection string. The runtime role is limited to the application table grants and RLS policies; it cannot bypass RLS or run DDL.

Before deploying migration `0008_tenant_rls` to an existing Render database, connect as its owner and prepare the runtime role. The SQL below deliberately uses psql's `\password` command rather than placing the password in SQL text, PowerShell history, or a connection command.

Generate a 256-bit password in Windows PowerShell 5.1 and copy it to the clipboard without printing or saving it. Keep the clipboard only long enough to paste it into psql's hidden password prompts and the Render `DATABASE_URL` field:

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

Install the Render CLI in Windows PowerShell with `winget install render.cli`, open a new PowerShell window, then run `render login` and select the workspace. Use the exact live Postgres resource name or ID shown by `render psql`/the Render Dashboard; existing database names can differ from the `terravanta-db` Blueprint alias. In the interactive psql session, check whether either role already exists before creating it:

First confirm the connection is to the existing database and its owner account; if `connected_as` and `database_owner` differ, stop and connect with the owner credentials:

```sql
SELECT current_user AS connected_as, pg_get_userbyid(datdba) AS database_owner
FROM pg_database WHERE datname = current_database();
```

Then check whether either role already exists:

```sql
SELECT rolname, rolcanlogin, rolbypassrls
FROM pg_roles
WHERE rolname IN ('terravanta_app', 'terravanta_runtime');
```

For roles that do not exist, run:

```sql
CREATE ROLE terravanta_app NOLOGIN INHERIT NOBYPASSRLS;
CREATE ROLE terravanta_runtime LOGIN INHERIT NOBYPASSRLS;
GRANT terravanta_app TO terravanta_runtime;
```

In that same interactive psql session, run this psql command separately (it is not SQL and should not be pasted into a dashboard SQL editor):

```text
\password terravanta_runtime
```

If `terravanta_app` already exists, use `ALTER ROLE terravanta_app NOLOGIN INHERIT NOBYPASSRLS;` instead of its `CREATE ROLE` statement. If `terravanta_runtime` exists, use `ALTER ROLE terravanta_runtime LOGIN INHERIT NOBYPASSRLS;` instead of its `CREATE ROLE` statement. Keep the `GRANT` statements and run `\password terravanta_runtime` separately to set or rotate its password. At the hidden prompts, paste the clipboard value twice; psql does not echo it or put the cleartext in its command history. The migration creates `terravanta_app` if missing, configures its RLS policies and table grants, and then the runtime login can assume it.

Keep the current `DATABASE_URL` while preparing the role. Deploy the commit containing migration `0008_tenant_rls` with `MIGRATIONS_DATABASE_URL` still set to the database owner, and wait until the Render logs confirm `alembic upgrade head` completed. Then update `DATABASE_URL` so the API uses the restricted runtime role; this avoids restarting the pre-migration API with a role that does not yet have the migrated table grants and policies.

In the Render `terravanta-api` service, set `DATABASE_URL` to the **internal** Render Postgres host and database, replacing only the username and password. Use the SQLAlchemy scheme and keep the password out of chat, local `.env` files and source control:

```text
postgresql+psycopg://terravanta_runtime:<generated-64-character-hex-password>@<internal-host>:5432/<database-name>
```

The generated hexadecimal password is URL-safe and needs no escaping. Leave `MIGRATIONS_DATABASE_URL` on the owner connection. After saving the Render variable, clear the local clipboard with `Set-Clipboard -Value ''`. Configure the remaining Render variables as follows:

| Variable | Production value |
| --- | --- |
| `APP_ENV` | `production` |
| `MIGRATIONS_DATABASE_URL` | Render Postgres owner connection string |
| `DATABASE_URL` | Same database, connected as `terravanta_runtime`; use `postgresql+psycopg://` form |
| `SUPABASE_URL` | Dedicated Terravanta Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase publishable/anon key only |
| `PUBLIC_APP_ORIGIN` | `https://terravanta-five.vercel.app` |
| `CORS_ORIGINS` | Additional exact trusted origins only; do not add `*.vercel.app` |
| `ENABLE_SYNTHETIC_DATA` | `false` |

The Blueprint leaves `MIGRATIONS_DATABASE_URL` and `DATABASE_URL` unsynced because the existing production Postgres resource is managed separately. Set `MIGRATIONS_DATABASE_URL` to its internal owner URL and `DATABASE_URL` to the restricted runtime login after migration `0008_tenant_rls` succeeds. The Blueprint does not provision a replacement database. The production API refuses to start if `DATABASE_URL` is absent/non-PostgreSQL, Supabase Auth is missing, or the migration connection is not set. Render does not manage SQL-created roles in its Credentials UI; rotate the `terravanta_runtime` password with psql `\password`, update the Render `DATABASE_URL` at the same time, then redeploy.

Confirm the API's database URL and startup logs before promoting a release. After migration, `GET /health` uses the runtime role. A database health response confirms connectivity; the PostGIS migration check in GitHub confirms the migration chain was applied in CI. Do not set `DATABASE_URL` to the owner URL as a workaround for a role error.

## Release flow

1. Push the reviewed commit to `main` in `Jaybe-123456/Terravanta`.
2. Wait for all three GitHub Actions checks. Render is configured to deploy only after checks pass; Vercel must have the same checks enabled in Project Settings → Deployment Checks.
3. Confirm the Render deploy ran `alembic upgrade head`, connected with the migration URL, then passed health checks through the restricted runtime URL.
4. Confirm Vercel promoted the matching commit to `https://terravanta-five.vercel.app`.
5. Open `/health` and `/docs` on the Render API, then sign in from a clean browser profile using a Supabase Auth account. Verify onboarding, farm creation and a read/write workflow with the intended role.

For rollback, keep schema changes additive until the previous app version is no longer needed. Take a database restore point and review migration compatibility before deploying. Do not run an unreviewed downgrade across the RLS migration.

## Edge Functions boundary

Supabase Edge Functions are intentionally not a second Terravanta application API. Core farm, receivables, settlement, evidence and audit workflows stay in the versioned FastAPI API because they use the Render/PostGIS database and its RLS context. Introduce a Supabase Edge Function only for a concrete short-lived integration such as an authenticated Auth webhook or processor callback, with the sender's signature/retry contract specified. No partner webhook contract is configured yet, so there is no deployed Edge Function to claim as active.

Before a real cooperative upload, confirm written authority, named-user access, private evidence storage, backups and restore, retention/deletion, malware scanning, incident handling and the cooperative's approved transfer process. See [receivables assurance](RECEIVABLES_ASSURANCE.md), [the cooperative pilot kit](COOPERATIVE_PILOT_KIT.md), and [the core platform architecture](CORE_PLATFORM_ARCHITECTURE.md).
