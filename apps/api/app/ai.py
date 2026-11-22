import asyncio
import json
import re
import time
from pathlib import Path

import httpx

from .config import settings


class NVIDIAProvider:
    """OpenAI-compatible NVIDIA Build adapter. All calls stay on the API server."""

    async def chat(self, messages: list[dict], *, model: str | None = None, max_tokens: int = 900) -> tuple[str, int]:
        if not settings.nvidia_api_key:
            raise RuntimeError("NVIDIA_API_KEY is not configured")
        started = time.perf_counter()
        url = settings.nvidia_base_url.rstrip("/") + "/chat/completions"
        payload = {"model": model or settings.nvidia_chat_model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens, "stream": False}
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
                    response = await client.post(url, headers={"Authorization": f"Bearer {settings.nvidia_api_key}", "Accept": "application/json"}, json=payload)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        await asyncio.sleep(0.4 * (attempt + 1))
                        continue
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return str(content), round((time.perf_counter() - started) * 1000)
            except Exception as exc:
                last_error = exc
                if attempt < 2 and isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                raise
        raise last_error or RuntimeError("NVIDIA request failed")

    async def parse_image(self, path: str, mime_type: str) -> tuple[str, int]:
        """Call the native Nemotron Parse NIM contract: multipart POST /v1/parse."""
        if not settings.nvidia_parse_url:
            raise RuntimeError("NVIDIA_PARSE_URL is not configured")
        if mime_type not in {"image/png", "image/jpeg"}:
            raise ValueError("Nemotron Parse accepts PNG or JPEG page images")
        started = time.perf_counter()
        headers = {"Accept": "application/json"}
        if settings.nvidia_parse_api_key:
            headers["Authorization"] = f"Bearer {settings.nvidia_parse_api_key}"
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with Path(path).open("rb") as document:
                    async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
                        response = await client.post(
                            settings.nvidia_parse_url,
                            headers=headers,
                            files={"document": (Path(path).name, document, mime_type)},
                        )
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        await asyncio.sleep(0.4 * (attempt + 1))
                        continue
                response.raise_for_status()
                content = response.json().get("content")
                if not isinstance(content, str):
                    raise RuntimeError("Nemotron Parse returned no content field")
                return content, round((time.perf_counter() - started) * 1000)
            except Exception as exc:
                last_error = exc
                if attempt < 2 and isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                raise
        raise last_error or RuntimeError("Nemotron Parse request failed")


def safe_case_response(text: str) -> bool:
    """Conservative guard: reject medication, dosage, or diagnostic instructions."""
    patterns = [
        r"\b\d+(?:\.\d+)?\s*(?:mg|ml|mL|g|kg)\s*/\s*kg\b",
        r"\b(?:dose|dosage)\s+(?:of|is|should|recommend)",
        r"\b(?:administer|prescribe|inject|give|treat with)\b.{0,80}\b(?:mg|ml|mL|antibiotic|drug|medicine|medication|ivermectin|oxytetracycline)\b",
        r"\b(?:diagnosed with|the diagnosis is|confirmed diagnosis)\b",
    ]
    return not any(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in patterns)


def safe_farm_response(text: str) -> bool:
    """Reject high-risk clinical, feed-rate, input-rate, and guaranteed-return instructions."""
    if not safe_case_response(text):
        return False
    patterns = [
        r"\b(?:feed|mix|apply|spray|dose|administer)\b.{0,100}\b\d+(?:\.\d+)?\s*(?:mg|ml|g|kg|lit(?:er|re)s?|l)\s*(?:/|per)\s*(?:cow|animal|head|day|acre|ha|hectare)\b",
        r"\b\d+(?:\.\d+)?\s*(?:mg|ml|g|kg|lit(?:er|re)s?|l)\s*(?:/|per)\s*(?:cow|animal|head|day|acre|ha|hectare)\b",
        r"\b(?:guaranteed?|guarantees?|will|certainly)\b.{0,80}\b(?:increase|improve|boost|raise)\b.{0,60}\b(?:yield|milk|production|profit|income|revenue|return)\b",
    ]
    return not any(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in patterns)


def parse_structured(text: str) -> tuple[dict, str]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        result = json.loads(cleaned)
        if not isinstance(result, dict):
            raise ValueError("Expected object")
        return result, str(result.get("extracted_text", ""))
    except (ValueError, json.JSONDecodeError):
        return {}, text


nvidia = NVIDIAProvider()
