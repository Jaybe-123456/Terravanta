import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const apiKey = process.env.ELEVENLABS_API_KEY?.trim();
const model = process.env.ELEVENLABS_MUSIC_MODEL?.trim() || "music_v2_5";
const outputPath = path.join(projectRoot, "assets", "music", "terravanta-platform-bed.mp3");
const indexPath = path.join(projectRoot, "index.html");
const marker = "<!-- The local ElevenLabs soundtrack script replaces this marker after music is generated. -->";

if (!apiKey) {
  throw new Error("ELEVENLABS_API_KEY is missing. Use a newly rotated key in this local shell only.");
}
if (!["music_v1", "music_v2", "music_v2_5"].includes(model)) {
  throw new Error("ELEVENLABS_MUSIC_MODEL must be music_v1, music_v2, or music_v2_5.");
}

const prompt = [
  "52-second instrumental underscore for a premium farm intelligence product film in Kenya.",
  "Warm, confident, human and forward-moving; understated, polished and suitable beneath product narration added later.",
  "Soft plucked acoustic strings with a gentle marimba-like texture, restrained hand percussion, a light pulse and airy pads.",
  "Build subtly, stay even and resolve softly at the end. No vocals, no lyrics, no dramatic trailer hits, no abrupt transitions.",
].join(" ");

const endpoint = new URL("https://api.elevenlabs.io/v1/music");
endpoint.searchParams.set("output_format", "mp3_48000_192");

const response = await fetch(endpoint, {
  method: "POST",
  headers: {
    "xi-api-key": apiKey,
    "content-type": "application/json",
    accept: "audio/mpeg",
  },
  body: JSON.stringify({
    prompt,
    music_length_ms: 52_000,
    model_id: model,
    force_instrumental: true,
    sign_with_c2pa: true,
  }),
  signal: AbortSignal.timeout(180_000),
});

if (!response.ok) {
  throw new Error(`ElevenLabs music generation failed with HTTP ${response.status}. Check key permissions, account access, and credits in ElevenLabs.`);
}

const contentType = response.headers.get("content-type") || "";
if (!contentType.toLowerCase().startsWith("audio/")) {
  throw new Error(`ElevenLabs returned an unexpected content type (${contentType || "missing"}); no soundtrack was installed.`);
}

const audio = Buffer.from(await response.arrayBuffer());
if (audio.length < 20_000) {
  throw new Error("ElevenLabs returned an unexpectedly small audio file; no soundtrack was installed.");
}

const html = await readFile(indexPath, "utf8");
const audioTag = '<audio id="terravanta-music" src="./assets/music/terravanta-platform-bed.mp3" data-composition-id="terravanta-music" data-start="0" data-duration="52" data-track-index="1" data-track-kind="audio" data-volume="0.12" data-fade-in="1.5" data-fade-out="3"></audio>';
let nextHtml;
if (html.includes('id="terravanta-music"')) {
  nextHtml = html.replace(/<audio id="terravanta-music"[^>]*><\/audio>/, audioTag);
} else if (html.includes(marker)) {
  nextHtml = html.replace(marker, `${audioTag}\n    ${marker}`);
} else {
  throw new Error("The expected soundtrack insertion point is missing from index.html; the project was left unchanged.");
}

await mkdir(path.dirname(outputPath), { recursive: true });
const tempPath = `${outputPath}.tmp`;
await writeFile(tempPath, audio);
await rename(tempPath, outputPath);
await writeFile(indexPath, nextHtml, "utf8");

console.log(`Generated and attached the instrumental soundtrack: ${path.relative(projectRoot, outputPath)}`);
console.log(`Model: ${model}; duration requested: 52 seconds; request id: ${response.headers.get("song-id") || "not returned"}`);
