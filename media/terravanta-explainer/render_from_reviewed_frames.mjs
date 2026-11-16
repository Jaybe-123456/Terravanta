import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectDir = fileURLToPath(new URL(".", import.meta.url));
const repositoryDir = resolve(projectDir, "../..");
const framesDir = resolve(projectDir, "assets/frames");
const outputDir = resolve(repositoryDir, "apps/web/public/videos");
const outputFile = resolve(outputDir, "terravanta-payout-close.mp4");
const posterFile = resolve(outputDir, "terravanta-payout-close-poster.png");
const ffmpegPath = process.env.FFMPEG_PATH ?? resolve(projectDir, ".tools/node_modules/ffmpeg-static/ffmpeg.exe");
const ffprobePath = process.env.FFPROBE_PATH ?? resolve(projectDir, ".tools/node_modules/ffprobe-static/bin/win32/x64/ffprobe.exe");
const sceneFiles = ["scene-01-source-files.png", "scene-02-match-period.png", "scene-03-human-review.png", "scene-04-sign-off.png", "scene-05-pilot-close.png"]
  .map((name) => resolve(framesDir, name));

if (!existsSync(ffmpegPath)) throw new Error(`FFmpeg not found at ${ffmpegPath}. Set FFMPEG_PATH to its executable.`);
for (const sceneFile of sceneFiles) {
  if (!existsSync(sceneFile)) throw new Error(`Reviewed HyperFrames snapshot is missing: ${sceneFile}`);
}

mkdirSync(outputDir, { recursive: true });

const fps = 24;
const clipDuration = 154 / fps;
const transitionDuration = 0.6;
const sceneFrames = 5;
const inputs = sceneFiles.flatMap((sceneFile) => ["-loop", "1", "-framerate", String(fps), "-t", String(clipDuration), "-i", sceneFile]);
const filters = sceneFiles.map((_, index) =>
  `[${index}:v]scale=1920:1080,zoompan=z='min(1.02,1+on*0.0001)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1280x720:fps=${fps},trim=duration=${clipDuration},settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[v${index}]`
);

let previous = "v0";
for (let index = 1; index < sceneFrames; index += 1) {
  const output = `xf${index}`;
  const offset = (index * clipDuration) - (index * transitionDuration);
  filters.push(`[${previous}][v${index}]xfade=transition=fade:duration=${transitionDuration}:offset=${offset.toFixed(6)}[${output}]`);
  previous = output;
}

const duration = (sceneFrames * clipDuration) - ((sceneFrames - 1) * transitionDuration);
filters.push(`[${previous}]fade=t=in:st=0:d=0.4,fade=t=out:st=${(duration - 0.4).toFixed(6)}:d=0.4,format=yuv420p[outv]`);

const args = [
  "-hide_banner", "-y", ...inputs,
  "-filter_complex", filters.join(";"),
  "-map", "[outv]", "-an", "-r", String(fps),
  "-c:v", "libx264", "-preset", "medium", "-crf", "22",
  "-profile:v", "high", "-level", "4.0", "-pix_fmt", "yuv420p",
  "-movflags", "+faststart",
  "-metadata", "title=Terravanta cooperative payout close",
  "-metadata", "comment=Silent illustrative preview. All displayed records are synthetic.",
  outputFile,
];

console.log(`Rendering ${sceneFiles.length} reviewed HyperFrames scenes at ${fps} fps to ${outputFile}`);
const result = spawnSync(ffmpegPath, args, { stdio: "inherit", windowsHide: true });
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status ?? 1);

const poster = spawnSync(ffmpegPath, [
  "-hide_banner", "-y", "-i", sceneFiles.at(-1), "-frames:v", "1", "-update", "1", posterFile,
], { stdio: "inherit", windowsHide: true });
if (poster.error) throw poster.error;
if (poster.status !== 0) process.exit(poster.status ?? 1);

if (existsSync(ffprobePath)) {
  const probe = spawnSync(ffprobePath, [
    "-v", "error", "-show_entries", "format=duration,size:stream=codec_name,width,height,r_frame_rate,pix_fmt",
    "-of", "json", outputFile,
  ], { encoding: "utf8", windowsHide: true });
  if (probe.error) throw probe.error;
  if (probe.status !== 0) throw new Error(probe.stderr || "FFprobe failed to validate the MP4.");
  console.log("Video verification:");
  console.log(probe.stdout.trim());
} else {
  console.warn(`FFprobe not found at ${ffprobePath}; skipped metadata verification.`);
}
