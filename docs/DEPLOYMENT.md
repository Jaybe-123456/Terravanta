# CI and production deployment

## What the pipeline does

`.github/workflows/ci-cd.yml` runs API tests and the web typecheck, tests and optimized build for pull requests and pushes to `main`. It never receives production secrets during those jobs. On `main`, the production job remains skipped until the repository variable `PRODUCTION_DEPLOY_ENABLED` is exactly `true`. Once enabled, it builds revision-tagged API and web images, publishes them to GHCR, copies the production Compose and Caddy files to the VPS, then rolls out the same commit and waits for health checks.

The production job uses a GitHub `production` environment. Configure required reviewers there if you want a manual approval gate before credentials are released. GitHub recommends least-privilege workflow permissions and immutable action references; this workflow pins its action dependencies to full commit SHAs and requests package-write permission only in the release job. Review and update the action SHAs as part of dependency maintenance.

## Required infrastructure

- A Linux VPS with Docker Engine and Docker Compose v2, a static public IP, and inbound TCP ports 80 and 443 open.
- A DNS A/AAAA record for the production hostname pointing to that VPS before the first deploy. Caddy obtains and renews HTTPS certificates.
- A dedicated Terravanta Supabase project with email confirmation enabled and the production URL added to its Auth redirect allowlist.
- SSH deploy user restricted to this host, with permission to run Docker Compose in `/opt/terravanta`.
- A GHCR read-only token for the VPS (`read:packages`) and the GitHub Actions `GITHUB_TOKEN` package-write permission.
- Off-host encrypted database and upload backups plus a tested restore procedure before real-farm production use. The provided Compose file persists database and uploads on the VPS; it is not a backup service or high-availability design.

## GitHub configuration

Set repository variables:

| Variable | Value |
| --- | --- |
| `PRODUCTION_DEPLOY_ENABLED` | `true` only after the host and secrets are ready |
| `PUBLIC_DOMAIN` | The public hostname, for example `app.example.co.ke` |
| `SUPABASE_URL` | The dedicated Terravanta project's URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase publishable/anon client key; never use a service-role key |

Set these secrets in the GitHub `production` environment:

| Secret | Value |
| --- | --- |
| `PROD_SSH_HOST` | VPS hostname or IP |
| `PROD_SSH_USER` | Restricted deployment username |
| `PROD_SSH_PORT` | SSH port, usually `22` |
| `PROD_SSH_PRIVATE_KEY` | Deploy key private half; install the public half for this user |
| `PROD_SSH_KNOWN_HOSTS` | Verified `known_hosts` line for the VPS; do not disable host-key checks |
| `GHCR_PULL_USER` | GitHub account with package read access |
| `GHCR_PULL_TOKEN` | Fine-scoped token with `read:packages` for the Terravanta package |

## First server setup

On the Linux VPS, create `/opt/terravanta/.env.production` from the checked-in `.env.production.example`. Replace every placeholder. Use long random hexadecimal values for `POSTGRES_PASSWORD` and `DEMO_AUTH_SECRET` so the database URL does not need special-character escaping. Keep this file readable only by the deployment user (`chmod 600`). Do not commit it or paste its contents into logs or chat.

Set `PUBLIC_DOMAIN`, `SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `IMAGE_PREFIX=ghcr.io/jaybe-123456/terravanta`, and `IMAGE_TAG` in that file. Use a deployed commit SHA for any manual rollout; the GitHub workflow overrides it with the exact revision being deployed. Optional NVIDIA credentials stay blank until the model account, terms and data controls are approved. The API refuses production startup if auth is misconfigured or synthetic data is enabled.

The GitHub deployment logs into GHCR on the server using the read-only token, uploads `docker-compose.production.yml` and `Caddyfile`, pulls both images tagged with the commit SHA and runs Alembic migrations through the API container before serving traffic. PostgreSQL and uploads stay on named VPS volumes. The database has no public port; only Caddy exposes 80/443. The reverse proxy sends `/api/v1/*` and API docs/health routes to FastAPI, while `/api/session` stays on Next.js for the secure refresh-token cookie.

## Manual workflow and rollback

For the first release, complete the server setup and configure GitHub variables/secrets above. Push to `main`; CI must pass and the production environment approval must be granted. To roll back, redeploy a previously successful image by checking out that commit and using the production workflow, or add an explicit rollback workflow before operating a customer dataset. Do not roll back across a destructive database migration without a tested backup and migration plan.

Local validation uses the existing `docker-compose.yml` and does not require enabling the production release job:

```powershell
docker compose --env-file .env.example -f docker-compose.yml config --quiet
```

Production planning: use [the product market wedge and pilot plan](GO_TO_MARKET.md) and [the reconciliation workflow contract](COOPERATIVE_RECONCILIATION.md). The current VPS topology is a pilot deployment path. Before production processing of identifiable farm records, complete backups/restore, storage retention and malware scanning, monitoring/alerting, incident response, operator access review and privacy notices.
