# Final video review

## Render artifact

- HyperFrames 0.9.85, local delivery render using installed Chrome, screenshot capture, hardware GPU, and one worker.
- H.264 MP4, 1920 × 1080, 30 fps, 52.022 seconds, 3,469,708 bytes. Artifact validation passed for all 1,560 frames.
- The 52-second instrumental bed was generated with ElevenLabs Music v2.5 through the hosted OAuth MCP and mixed into the video as AAC stereo at low volume with short fades. The exported video was copied to `apps/web/public/videos/terravanta-platform-overview.mp4`; its poster is a decoded frame at 4 seconds. Narration remains out until the founder supplies and approves a voice recording.

## Visual review

All eight scenes were reviewed in HyperFrames snapshots, and decoded frames from the final MP4 at 28 and 42 seconds were inspected locally. Generated snapshots, thumbnails, and render intermediates are excluded from source control; the editable compositions and final frontend MP4 are included.

- The opening map identifies Vercel as text and uses the Render, FastAPI and Supabase marks. It shows signed-in identity flowing to API access, API-managed database access, optional model service, WhatsApp text routing, and manual cooperative/processor file imports.
- Farmer records, production capture, veterinary follow-up dates/outcomes, settlement-close exceptions, processor claim evidence and the Terras/AI review boundary remain legible in the sampled frames.
- WhatsApp is shown as an illustrative consent-based workflow: web sign-in, one-time phone pairing, request-code text, signed webhook routing and queued replies. It claims no separate Terravanta mobile app install is needed, while still requiring web access and a linked number. Live delivery still needs Meta business approval, a verified phone and an enabled webhook. Text only; no images or documents.
- NVIDIA is optional and server-configured; results remain drafts for human review. No customer logos, live partner claims, testimonials, financial results, or clinical/productivity outcomes are shown.
- No sampled frame showed visible clipping or an unintended overlap at the review-sheet scale.

## Build verification

The HyperFrames check passed with no errors or contrast warnings. `npm.cmd run build` in `apps/web` completed successfully after the updated MP4 and poster were installed. The first sandboxed attempt was denied permission to create a prerender folder; the workspace-authorized retry completed all 11 static pages.

No Meta/WhatsApp settings, Render credentials, external AI credentials, or deployment settings were changed.
