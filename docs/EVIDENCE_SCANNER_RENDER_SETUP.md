# Private ClamAV scanner on Render

**Status:** not deployed. Evidence uploads remain fail-closed until the API can reach a scanner. This guide uses the Render Dashboard; it does not require a Blueprint or change the production database.

## Free-plan constraint

Render Free web services can send requests over the private network but cannot receive them. Private services do not have a free compute plan. A Render Free API therefore cannot receive ClamAV traffic from another Free web service, but it can send traffic to a paid Private Service in the same workspace and region. See [Render free-plan limits](https://render.com/docs/free), [Render private services](https://render.com/docs/private-services), and [Render private networking](https://render.com/docs/private-network).

ClamAV's standard signature database has a recommended minimum of 3 GiB RAM, with 3–4 GiB suggested for Docker, plus 5 GiB of free disk. The current Render `2c-4g` plan provides 4 GB RAM and is listed at about US$85/month; a 5 GB persistent disk adds about US$1.25/month at the listed per-GB rate. Check the Render Dashboard price before creating anything. See [ClamAV requirements](https://docs.clamav.net/) and [Render pricing](https://render.com/pricing).

If that cost is not acceptable, keep `EVIDENCE_SCANNER_HOST` blank. Uploads will continue to be rejected safely; do not point the API at a public TCP scanner or disable scanning to make uploads work.

## Create the private service

1. In Render, click **New + → Private Service**. Under **Source Code**, choose **Existing Image** and enter `docker.io/clamav/clamav:1.5_base`. ClamAV's official image starts `clamd` and its signature updater; `1.5_base` is the current feature-release tag. Review the image tag before each planned update in the [ClamAV Docker guide](https://docs.clamav.net/manual/Installing/Docker.html).
2. Name it `terravanta-evidence-scanner`, choose **Singapore** to match the API, and select at least **2 CPU / 4 GB RAM (`2c-4g`)**. Confirm the displayed price before deploying.
3. Keep it a **Private Service**. Allow its `clamd` TCP listener on port `3310` only on Render's private network. Do not create a public web service, public URL, or internet-facing port mapping. ClamAV warns its TCP protocol has no transport authentication or encryption, so it must remain private.
4. Wait for the service logs to show that `freshclam` has downloaded signatures and `clamd` is ready on port `3310`. If you attach persistent storage, mount it at `/var/lib/clamav` for the signature database; use at least 5 GB and verify the image's expected permissions.
5. In the scanner service's **Connect → Internal** panel, copy its internal address. It should look like `some-hostname:3310`. Use only the hostname portion for the API environment variable; the API code supplies port `3310` separately.

## Connect the API

In the existing `terravanta-api` service, add or set:

| Variable | Value |
| --- | --- |
| `EVIDENCE_SCANNER_HOST` | The internal hostname from the scanner's Connect panel, without a scheme or port |
| `EVIDENCE_SCANNER_PORT` | `3310` |
| `EVIDENCE_SCANNER_TIMEOUT_SECONDS` | `8` |
| `EVIDENCE_RETENTION_PURGE_ENABLED` | Keep `false` |

Save the API environment changes and redeploy only the API. Keep WhatsApp, database, and authentication variables unchanged. The API sends the file to `clamd` before storing it. A missing scanner, connection failure, timeout, or invalid verdict rejects the upload.

Use a cooperative-approved test workspace and a harmless small CSV/PDF to verify the upload path. Do not use live financial evidence until the customer has approved the data, retention and backup plan. Do not test by sending real documents to a public malware-scanning site.

## Separate CI from Render deployment

The PostGIS migration/RLS workflow runs on a pull request to `main`. A PR check does not authorize or require merging. Keep the Render API's current Production database untouched until there is a reviewed migration plan and a verified backup/restore procedure.
