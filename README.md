# Terravanta

Terravanta is a veterinary-first farm-record product for Kenyan mixed farms. Its initial market wedge connects a farmer's dairy production and animal records to cooperative delivery summaries under explicit, revocable consent. Real-account mode is the default. It does not create synthetic records unless `ENABLE_SYNTHETIC_DATA=true` is explicitly set.

The product has three role-specific workspaces:

- **Farmer:** register farms, plots and animals; record health, feed, crop–livestock resources and production; trace deliveries; grant or revoke a cooperative's delivery-summary access.
- **Veterinarian:** review assigned open cases, verify farmer-submitted health events, and create clinical records. A verification signature is separate from AI output.
- **Cooperative administrator:** view only active, consented delivery summaries, reconciliation counts and missing delivery references. Clinical and laboratory records are excluded from this scope.

See [architecture](docs/ARCHITECTURE.md), [implemented scope and limitations](docs/ROADMAP.md), [synthetic demo data](docs/SYNTHETIC_DEMO_DATA.md), and the [market wedge, GTM and PMF validation plan](docs/GO_TO_MARKET.md).

To deploy the public API and managed PostGIS database on Render, use the [Render deployment guide](docs/RENDER_DEPLOYMENT.md) and the checked-in `render.yaml` Blueprint.

The initial commercial workflow is a cooperative milk-reconciliation service: import a daily collection sheet, match it to delivery records shared with consent, review exceptions, and trace each intake row to its source. The upload contract, deterministic rules, reviewer loop and success measures are documented in [the reconciliation service contract](docs/COOPERATIVE_RECONCILIATION.md).

## Run locally with Docker Compose

Prerequisites: Docker Desktop with the Linux container engine, Node/Python are not needed for the Compose path.

```powershell
Copy-Item .env.example .env
```

Edit `.env`. Set unique local values for `POSTGRES_PASSWORD` and `DEMO_AUTH_SECRET`, then configure a **dedicated Terravanta Supabase project**: set `SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, and `NEXT_PUBLIC_SUPABASE_ANON_KEY`. Leave `SUPABASE_JWKS_URL` blank to derive the standard endpoint. In Supabase Auth URL Configuration, allow `http://localhost:3001` as a redirect URL. Do not point Terravanta at VetIOS' Supabase project.

Start the services from the repository root:

```powershell
docker compose config --quiet
docker compose up --build -d
```

The example ports are 3000 and 8000. If those ports are occupied, set `WEB_HOST_PORT`, `API_HOST_PORT`, `NEXT_PUBLIC_API_URL`, and `CORS_ORIGINS` consistently in `.env`. This checkout currently uses 3001 and 8001. After setting Supabase values, rebuild with `docker compose up --build -d`. Open the app at `http://localhost:3001`, API health at `http://localhost:8001/health`, and OpenAPI at `http://localhost:8001/docs`.

If the browser still shows `TV-KBU-0042`, animals tagged `KBU-021`–`KBU-024`, or an API documentation link on port 8000, it is using an older frontend/API build. The public API URL and auth mode are compiled into the frontend image. Rebuild both services from this repository root with `docker compose --env-file .env -f .\docker-compose.yml up --build -d api web`, then hard-refresh the browser. This keeps the PostgreSQL volume; do not add `--volumes` when rebuilding. With Supabase settings blank, the rebuilt app should show the unconfigured sign-in screen and no farm records.

Farmer registration creates a Supabase identity and provisions a farmer-only Terravanta account after Supabase confirms the account email. The account opens to an empty private workspace and the farmer enters their own farm details. Veterinarian and cooperative access are never selectable at sign-up; those roles require trusted operator provisioning and are not yet self-service invitations.

### Provision a pilot cooperative or veterinarian

For a pilot, send the staff invitation from the dedicated Supabase Auth dashboard, then provision the accepted identity inside the trusted API container. This command writes role and membership records directly; it is not exposed as an internet endpoint and does not need a service-role key.

```powershell
# Run from the repository root. Create a cooperative and copy the returned organization UUID.
docker compose exec api python -m app.operator create-cooperative --name "Example Dairy Cooperative"

# Copy the staff Supabase user UUID from the dedicated Auth dashboard after the invite is accepted.
# Cooperative administrators must be linked to their organization.
docker compose exec api python -m app.operator provision-user --supabase-user-id "<SUPABASE_USER_UUID>" --name "Cooperative Admin" --email "admin@example.org" --role cooperative_admin --organization-id "<ORGANIZATION_UUID>"

# Veterinarians must be assigned to a farm before they can review its cases.
docker compose exec api python -m app.operator provision-user --supabase-user-id "<SUPABASE_USER_UUID>" --name "Veterinarian" --email "vet@example.org" --role veterinarian --farm-id "<FARM_UUID>"
```

The operator command rejects identity/email mismatches, farmer role escalation and invalid organization/farm assignments. The farmer's traceability screen can grant a delivery-summary consent directly to a cooperative administrator's confirmed email; the cooperative API returns only that consented scope.

To stop the app while retaining its local database and uploads:

```powershell
docker compose down
```

To delete the local database volume and its records:

```powershell
docker compose down --volumes
```

## Real account onboarding

Email/password sign-up and sign-in use Supabase Auth. Enable email confirmation in the Supabase project and add the local app URL to the project's redirect allowlist. After sign-in, the API validates the JWT and checks the provider's current user profile and confirmed-email timestamp before creating a Terravanta farmer profile with the `farmer` role. It ignores role claims from user metadata. A new farmer has no farm membership until they register a farm. Existing veterinarian/cooperative accounts retain their server-assigned roles.

