# Deploy the Terravanta API on Render

This Blueprint deploys the FastAPI container, a private managed PostgreSQL database, PostGIS, and a small persistent upload disk. The API image runs `alembic upgrade head` before Uvicorn starts. Its `/health` endpoint checks the database connection.

## Before creating the services

1. Choose Supabase Auth for email/password accounts or use the temporary access-code pilot below. If using Supabase, create a **dedicated Terravanta Supabase project**; do not use VetIOS credentials. Add the production Vercel URL to its allowed redirect URLs.
2. Identify the production Vercel origin, such as `https://terravanta.vercel.app`. The API CORS value must be the exact origin including `https://` and with no trailing slash. You can enter multiple exact origins separated by commas.
3. Review the Render plan selection and billing screen before confirming creation. The checked-in Blueprint selects a continuously running API service (0.5 CPU / 512 MB), a paid Postgres instance (0.5 CPU / 1 GB), and 1 GB persistent file storage. Render's current published prices put these at about **$7/month + $19/month + $0.25/month**, or roughly **$26.25/month**, before bandwidth, taxes, workspace fees, or future scaling. Confirm current prices in your account before provisioning.

Do not choose Render's free Postgres for real farmer data: Render says free databases expire after 30 days, have a 1 GB limit, and have no backups. The paid Postgres plan provides managed backups/PITR. The API's 1 GB disk keeps uploaded source documents across restarts; it is only attached to this one API instance and does not replace an object-storage/backup plan.

## Create the API and database

1. Push `render.yaml` to the `main` branch of `Jaybe-123456/Terravanta`.
2. In Render, choose **New → Blueprint** and connect that GitHub repository. Select `main` and let Render read `render.yaml`.
3. Before confirming, verify the resources shown are `terravanta-api` and `terravanta-db`, both in Singapore, and review the monthly charges.
4. Render will ask for the Blueprint's unsynced values. Set `CORS_ORIGINS` to your exact production Vercel origin. For Supabase Auth, also set `SUPABASE_URL` and `SUPABASE_ANON_KEY` to the dedicated Terravanta project values (never a service-role key). For email code sign-in, set the Resend variables described below.
5. Confirm creation. The API container's startup runs `alembic upgrade head`; the first migration enables PostGIS and creates the schema. `autoDeployTrigger: checksPass` means later commits deploy after GitHub checks pass.

## Get and verify the public API URL

When Render reports the API service as **Live**, open its service page and copy the `onrender.com` URL from the top. It will look like `https://terravanta-api-<suffix>.onrender.com`.

Open these URLs, replacing the host with the one Render assigned:

```text
https://<render-api-host>/health
https://<render-api-host>/docs
```

`/health` should return `{"status":"ok","service":"terravanta-api"}`. The `/docs` page should load. In **Events → Logs**, confirm startup completed the Alembic upgrade before Uvicorn started. If deployment fails, check the first migration/database error in the deploy logs; the database and API must stay in the same Render region.

## Connect the Vercel frontend

In the Vercel project for Terravanta, add these Production environment variables:

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | The Render API URL, with no trailing slash |
| `NEXT_PUBLIC_AUTH_MODE` | `supabase` for email/password, or `access_code` for the temporary pilot |
| `NEXT_PUBLIC_SUPABASE_URL` | Required only for `supabase` mode |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Required only for `supabase` mode |

Save the variables and redeploy the Production deployment because `NEXT_PUBLIC_API_URL` is compiled into the frontend build. Add the Vercel production URL to Supabase's redirect allowlist. After the Vercel URL is stable, keep `CORS_ORIGINS` on Render set to that exact origin and redeploy the API if you change it.

For Vercel Preview deployments, add their exact origin to Render's comma-separated `CORS_ORIGINS` only if you intentionally want previews to access the same real database. Keep preview access off by default to avoid mixing development builds with production farm records.

## Temporary access-code pilot

The access-code screen lets a user enter their name and email and request a sign-in code. The API sends an eight-digit one-time code to that address, stores only a keyed hash, allows up to five attempts, expires it after 10 minutes, and consumes it after successful verification. Verified emails can create farmer accounts; staff roles are not granted through this flow. The code is delivered by email and is never displayed in the browser or returned by the API.

On Render, set `TEMP_ACCESS_AUTH_ENABLED=true`, `RESEND_API_KEY` to a Resend sending-only API key, and `ACCESS_CODE_FROM_EMAIL` to a sender address on a domain verified in Resend (for example, `Terravanta <signin@your-verified-domain>`). Render free web services block outbound SMTP, so this integration sends through Resend's HTTPS API. Keep the existing `DEMO_AUTH_SECRET` unique and private; it signs temporary API sessions. On Vercel, set `NEXT_PUBLIC_AUTH_MODE=access_code`, keep `NEXT_PUBLIC_API_URL` pointed at the Render API, and redeploy Production. Supabase variables may remain configured but are not used by this access-code screen. Add Resend's required DNS records in your domain provider before requesting codes.

Users request codes directly in the sign-in form; no administrator PowerShell command is needed. The API limits each email to three requests per 15 minutes and all code requests to 100 per hour. Email verification confirms control of the address but does not itself establish a real-world identity. Vercel Deployment Protection is a separate front-door setting; app access codes cannot bypass it. Ensure the public Production domain is not protected by Vercel Auth if farmers should open it without a Vercel account.

## Operational limits before a real farm pilot

- This is a single API instance. The attached disk prevents horizontal scaling and zero-downtime API redeploys; move uploads to private S3-compatible storage before scaling.
- The API container applies Alembic migrations during startup, so deploy one instance at a time. Review every schema change and have a database restore point before production schema changes.
- Confirm Render's Postgres backups and retention in the database dashboard, and test restoring a backup before storing identifiable farm records.
- Add monitoring, incident response, access reviews, privacy notice and retention policy before inviting real farmers. Keep NVIDIA credentials unset until external processing terms and consent are approved.

## Local checks

From the repository root:

```powershell
docker compose --env-file .env.example -f docker-compose.yml config --quiet
```

The current local Compose stack is separate from Render. It does not provision, modify, or connect to VetIOS.
