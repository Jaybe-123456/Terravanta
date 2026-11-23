# Terravanta platform overview narration draft

No narration is included in this review render. This script is for the founder's own recording only; do not synthesize or clone a voice.

1. Vercel serves the Terravanta web workspace. Supabase Auth signs users in; the FastAPI service on Render checks access and works with PostgreSQL and PostGIS. Cooperative and processor data comes in through source-file imports. Optional AI and WhatsApp remain separate connections.
2. Farm work spans livestock, crops, feed, production and cooperative records. Entries keep their source.
3. Farmers record what happened on the farm and where production came from.
4. A health event can move into an assigned veterinary queue, with a follow-up date and outcome recorded by a person.
5. A farmer signs in on the web, gives consent and pairs a phone once. Then a coded text from the linked WhatsApp number can join the veterinary request; the signed webhook routes it, and opted-in replies are queued back. No separate Terravanta mobile download is needed. Live delivery requires Meta business approval and a verified phone number. The workflow handles text, not attachments.
6. Cooperatives can import a close, match records and review exceptions with an attributable trail. The workflow does not make payments.
7. A processor claim keeps the cooperative's assertion, the processor's response, the reviewed due-date basis and evidence together.
8. Terras helps people find workflows. Optional AI drafts require provider configuration and explicit consent; people remain responsible for decisions. Measure one authorized pilot before promising impact.
