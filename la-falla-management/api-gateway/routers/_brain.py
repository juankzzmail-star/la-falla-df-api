"""Gentil's deep brain — DeepSeek V4 Pro for strategic reasoning.

Gentil runs on two brains by design:

  * Fast brain (Groq Llama / OpenClaw): high-frequency, low-stakes generation where the
    heavy lifting is already done by deterministic code and the model only phrases the
    result — e.g. the daily reading (`dashboard.generate_daily_suggestions`) and the chat.

  * Deep brain (this module, DeepSeek V4 Pro): low-frequency, high-stakes STRATEGIC
    reasoning where quality beats speed/cost — risk analysis, the risk radar, strategic
    observations, the strategy cascade. Slower and paid, but it reasons instead of phrasing.

Keep this module provider-agnostic at the call site: routers import `deep_analysis()` and
`available()` and never touch the HTTP details. Switching model/provider is one env var.

Config (set in Easypanel on the api-gerencia service):
  DEEPSEEK_API_KEY  — required; without it `available()` is False and callers degrade honestly.
  DEEPSEEK_MODEL    — defaults to "deepseek-v4-pro" (the deep tier on api.deepseek.com).
  DEEPSEEK_URL      — defaults to the official OpenAI-compatible endpoint.
"""
import os
import json
import time

import requests
from fastapi import HTTPException

DEEPSEEK_URL   = os.environ.get("DEEPSEEK_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")


def available() -> bool:
    """True when the deep brain is configured. Callers use this to degrade honestly
    (placeholder text / 503) instead of fabricating analysis."""
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


def deep_analysis(system: str, prompt: str, max_tokens: int = 1200,
                  json_mode: bool = True, temperature: float = 0.3) -> str:
    """Call DeepSeek V4 Pro and return the raw assistant content (str).

    Raises HTTP 503 when the key is missing or the provider never answers — never silently
    returns empty, so the caller can surface an honest error. Retries transient failures
    with backoff. `json_mode` asks the provider for a JSON object; pair it with
    `parse_json()` which also tolerates markdown-fenced or prose-wrapped JSON.
    """
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise HTTPException(503, "DEEPSEEK_API_KEY no configurada — el cerebro profundo de Gentil no está disponible.")

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    last = ""
    for attempt in range(3):
        try:
            r = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=120)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"] or ""
            last = f"{r.status_code}: {r.text[:200]}"
        except requests.exceptions.RequestException as e:
            last = str(e)
        if attempt < 2:
            time.sleep(2 ** attempt)
    raise HTTPException(503, f"DeepSeek no respondió tras 3 intentos ({last}).")


def parse_json(raw: str):
    """Best-effort JSON parse of a model response.

    Accepts a clean JSON object/array, a ```json fenced block, or JSON embedded in prose.
    Returns the parsed value, or raises ValueError if nothing parseable is found.
    """
    if raw is None:
        raise ValueError("respuesta vacía")
    s = raw.strip()
    # strip a markdown fence if present
    if s.startswith("```"):
        body = s.split("```", 2)
        if len(body) >= 2:
            s = body[1]
            if s.lstrip().lower().startswith("json"):
                s = s.lstrip()[4:]
            s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # find the first {...} or [...] span
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = s.find(opener), s.rfind(closer)
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(s[i:j + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"sin JSON parseable en: {s[:160]}")