The Supabase URL and publishable anon key are public client settings. The backend uses the same anon key only to validate tokens when the Supabase project has legacy shared-secret signing; otherwise it validates against the project's JWKS. **Never put a Supabase service-role key in frontend variables or this repository.** Refresh tokens are kept in an HttpOnly cookie; access tokens remain in memory. Demo login and seed records are off by default. To explicitly enable the fictional demo, set both `NEXT_PUBLIC_AUTH_MODE=demo` and `ENABLE_SYNTHETIC_DATA=true`, then rebuild.

## NVIDIA configuration

Ordinary farm records work without NVIDIA credentials. The veterinary assistant uses a backend-only NVIDIA Build chat adapter and defaults to `nvidia/nemotron-3.5-lightning-30b-a3b`. Set `NVIDIA_API_KEY` and, if needed, `NVIDIA_BASE_URL` / `NVIDIA_CHAT_MODEL` in `.env`; the caller must also opt into external processing for that request. The provider model ID is configurable and must be rechecked against the NVIDIA account before deployment.

Selectable PDF text extraction is local. Image document extraction requires explicit user consent and a reachable native Nemotron Parse NIM endpoint configured in `NVIDIA_PARSE_URL`; provide `NVIDIA_PARSE_API_KEY` only if that endpoint requires it. The parsed text is mapped into structured fields through the chat model only when `NVIDIA_API_KEY` is configured. `NVIDIA_PARSE_MODEL` records the configured model identity; the native Parse endpoint URL controls the service call. Drafts always need human review and are never written directly into official records.

No NVIDIA call is fabricated when credentials or endpoints are missing. Do not send real clinical or farm data to an external endpoint until the account terms, data handling, retention, access and consent are approved. **Any API keys pasted into the original build prompt should be treated as exposed and rotated; they are not used here.**

## Run without Docker

Use Python 3.12+ and Node.js 22+.

```powershell
# terminal 1 — API
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:DATABASE_URL = "sqlite:///./terravanta.db"
uvicorn app.main:app --reload --port 8000

# terminal 2 — frontend
cd apps/web
npm ci
npm run dev
```

The API creates local SQLite tables on first startup and does not seed records by default. Set `ENABLE_SYNTHETIC_DATA=true` only when you intentionally want the fictional demo dataset. SQLite does not provide PostGIS; use Compose/PostGIS for geospatial storage. Never enable synthetic data in production.

## Verification commands

From `apps/api`:

```powershell
pip install -r requirements-dev.txt
pytest -q
```

From `apps/web`:

```powershell
npm ci
npm run lint
npm test
npm run build
```

The API workflow tests use an isolated in-memory SQLite database. Frontend tests cover IndexedDB offline capture and account-scoped replay. Docker Compose can be syntax-checked without starting the engine using `docker compose --env-file .env.example config --quiet`.

## Deploy next

1. Run the field discovery and pilot design in [GO_TO_MARKET.md](docs/GO_TO_MARKET.md); the wedge and numeric pilot gates are hypotheses, not demonstrated PMF.
2. Provision managed PostgreSQL with PostGIS, private S3-compatible object storage, Supabase Auth, monitoring, backups and restore testing.
3. Configure the dedicated Terravanta Supabase project, email verification, redirect allowlist, account recovery, rate limits and privacy notices. Farmer registration is self-service; veterinarian and cooperative invitations still require an operator workflow.
4. Set API secrets and production config in a secret manager. Set explicit CORS origins and Supabase frontend build variables; keep `ENABLE_SYNTHETIC_DATA=false`.
5. Build and deploy API/web containers with private database access and HTTPS. The API image applies Alembic migrations before server start. Confirm backup/restore, file limits and health checks.
6. Rotate any credentials exposed in the original prompt. Configure NVIDIA credentials only after reviewing current endpoint/model availability, account terms and data handling. Test against a veterinarian-reviewed evaluation set before enabling it for a pilot.
7. Onboard pilot farms with informed consent and verified source records. Existing local database volumes may retain synthetic rows from earlier development; they are not automatically deleted and must be separately reviewed before any real-data deployment.

### CI and production release

The GitHub workflow runs API tests, web typechecks/tests and an optimized frontend build on pushes and pull requests to `main`. The production release remains gated until `PRODUCTION_DEPLOY_ENABLED=true` is configured and the production GitHub environment secrets are present. It publishes commit-tagged images to GHCR, deploys to a Linux Docker VPS behind Caddy HTTPS, and waits for service health checks. It never places a database password, NVIDIA key or Supabase service-role key in the browser build.

Follow [CI/CD and production deployment](docs/DEPLOYMENT.md) for the VPS prerequisites, exact GitHub variables and secrets, first-host setup, and rollback guidance. The provided VPS setup persists Postgres and uploads locally; configure encrypted off-host backups and a tested restore before storing pilot farm records.

To validate production Compose syntax locally, from the repository root run:

```powershell
docker compose --env-file .env.production.example -f docker-compose.production.yml config --quiet
```

## Technical stack

Next.js 16 / React 19 / TypeScript, Tailwind CSS, Recharts; FastAPI / Pydantic / SQLAlchemy / Alembic; PostgreSQL + PostGIS; Supabase Auth JWT validation; Docker Compose; NVIDIA provider abstraction.
