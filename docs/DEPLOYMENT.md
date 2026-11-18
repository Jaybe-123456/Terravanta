# CI/CD and production deployment

## Current deployment path

Production uses GitHub Actions for CI, Render for the FastAPI/PostGIS service, and Vercel for the Next.js application. The GitHub workflow does not publish GHCR images or connect to a VPS. The older `docker-compose.production.yml` and `Caddyfile` remain an optional self-managed deployment path and are not part of this release workflow.

`.github/workflows/ci-cd.yml` runs on pull requests and pushes to `main`:

- `API tests` runs the API suite on an isolated SQLite database.
- `PostGIS migration check` applies every Alembic migration to PostGIS 16 and verifies the migration head.
- `Web checks and production build` runs TypeScript, browser-storage tests, and the optimized Next.js build in the access-code auth mode used by the production pilot.

The jobs use placeholder/local configuration only; they receive no production credentials. Render is configured for `autoDeployTrigger: checksPass`, so its Git-connected service deploys `main` after the repository checks pass. Vercel creates a production deployment from the production branch; configure Vercel Deployment Checks to hold promotion until the three GitHub checks above pass. Vercel’s Git integration and Render’s Git integration perform the provider deployments; no deploy key, GHCR token, Render deploy hook, or Vercel token is needed in GitHub Actions.

## One-time provider configuration

### GitHub

Confirm the connected repository is `Jaybe-123456/Terravanta`, the production branch is `main`, and Actions are enabled. Keep the workflow’s `contents: read` permission. No `PRODUCTION_DEPLOY_ENABLED` variable or SSH/GHCR secrets are used by this pipeline.

For direct pushes, branch protection is optional. If you use pull requests, require the `API tests`, `PostGIS migration check`, and `Web checks and production build` statuses before merge. Keep these job names stable if Vercel Deployment Checks or branch rules reference them.

### Render

The Render API service must be linked to `Jaybe-123456/Terravanta` on `main` and use the checked-in Blueprint’s **After CI Checks Pass** deployment behavior (`autoDeployTrigger: checksPass`). Confirm the live service has the production environment variables and a private persistent disk from [the Render deployment guide](RENDER_DEPLOYMENT.md). Startup applies Alembic migrations before Uvicorn accepts traffic. Keep one API instance while evidence files use Render’s local persistent disk.

### Vercel

The Vercel project must be linked to `Jaybe-123456/Terravanta`, use `main` as its Production Branch, and have Root Directory `apps/web`. Keep the Next.js framework setting and the output directory `.next` from `apps/web/vercel.json`.

Set these in the Vercel **Production** environment and redeploy after changing them:

| Variable | Production value |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | `https://terravanta.onrender.com` |
| `NEXT_PUBLIC_AUTH_MODE` | `access_code` for the current email-code pilot |
| `NEXT_PUBLIC_SUPABASE_URL` | Terravanta Supabase project URL; needed when using `supabase` auth mode |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase publishable/anon key only; needed for `supabase` auth mode, never use a service-role key |

Open **Project Settings → Deployment Checks** and add the GitHub checks `API tests`, `PostGIS migration check`, and `Web checks and production build` for Production. This lets Vercel build a commit while holding its production domain promotion until those checks pass. Verify the connected Git project and exact Production Branch before the first push.

## Release flow

1. Push the reviewed commit to `main` in `Jaybe-123456/Terravanta`.
2. In GitHub Actions, wait for all three checks to pass. A failure blocks the Render deploy; Vercel must have the Deployment Checks above enabled to block production promotion as well.
3. In Render, confirm the API deploy for that commit is live and that the deploy log shows `alembic upgrade head` completed.
4. In Vercel, confirm the production deployment for the same commit passed Deployment Checks and was promoted to `https://terravanta-five.vercel.app`.
5. Check `https://terravanta.onrender.com/health` and `/docs`, then open the Vercel site and verify sign-in and a read/write workflow using an authorized account.

If a deploy fails, inspect that provider’s build/runtime logs and keep the previous live revision until the migration and new app version are understood. Alembic migrations run during API startup; take a database restore point and review migration compatibility before deploying schema changes. A rollback across a destructive migration requires a tested restore plan.

## Operational boundary

The deployment pipeline does not make the product ready for live financial files by itself. Before a real cooperative upload, confirm written authority, named-user access, private evidence storage, backups and restore, retention/deletion, malware scanning, incident handling, and the cooperative’s approved transfer process. See [receivables assurance](RECEIVABLES_ASSURANCE.md) and [the cooperative pilot kit](COOPERATIVE_PILOT_KIT.md).

Render documents Git deploys after CI checks pass in its [deploy documentation](https://render.com/docs/deploys). Vercel documents production Git deploys and deployment checks in its [Git integration](https://vercel.com/docs/git) and [Deployment Checks](https://vercel.com/docs/deployment-checks) guides.
