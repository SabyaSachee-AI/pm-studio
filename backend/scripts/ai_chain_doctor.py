"""AI chain doctor — show which free-tier providers actually contribute.

For a given task_type (default: code_generate) this prints every model in the
fallback chain and, for each, whether its provider has an API key configured
(env or per-org Admin → AI config) and whether it is currently cooling down.

A model whose provider has NO key is silently skipped at runtime, so a chain
that *looks* 20 models deep may really be running only 2-3. This surfaces that
gap so you can add the missing keys.

Run on the VPS:
    docker compose -f docker-compose.contabo.yml exec backend \
        python -m scripts.ai_chain_doctor code_generate
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.core.database import SyncSessionLocal
from app.models.organization import Organization
from app.services.ai.providers import FREE_ROUTING
from app.services.ai.router import AiRouter, _OPENAI_COMPAT_INSTRUCTOR_MODES


def _chain(task_type: str) -> list[tuple[str, str]]:
    entry = FREE_ROUTING.get(task_type)
    if not entry:
        raise SystemExit(f"Unknown task_type '{task_type}'. Known: {', '.join(sorted(FREE_ROUTING))}")
    out: list[tuple[str, str]] = []
    idx = 1
    while True:
        pair = entry.get(f"model_{idx}")  # type: ignore[assignment]
        if not pair:
            break
        out.append(tuple(pair))  # type: ignore[arg-type]
        idx += 1
    return out


def _is_cooling_sync(provider: str, model: str) -> bool:
    try:
        import redis  # type: ignore[import]

        from app.core.config import get_settings

        r = redis.from_url(get_settings().redis_url, decode_responses=True)
        return bool(r.exists(f"ai_cooldown:{provider}") or r.exists(f"ai_cooldown:{provider}:{model}"))
    except Exception:
        return False


def main() -> None:
    task_type = sys.argv[1] if len(sys.argv) > 1 else "code_generate"
    chain = _chain(task_type)
    router = AiRouter()

    db = SyncSessionLocal()
    try:
        org = db.execute(select(Organization).limit(1)).scalar_one_or_none()
    finally:
        db.close()
    if org is None:
        raise SystemExit("No organization found — cannot resolve per-org keys.")

    print(f"\nAI chain doctor — task_type = {task_type}")
    print(f"Organization: {org.name} ({org.id})")
    print(f"Chain length: {len(chain)} models\n")
    print(f"{'#':>2}  {'PROVIDER':<12} {'MODEL':<42} {'KEY':<8} {'STATUS'}")
    print("-" * 82)

    provider_live: dict[str, bool] = {}
    live_models = 0
    for i, (provider, model) in enumerate(chain, start=1):
        has_key = router._get_api_key(provider, org) is not None
        supported = provider == "anthropic" or provider in _OPENAI_COMPAT_INSTRUCTOR_MODES
        provider_live.setdefault(provider, has_key and supported)
        if has_key and supported:
            cooling = _is_cooling_sync(provider, model)
            status = "cooling" if cooling else "READY"
            if not cooling:
                live_models += 1
        elif not supported:
            status = "unsupported"
        else:
            status = "NO KEY -> skipped"
        key_col = "yes" if has_key else "--"
        print(f"{i:>2}  {provider:<12} {model[:42]:<42} {key_col:<8} {status}")

    print("-" * 82)
    live = sorted(p for p, ok in provider_live.items() if ok)
    dead = sorted(p for p, ok in provider_live.items() if not ok)
    print(f"\nLive providers ({len(live)}): {', '.join(live) or 'NONE'}")
    print(f"Missing/skipped ({len(dead)}): {', '.join(dead) or 'none'}")
    print(f"Models actually usable right now: {live_models}/{len(chain)}")
    if live_models <= 2:
        print(
            "\n⚠  Only a couple of models are usable — when their free quota runs out "
            "the whole chain stalls. Add keys for the missing providers above "
            "(Admin -> AI config, or the *_API_KEY env vars) to make the chain truly deep."
        )


if __name__ == "__main__":
    main()
