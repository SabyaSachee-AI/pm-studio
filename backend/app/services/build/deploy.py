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


def _project_path(base: str, repo_full_name: str) -> str:
    """Per-project deploy directory: <base>/<repo-name>.

    Every project gets its own folder automatically, so deploying project B can
    never pull its repo into project A's directory. If the configured path
    already ends with the repo name (old single-app configs), keep it as is.
    """
    repo_name = repo_full_name.split("/")[-1]
    base = base.rstrip("/")
    if base.endswith(f"/{repo_name}"):
        return base
    return f"{base}/{repo_name}"


def _auto_port(db: Any, build: Build) -> int:
    """Stable, collision-free port per project.

    Reuses the port any build of the SAME project already deployed with;
    otherwise picks the lowest free port from 3000 up, skipping ports used by
    other projects' deploys and PM Studio's own services.
    """
    own = ((build.quality_report or {}).get("deploy") or {}).get("port")
    if own:
        return int(own)
    used: set[int] = {8090, 8005, 5432, 6379, 8000}  # PM Studio + common infra
    sibling_port: int | None = None
    for b in db.query(Build).filter(Build.deleted_at.is_(None)).all():
        p = ((b.quality_report or {}).get("deploy") or {}).get("port")
        if not p:
            continue
        if b.project_id == build.project_id:
            sibling_port = int(p)  # same project → same port (stable URL)
        else:
            used.add(int(p))
    if sibling_port and sibling_port not in used:
        return sibling_port
    port = 3000
    while port in used:
        port += 1
    return port


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

    # Per-app web port: explicit choice > this project's existing port > next free.
    report = dict(build.quality_report or {})
    chosen_port = port or _auto_port(db, build)

    # Build an authenticated clone URL so the (private) repo can be cloned/pulled
    # on the VPS without a manual one-time clone.
    token, _ = _db_creds()
    repo_token_url = f"https://{token}@github.com/{full}.git" if token else ""

    secrets = dict(_SECRET_MAP)  # host/user/ssh_key/path
    values = {name: str(cfg[key]) for key, name in secrets.items()}
    # Isolate every project in its own directory under the configured base path.
    deploy_path = _project_path(str(cfg["path"]), full)
    values["VPS_PATH"] = deploy_path
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
        "path": deploy_path,
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
