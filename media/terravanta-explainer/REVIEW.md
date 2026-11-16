# Terravanta explainer review

## Creative decisions

The film follows one cooperative payout close from three source exports, through period matching and exception review, to cooperative sign-off and a measurable pilot invitation. It makes the service boundary visible: Terravanta prepares the review work; a named cooperative user decides exceptions and approves the close. It does not show a general farm product tour or a veterinary AI demo because those would dilute this first service wedge. The closing CTA asks for one anonymized, completed payout close and makes no performance claim.

## Measured and inspected

The source composition is 1920×1080 with a 30-second timeline. HyperFrames lint reported zero errors and six warnings; its layout analysis reported zero errors. The warnings describe the five scenes and nested markup living in one root composition, which makes Studio editing less granular. Phone and full-size HyperFrames review sheets were inspected, as were five rendered video scene samples. The story copy remains readable at phone width; example table labels are intentionally secondary details.

The final dashboard asset is H.264, 1280×720, 24 fps, 29.709 seconds and 1,547,033 bytes. FFprobe confirms the video stream and no audio stream. It was assembled from five reviewed HyperFrames snapshots with a restrained center zoom and crossfades because the native HyperFrames renderer's Chrome process crashes on this Windows host. The pinned browser install also failed because `storage.googleapis.com` did not resolve. HyperFrames' current runtime check consequently fails at browser startup; the previous snapshot images and the final MP4 were reviewed independently.

## Deliberate limitations

The film is silent. No voice recording was present in the workspace, and the ElevenLabs key previously pasted into chat must be rotated before it is used. The 3D Blender scene script is present, but Blender was unavailable; the current artwork is an authored SVG. Sound was not heard or evaluated because there is no soundtrack.

The weakest shot is the period-matching UI: its headline reads at phone width, but the small synthetic table details do not. With more time, make the matching interaction itself a separate, closer product shot. Before expanding the film, split scenes into editable sub-compositions and rerun HyperFrames' runtime review on a host whose Chrome headless process starts reliably.
