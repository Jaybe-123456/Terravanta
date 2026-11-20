# Terravanta explainer and Terras

## Cooperative receivables explainer

The editable HyperFrames project lives in `media/terravanta-explainer`. Six timed sub-compositions tell one workflow: a remaining cooperative claim; manual PDF/CSV evidence intake; separate seller-asserted and processor-confirmed values; age from a user-reviewed due date; a role-attributed processor response; and a private evidence export. Figures and dates are explicitly synthetic. The film does not claim a real customer result, a live MIS connector, legal validation, payment movement or recovered funds. The export illustration shows original evidence, response history and an SHA-256 integrity manifest; a hash detects file changes but does not prove source truth.

The project uses local GSAP, the actual Terravanta leaf mark and no model-generated media. The composition is silent because the founder has not yet supplied a recording. A draft written for the founder's own voice is in `media/terravanta-explainer/VOICEOVER_SCRIPT.md`; the key previously pasted in chat must be revoked and is not used.

From the repository root, use the installed HyperFrames launcher with a project-local cache in PowerShell:

```powershell
Set-Location media/terravanta-explainer
$env:HYPERFRAMES_CACHE_DIR = Join-Path (Get-Location) '.tools\hyperframes-cache'
$env:npm_config_cache = Join-Path (Get-Location) '.tools\npm-cache'
$env:HYPERFRAMES_FFMPEG_PATH = Join-Path (Get-Location) '.tools\node_modules\ffmpeg-static\ffmpeg.exe'
$env:HYPERFRAMES_FFPROBE_PATH = Join-Path (Get-Location) '.tools\node_modules\ffprobe-static\bin\win32\x64\ffprobe.exe'
$hf = Join-Path $env:USERPROFILE '.agents\skills\hyperframes\scripts\plugin-cli.mjs'
node $hf check --json
node $hf snapshot --review
node $hf preview --background
node $hf preview --status --json
node $hf render --quality delivery --output '..\..\apps\web\public\videos\terravanta-receivables-assurance.mp4'
& $env:HYPERFRAMES_FFMPEG_PATH -y -ss 1 -i '..\..\apps\web\public\videos\terravanta-receivables-assurance.mp4' -frames:v 1 -update 1 '..\..\apps\web\public\videos\terravanta-receivables-assurance-poster.png'
```

The dashboard consumes `apps/web/public/videos/terravanta-receivables-assurance.mp4` and its matching poster. The player is embedded in cooperative, farmer, veterinarian and processor views so a user can discover the product explainer without changing roles. The cooperative overview, processor claims inbox and farmer/veterinarian overview pages show the film; cooperative users can also reach it from the claims workflow.

The Windows render used the installed HyperFrames 0.9.72 launcher with FFmpeg and FFprobe configured in the launching PowerShell session. Set `HYPERFRAMES_FFMPEG_PATH` and `HYPERFRAMES_FFPROBE_PATH` when those tools are not discoverable on `PATH`. The six reviewed scene snapshots can be assembled with `node render_from_reviewed_frames.mjs` only if the native renderer cannot encode.

## Web deployment output

The Next.js app uses its standard `.next` build directory. `apps/web/vercel.json` explicitly sets the Vercel output directory to `.next`, overriding a stale dashboard value of `build-output`. Keep the Vercel project root at `apps/web` and use `npm run build`; the web Dockerfile copies the same `.next` artifact into its runner image.

## Terras workflow guide

Terras currently uses a deterministic, role-scoped local router at `POST /api/v1/terras/route`. It does not call NVIDIA, transmit user text externally, or treat model output as authorization. It maps a cooperative payout-close request to the existing settlement-close workflow and can prepare a milk record draft for a farmer. The draft is saved only after the user reviews its quantity/date and confirms; the existing production API checks role and farm membership. Cooperative close intake still requires the three CSV exports, a human reviewer for exceptions, and an authorized approver. The router never executes an approval or payment.

Focused API assertions are in `apps/api/tests/test_terras.py`; `apps/api/tests/smoke_terras.py` runs the same critical paths in an API image without requiring pytest to be installed. CI runs the full test suite with `requirements-dev.txt`.

## Voice and secrets

The previously pasted ElevenLabs API key must be revoked before any voice work. Put a replacement in a server-side secret store or a local environment variable that is not committed. Use only the founder's clean, isolated recording; do not substitute another person's voice or synthesize narration before the founder provides and approves the source audio.
