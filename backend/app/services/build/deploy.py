"""Stage 7 — deploy a generated build to the VPS via a GitHub Actions workflow.

PM Studio sets the VPS secrets on the repo (if PyNaCl is available) and triggers
the repo's ``deploy.yml`` (workflow_dispatch), which SSHes into the VPS and runs
``git pull && docker compose up -d --build``.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.models.build import Build

logger = logging.getLogger(__name__)

_REQUIRED = ("host", "user", "ssh_key", "path")
_SECRET_MAP = {"host": "VPS_HOST", "user": "VPS_USER", "ssh_key": "VPS_SSH_KEY", "path": "VPS_PATH"}


def _vps_config(db: Any) -> dict[str, str]:
    """VPS deploy config from org settings (Admin → AI config). SSH key decrypted."""
    from app.core.crypto import decrypt_secret  # noqa: PLC0415
    from app.models.organization import Organization  # noqa: PLC0415
    org = db.query(Organization).first()
    cfg = dict((org.ai_provider_configs or {}).get("vps_deploy") or {}) if org else {}
    if cfg.get("ssh_key"):
        cfg["ssh_key"] = decrypt_secret(cfg["ssh_key"])
    return cfg


async def deploy_build(build_id: UUID, db: Any, port: int | None = None) -> dict[str, Any]:
    from app.services.build.github import _db_creds, set_repo_secret, trigger_workflow  # noqa: PLC0415

    build = db.query(Build).filter(Build.id == build_id).first()
    if not build:
        return {"error": "Build not found"}
    if not build.github_full_name:
        return {"error": "Push the build to GitHub first"}

    cfg = _vps_config(db)
    missing = [k for k in _REQUIRED if not cfg.get(k)]
    if missing:
        return {"error": f"VPS not configured. Set {', '.join(missing)} in Admin → AI config (VPS deploy)."}

    full = build.github_full_name
    branch = build.default_branch or "main"

    # Per-app web port (avoids clashes on a shared VPS). Persist for reference.
    report = dict(build.quality_report or {})
    chosen_port = port or (report.get("deploy") or {}).get("port") or 3000

    # Build an authenticated clone URL so the (private) repo can be cloned/pulled
    # on the VPS without a manual one-time clone.
    token, _ = _db_creds()
    repo_token_url = f"https://{token}@github.com/{full}.git" if token else ""

    secrets = dict(_SECRET_MAP)  # host/user/ssh_key/path
    values = {name: str(cfg[key]) for key, name in secrets.items()}
    values["REPO_TOKEN_URL"] = repo_token_url
    values["APP_PORT"] = str(chosen_port)

    auto_set: list[str] = []
    manual: list[str] = []
    for secret_name, secret_value in values.items():
        if not secret_value:
            continue
        ok = await set_repo_secret(full, secret_name, secret_value)
        (auto_set if ok else manual).append(secret_name)

    dispatched = await trigger_workflow(full, "deploy.yml", branch)

    report["deploy"] = {
        "dispatched": dispatched,
        "secrets_auto_set": auto_set,
        "secrets_manual_needed": manual,
        "branch": branch,
        "port": chosen_port,
        "url": f"http://{cfg['host']}:{chosen_port}",
    }
    build.quality_report = report
    db.commit()

    if manual:
        return {
            "status": "needs_secrets",
            "message": (
                "Couldn't auto-set these repo secrets (PyNaCl missing). Add them once "
                f"in GitHub → repo Settings → Secrets → Actions: {', '.join(manual)}."
            ),
            "secrets_manual_needed": manual,
            "dispatched": dispatched,
        }
    if not dispatched:
        return {"status": "error", "message": "Could not trigger the deploy workflow. Ensure deploy.yml exists (re-scaffold)."}
    return {
        "status": "deploying",
        "message": f"Deploy triggered. App will be at http://{cfg['host']}:{chosen_port}",
        "branch": branch,
        "url": f"http://{cfg['host']}:{chosen_port}",
    }
