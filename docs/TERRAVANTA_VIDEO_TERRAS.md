# Terravanta explainer and Terras

## Cooperative close explainer

The HyperFrames composition lives in `media/terravanta-explainer`. It tells one concrete story: import the collection, processor settlement, and farmer payout exports; compare member rows; review exceptions; record cooperative sign-off; export the statement pack. It does not imply that Terravanta initiates a payment or that live cooperative results exist. All member identifiers and visual rows in the film are illustrative and synthetic.

The project pins HyperFrames CLI `0.9.58` and uses local GSAP. It has no external media, network-loaded assets, or model-generated narration. `generate_asset.py` is prepared to produce first-party 3D export-stack artwork when Blender is installed; Blender is not available in this build environment, so the current composition uses a native SVG illustration. The narration script is in `media/terravanta-explainer/VOICEOVER_SCRIPT.md`; its audio is intentionally absent until the founder supplies a clean recording and a rotated ElevenLabs credential is stored outside the repository.

From the repository root, prepare and check the film:

```powershell
Set-Location media/terravanta-explainer
npm install
npm run check
npx --yes hyperframes@0.9.58 snapshot --at 3,9,15,21,27
```

The composition's scene frames were captured and reviewed with HyperFrames. On this Windows host, HyperFrames' native MP4 render could not start Chrome's headless process, and its pinned-browser download could not resolve `storage.googleapis.com`. The reviewed frames are kept in `assets/frames` so the silent preview can be reproduced without that browser install. After FFmpeg and FFprobe are available, assemble them into the dashboard asset:

```powershell
npm run render:reviewed
```

The rendered preview is H.264 at 1280×720, 24 fps, with slow scene movement, crossfades, no audio track, and synthetic-data framing. FFprobe verifies codec, dimensions, frame rate and duration. The dashboard video is embedded on the cooperative Close desk with controls and a poster image. Keep the rendered film in `apps/web/public/videos`; keep local tool binaries in the ignored `.tools` folder. Set `FFMPEG_PATH` and `FFPROBE_PATH` if binaries are installed elsewhere. The requested preview is silent until the founder's narration track is recorded and approved.

## Web deployment output

The Next.js app uses its standard `.next` build directory, which matches the Vercel output path seen in the deployment logs. In Vercel, keep the project root at `apps/web`, use `npm run build`, and leave the output directory on Next.js auto-detection (or `.next`). The web Dockerfile copies the same `.next` artifact into its runner image.

## Terras workflow guide

Terras currently uses a deterministic, role-scoped local router at `POST /api/v1/terras/route`. It does not call NVIDIA, transmit user text externally, or treat model output as authorization. It maps a cooperative payout-close request to the existing settlement-close workflow and can prepare a milk record draft for a farmer. The draft is saved only after the user reviews its quantity/date and confirms; the existing production API checks role and farm membership. Cooperative close intake still requires the three CSV exports, a human reviewer for exceptions, and an authorized approver. The router never executes an approval or payment.

Focused API assertions are in `apps/api/tests/test_terras.py`; `apps/api/tests/smoke_terras.py` runs the same critical paths in an API image without requiring pytest to be installed. CI runs the full test suite with `requirements-dev.txt`.

## Voice and secrets

The previously pasted ElevenLabs API key must be revoked before any voice work. Put a replacement in a server-side secret store or a local environment variable that is not committed. Use only the founder's clean, isolated recording; do not substitute another person's voice or synthesize narration before the founder provides and approves the source audio.
