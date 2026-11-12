"""Thin Gemini JSON wrapper. No key / any error => caller-supplied deterministic fallback."""
import json
import logging
import re

import httpx

from .config import settings

log = logging.getLogger("llm")


def available() -> bool:
    return bool(settings.gemini_api_key)


def _parse(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def chat_json(system: str, prompt: str, fallback: dict | None = None, temperature: float = 0.4) -> dict:
    fb = fallback if fallback is not None else {}
    if not available():
        return fb
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    try:
        r = httpx.post(url, headers={"x-goog-api-key": settings.gemini_api_key}, json=body, timeout=40)
        r.raise_for_status()
        out = _parse(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        return out if isinstance(out, dict) else fb
    except Exception as e:  # noqa: BLE001
        log.warning("LLM call failed, using fallback: %s", e)
        return fb
