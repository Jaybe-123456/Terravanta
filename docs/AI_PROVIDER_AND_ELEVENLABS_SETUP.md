# Terravanta AI providers and ElevenLabs media

This guide separates live product inference from one-time video production. AI credentials stay on the API or in a local generation shell; none belong in the browser bundle.

## NVIDIA for Terravanta review drafts

Set these on the **Render API service**. The browser calls the Terravanta API; it never receives a provider key.

| Variable | Value |
| --- | --- |
| `NVIDIA_API_KEY` | A current NVIDIA API key with access to the chosen model |
| `NVIDIA_BASE_URL` | `https://integrate.api.nvidia.com/v1` for NVIDIA hosted inference |
| `NVIDIA_CHAT_MODEL` | `stg/nvidia/nemotron-3.5-bolt-e4b`, or a currently available chat model for the key |
| `AI_TIMEOUT_SECONDS` | `35` |

This enables the consent-gated farm and veterinary draft routes. Each request still needs the user's external-processing consent, and a person reviews the draft. Setting these variables proves configuration only; it does not establish successful authentication, quota, or a live response. After redeploying the API, use the provider status panel and make one consented, non-sensitive test request.

Image document parsing uses NVIDIA's hosted Nemotron Parse API. Set these on the same Render API service:

| Variable | Value |
| --- | --- |
| `NVIDIA_PARSE_URL` | Optional override; default endpoint is `https://ai.api.nvidia.com/v1/retrieval/nvidia/nemotron-3.5-parse/parse` |
| `NVIDIA_PARSE_API_KEY` | Optional separate bearer key; if blank, the API reuses `NVIDIA_API_KEY` |
| `NVIDIA_PARSE_MODEL` | `nvidia/nemotron-3.5-parse` |

Image uploads remain opt-in; selectable-text PDF extraction stays local. The hosted Parse API is a separate call from chat completions, but can use the same NVIDIA key. Keep these NVIDIA values out of Vercel.

## ElevenLabs soundtrack for the product video

The soundtrack is generated during media production and bundled into the MP4. It is not a runtime Terravanta provider, so **do not put an ElevenLabs key in Render or Vercel**.

The current 52-second instrumental bed was generated with ElevenLabs Music v2.5 through the hosted OAuth MCP and saved at `media/terravanta-platform-overview/assets/music/terravanta-platform-bed.mp3`. The HyperFrames timeline now includes it as a quiet background track with fade-in and fade-out. It is bundled into the final MP4; Terravanta production users do not need an ElevenLabs connection.

The repository also contains `media/terravanta-platform-overview/scripts/generate-music.mjs` for a future direct API workflow. It calls the documented `POST https://api.elevenlabs.io/v1/music` endpoint, requests a 52-second MP3 and C2PA provenance signing, then attaches the track. Use that script only with a newly rotated ElevenLabs API key; it reads the key from the local process environment and never writes it into the project.

Use a newly rotated ElevenLabs API key. The key previously shared in chat should be revoked. In PowerShell, paste the new key into the hidden secure prompt below; it is held only in the current shell process, then cleared:

```powershell
$secure = Read-Host "Paste the newly rotated ElevenLabs API key" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $env:ELEVENLABS_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  node .\media\terravanta-platform-overview\scripts\generate-music.mjs
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  $secure.Dispose()
  Remove-Item Env:ELEVENLABS_API_KEY -ErrorAction SilentlyContinue
}
```

Run from the repository root. The script fails without changing the timeline when the key is missing, rejected, or the service returns a non-audio response. Music generation uses the ElevenLabs workspace's API access and credits.

## ElevenLabs hosted MCP in Codex

The hosted ElevenLabs MCP is a remote OAuth service for creative work such as music generation. It is not the MCP server that Terravanta exposes to its own users. It is already registered in the user's global Codex configuration and the OAuth flow completed successfully. To repeat the setup on another workstation:

```powershell
codex mcp add elevenlabs --url https://api.elevenlabs.io/v1/mcp
codex mcp login elevenlabs
codex mcp list
```

Complete the ElevenLabs OAuth flow to authorize the intended ElevenLabs account. The MCP uses that account's credits without copying an API key into Codex. Restart Codex if the server does not appear in a new chat. The direct API script above is available when a future export is needed in the project tree.

## Production boundaries

- Supabase stays responsible for sign-in and browser sessions.
- Render FastAPI stays responsible for farm-scoped access, consent checks and NVIDIA calls.
- PostgreSQL remains the system of record; AI output remains a human-reviewed draft.
- The soundtrack is a static media artifact in the frontend; ElevenLabs is not called by production users.
- Leave every WhatsApp/Meta variable unchanged while the business domain and phone onboarding are incomplete.
