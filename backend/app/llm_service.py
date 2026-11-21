import logging
import time
import asyncio
import litellm

from . import config

logger = logging.getLogger("llm_service")

# LiteLLM's built-in in-memory cache. The key is built from model + full message list.
litellm.enable_cache(type="local")

VALID_STATUSES = {429, 500, 502, 503}


class AllProvidersUnavailable(Exception):
    """Raised when every key in the pool has failed."""


def parse_simulation(header_value: str | None) -> dict:
    """Parse 'key_1=429,key_2=500' or '*=429' into {'key_1': 429, ...}.
    Returns {} unless ENABLE_FAILURE_SIMULATION=true."""
    if not config.ENABLE_FAILURE_SIMULATION or not header_value:
        return {}
    result = {}
    for part in header_value.split(","):
        key, _, status = part.partition("=")
        key, status = key.strip(), status.strip()
        if key and status.isdigit() and int(status) in VALID_STATUSES:
            result[key] = int(status)
    return result


def build_messages(system_prompt: str, history: list[dict], user_message: str) -> list[dict]:
    """system prompt + stored history + new message (metadata stripped)."""
    messages = [{"role": "system", "content": system_prompt}]
    for m in history:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


async def get_reply(messages: list[dict], simulate: dict | None = None) -> dict:
    """Try each key in order. Returns {'reply': str, 'metadata': dict}.
    Raises AllProvidersUnavailable if every key fails."""
    simulate = simulate or {}
    start = time.perf_counter()
    failed = 0

    for index, api_key in enumerate(config.LLM_API_KEYS, start=1):
        key_id = f"key_{index}"

        # Failure simulation: this key "returns" the given status, for this request only
        status = simulate.get(key_id) or simulate.get("*")
        if status:
            logger.warning("%s: simulated failure %s", key_id, status)
            failed += 1
            continue

        extra = {}
        if simulate:
            # While simulating, skip the cache read so a real key answers (key_id = key_2)
            extra["cache"] = {"no-cache": True}

        try:
            response = await asyncio.to_thread(
                litellm.completion,
                model=config.LLM_MODEL,
                messages=messages,
                api_key=api_key,
                num_retries=0,  # we do the failover ourselves, no slow internal retries
                timeout=30,
                caching=True,
                **extra,
            )
            text = response.choices[0].message.content
            if not text or not text.strip():
                raise ValueError("empty reply")
        except Exception as exc:  # 429, quota, 5xx, bad key, timeout, empty reply...
            logger.warning("%s failed: %s: %s", key_id, type(exc).__name__, str(exc)[:300])
            failed += 1
            continue

        cache_hit = bool((getattr(response, "_hidden_params", None) or {}).get("cache_hit"))
        usage = response.usage
        latency_ms = int((time.perf_counter() - start) * 1000)

        return {
            "reply": text,
            "metadata": {
                "resolution_source": "LLM_CACHE" if cache_hit else "LIVE_INFERENCE",
                "model": config.LLM_MODEL,
                "latency_ms": latency_ms,
                "input_tokens": int(usage.prompt_tokens or 0),
                "output_tokens": int(usage.completion_tokens or 0),
                "key_id": None if cache_hit else key_id,
                "fallback_attempts": 0 if cache_hit else failed,
            },
        }

    raise AllProvidersUnavailable("all providers unavailable")