"""Validate and repair architecture suite cross-document alignment."""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import Any

from app.models.architecture import DOC_FIELDS
from app.services.ai.architecture_canon import build_suite_canon_from_srs
from app.services.ai.mermaid_sanitize import sanitize_doc_diagrams

# Universal tech-stack drift fixes — apply to every generated project
_STACK_PATTERNS = (
    (re.compile(r"/api/auth/", re.I), "/api/v1/auth/"),
    (re.compile(r"/api/auth\b", re.I), "/api/v1/auth"),
    (re.compile(r"signin", re.I), "login"),
    (re.compile(r"signup", re.I), "register"),
    (re.compile(r"next-?auth", re.I), "JWT HttpOnly cookies via FastAPI"),
    (re.compile(r"NextAuth\.js", re.I), "FastAPI JWT auth"),
)

# Project-specific entity drift fixes (e.g. AI calling notebooks "folders").
# Applied ONLY when the canonical entity exists in the suite canon glossary.
_KNOWN_ENTITY_DRIFT: dict[str, tuple[tuple[re.Pattern[str], str], ...]] = {
    "notebooks": (
        (re.compile(r"/folders\b", re.I), "/notebooks"),
        (re.compile(r"\bfolders\b", re.I), "notebooks"),
        (re.compile(r"\bfolder_id\b", re.I), "notebook_id"),
        (re.compile(r"\bfolder\b", re.I), "notebook"),
    ),
}


def _entity_patterns(canon: dict[str, Any] | None) -> tuple[tuple[re.Pattern[str], str], ...]:
    """Stack patterns + drift patterns for entities present in this project's canon."""
    patterns: list[tuple[re.Pattern[str], str]] = list(_STACK_PATTERNS)
    glossary = (canon or {}).get("entity_glossary") or {}
    for entity, drift in _KNOWN_ENTITY_DRIFT.items():
        if entity in glossary:
            patterns = list(drift) + patterns
    return tuple(patterns)


def normalize_api_call_string(call: str, canon: dict[str, Any] | None = None) -> str:
    """Strip HTTP method prefix and FR annotations from frontend api_calls."""
    c = str(call or "").strip()
    m = re.match(r"^(GET|POST|PUT|PATCH|DELETE)\s+(.+)$", c, re.I)
    if m:
        c = m.group(2).strip()
    c = re.sub(r"\s*\(FR-\d+\)\s*$", "", c, flags=re.I)
    return _apply_text_replacements(c, canon)


def _match_call_to_api_path(call: str, api_paths: list[str]) -> str:
    call = CALL_PATH_ALIASES.get(call, call)
    if call in api_paths:
        return call
    for p in api_paths:
        if p and (call.endswith(p) or p in call or call.endswith(p.split("/")[-1])):
            return p
    for alias_src, alias_dst in CALL_PATH_ALIASES.items():
        if call.startswith(alias_src) and alias_dst in api_paths:
            return alias_dst
    return call


def _entity_slug(name: str) -> str:
    """Normalize entity name to snake_case slug for fuzzy matching."""
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def _entity_matches_table(entity: str, table_name: str) -> bool:
    """True if a glossary entity name is reasonably represented by a DB table name.

    Handles multi-word phrases like 'public knowledge base' → 'knowledge_base'.
    """
    ent = _entity_slug(entity)
    tbl = _entity_slug(table_name)
    if ent == tbl:
        return True
    # Substring in either direction (e.g. "logs" ⊂ "audit_logs")
    if ent in tbl or tbl in ent:
        return True
    # Word overlap: any significant word (>3 chars) shared
    ent_words = {w for w in ent.split("_") if len(w) > 3}
    tbl_words = {w for w in tbl.split("_") if len(w) > 3}
    return bool(ent_words & tbl_words)


def _glossary_entity_covered(entity: str, table_names: set[str]) -> bool:
    """True if any table in the DB represents this glossary entity."""
    return any(_entity_matches_table(entity, t) for t in table_names)


def _fr_ids_from_srs(srs_content: dict[str, Any]) -> list[str]:
    frs = srs_content.get("functional_requirements") or []
    ids: list[str] = []
    for fr in frs:
        fid = str(fr.get("fr_number") or fr.get("id") or fr.get("fr_id") or "")
        if fid:
            ids.append(fid.upper() if fid.upper().startswith("FR") else fid)
    return ids


def _normalize_fr_id(fr: str) -> str:
    s = str(fr or "").strip().upper()
    if s and not s.startswith("FR"):
        if s.isdigit():
            return f"FR-{s.zfill(3)}"
    return s


def _apply_text_replacements(text: str, canon: dict[str, Any] | None = None) -> str:
    if not text:
        return text
    out = text
    for pattern, repl in _entity_patterns(canon):
        out = pattern.sub(repl, out)
    return out


_STACK_KEY_RENAMES = {
    "[...nextauth]": "[auth]",
    "nextauth": "jwt_auth",
}

_ENTITY_KEY_RENAMES: dict[str, dict[str, str]] = {
    "notebooks": {
        "folder_id": "notebook_id",
        "folders": "notebooks",
        "folder": "notebook",
    },
}


def _key_renames(canon: dict[str, Any] | None) -> dict[str, str]:
    renames = dict(_STACK_KEY_RENAMES)
    glossary = (canon or {}).get("entity_glossary") or {}
    for entity, mapping in _ENTITY_KEY_RENAMES.items():
        if entity in glossary:
            renames.update(mapping)
    return renames


def _rename_key(key: str, renames: dict[str, str]) -> str:
    k = str(key)
    return renames.get(k, renames.get(k.lower(), k))


def _deep_replace_strings(obj: Any, canon: dict[str, Any] | None = None) -> Any:
    renames = _key_renames(canon)

    def walk(node: Any) -> Any:
        if isinstance(node, str):
            return _apply_text_replacements(node, canon)
        if isinstance(node, dict):
            return {_rename_key(k, renames): walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(obj)


CALL_PATH_ALIASES: dict[str, str] = {
    "/api/v1/user/profile": "/api/v1/auth/me",
    "/api/v1/user/preferences": "/api/v1/auth/me",
    "/api/v1/subscription": "/api/v1/users/me/usage",
    "/api/v1/users/profile": "/api/v1/auth/me",
}


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return s[:40] or "feature"


def _generic_fr_stub(fr_id: str, srs_content: dict[str, Any]) -> dict[str, Any] | None:
    """Build a minimal endpoint stub for an uncovered FR from its SRS title (any project)."""
    for fr in srs_content.get("functional_requirements") or []:
        fid = str(fr.get("fr_number") or fr.get("id") or fr.get("fr_id") or "")
        if _normalize_fr_id(fid) != fr_id:
            continue
        title = str(fr.get("title") or fr.get("description") or fr.get("name") or fr_id)
        slug = _slugify(title)
        return {
            "module": slug.split("-")[0],
            "method": "POST",
            "path": f"/{slug}",
            "description": f"{title} (auto-stub — refine during implementation)",
            "auth_required": True,
            "mvp_scope": "v2",
        }
    return None


def sync_frontend_api_calls(
    api_doc: dict[str, Any],
    fe_doc: dict[str, Any],
    canon: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild frontend page api_calls from API endpoint catalog."""
    fe_doc = copy.deepcopy(fe_doc)
    endpoints = api_doc.get("endpoints") or []
    all_paths = [
        str(e.get("full_path") or e.get("path") or "")
        for e in endpoints
        if e.get("full_path") or e.get("path")
    ]
    by_module: dict[str, list[str]] = defaultdict(list)
    for ep in endpoints:
        mod = str(ep.get("module") or "general").lower()
        path = str(ep.get("full_path") or ep.get("path") or "")
        if path:
            by_module[mod].append(path)

    # Universal hints + project entities (canon glossary) + API modules themselves
    path_hints: list[tuple[str, str]] = [
        ("login", "auth"),
        ("register", "auth"),
        ("setting", "auth"),
        ("profile", "auth"),
        ("preference", "auth"),
    ]
    for entity in ((canon or {}).get("entity_glossary") or {}):
        singular = entity.rstrip("s")
        path_hints.append((singular, entity))
    for mod in by_module:
        if mod != "general":
            path_hints.append((mod.rstrip("s"), mod))

    for page in fe_doc.get("pages") or []:
        page_path = str(page.get("path") or "").lower()
        matched: list[str] = []
        for hint, module in path_hints:
            if hint in page_path:
                matched.extend(by_module.get(module, []))
        if not matched:
            for ep_path in all_paths:
                segment = page_path.strip("/").split("/")[-1] if page_path else ""
                if segment and segment in ep_path.lower():
                    matched.append(ep_path)
        if not matched and page.get("protected") is False:
            matched = [p for p in all_paths if "/auth/" in p][:3]
        if matched:
            raw_calls = list(dict.fromkeys(matched[:10]))
        else:
            # Only keep existing calls that already match API paths (clear the rest
            # so the validator doesn't penalise un-syncable stale paths)
            existing = page.get("api_calls") or []
            raw_calls = [c for c in existing if c and c in all_paths]
        page["api_calls"] = [
            _match_call_to_api_path(normalize_api_call_string(c, canon), all_paths)
            for c in raw_calls
            if c
        ]
    return fe_doc


def align_security_to_api(
    api_doc: dict[str, Any],
    sec_doc: dict[str, Any],
    canon: dict[str, Any],
) -> dict[str, Any]:
    """Build RBAC permission matrix from API modules and auth flags."""
    sec_doc = copy.deepcopy(sec_doc)
    endpoints = api_doc.get("endpoints") or []
    modules = sorted({str(e.get("module") or "general") for e in endpoints})
    roles = canon.get("roles") or []
    matrix: dict[str, list[str]] = {}
    for role in roles:
        perms: list[str] = []
        for mod in modules:
            mod_eps = [e for e in endpoints if str(e.get("module")) == mod]
            if role == "admin":
                perms.append(f"{mod}: *")
            elif role == "guest":
                public = [e for e in mod_eps if not e.get("auth_required")]
                if public:
                    perms.append(f"{mod}: {', '.join(e.get('method', 'GET') for e in public[:3])}")
            elif role.startswith("collaborator"):
                perms.append(f"{mod}: read, comment" if "comment" in role else f"{mod}: read, write_shared")
            else:
                perms.append(f"{mod}: read, write_own")
        matrix[role] = perms
    rbac = sec_doc.get("rbac") or {}
    rbac["permission_matrix"] = matrix
    rbac["roles"] = rbac.get("roles") or [
        {"name": r, "description": f"{r} per suite canon", "permissions": matrix.get(r, [])}
        for r in roles
    ]
    sec_doc["rbac"] = rbac
    api_security = []
    for ep in endpoints[:20]:
        api_security.append({
            "control": f"{ep.get('method')} {ep.get('full_path')}",
            "implementation": (
                "JWT + RBAC required" if ep.get("auth_required") else "Public endpoint"
            ),
        })
    sec_doc["api_security"] = api_security
    return sec_doc


def apply_deterministic_fixes(
    docs: dict[str, dict[str, Any] | None],
    srs_content: dict[str, Any],
    suite_canon: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any] | None]:
    """Rule-based repairs across all 6 documents."""
    fixed = {k: copy.deepcopy(v) if v else None for k, v in docs.items()}
    canon = suite_canon or build_suite_canon_from_srs(
        srs_content,
        srs_content.get("project_name", "Project"),
    )

    # Entities considered v1/MVP for this project: canon glossary + auth basics
    glossary_entities = {str(k).lower() for k in (canon.get("entity_glossary") or {})}
    v1_modules = glossary_entities | {"auth", "users", "sessions"}

    # System arch — modular monolith
    sys_doc = fixed.get("doc_system_arch")
    if sys_doc:
        sys_doc = _deep_replace_strings(sys_doc, canon)
        pattern = str(sys_doc.get("architecture_pattern") or "")
        pname = canon.get("project_name", "")
        overview = str(sys_doc.get("overview") or "")
        if pname and pname.lower() not in overview.lower():
            sys_doc["overview"] = f"{pname}: {overview}".strip(": ")
        if "microservice" in pattern.lower() or len(sys_doc.get("components") or []) > 8:
            sys_doc["architecture_pattern"] = canon["architecture_pattern"]
            comps = sys_doc.get("components") or []
            if len(comps) > 8:
                sys_doc["components"] = comps[:8]
                sys_doc["overview"] = (
                    str(sys_doc.get("overview", ""))
                    + " MVP uses a modular monolith; advanced scale-out is v2."
                )
        else:
            sys_doc["architecture_pattern"] = canon["architecture_pattern"]
        fixed["doc_system_arch"] = sys_doc

    # Database — canonical entity names + MVP tagging
    db_doc = fixed.get("doc_database")
    if db_doc:
        db_doc = _deep_replace_strings(db_doc, canon)
        for tbl in db_doc.get("tables") or []:
            if "mvp_scope" not in tbl:
                name = str(tbl.get("name") or "").lower()
                tbl["mvp_scope"] = "v1" if (name in v1_modules or not glossary_entities) else "v2"
        fixed["doc_database"] = db_doc

    # API — paths, auth text, FR coverage, mvp_scope
    api_doc = fixed.get("doc_api")
    if api_doc:
        api_doc = _deep_replace_strings(api_doc, canon)
        api_doc["base_url"] = canon["api_base_url"]
        api_doc["auth"] = canon["auth_strategy"]
        endpoints = api_doc.get("endpoints") or []
        seen_paths: set[str] = set()
        covered_frs: set[str] = set()
        new_eps: list[dict[str, Any]] = []
        for i, ep in enumerate(endpoints):
            ep = dict(ep)
            path = _apply_text_replacements(str(ep.get("path") or ""), canon)
            full = _apply_text_replacements(str(ep.get("full_path") or ""), canon)
            if not full and path:
                base = canon["api_base_url"].rstrip("/")
                full = f"{base}{path}" if path.startswith("/") else f"{base}/{path}"
            ep["path"] = path
            ep["full_path"] = full
            if "mvp_scope" not in ep:
                ep["mvp_scope"] = "v1" if (
                    str(ep.get("module") or "").lower() in v1_modules or not glossary_entities
                ) else "v2"
            lid = _normalize_fr_id(str(ep.get("linked_fr") or ""))
            if lid:
                covered_frs.add(lid)
            key = f"{ep.get('method')}:{full}"
            if key not in seen_paths:
                seen_paths.add(key)
                if not ep.get("id"):
                    ep["id"] = f"ep-{i + 1:03d}"
                new_eps.append(ep)

        required_frs = [_normalize_fr_id(x) for x in _fr_ids_from_srs(srs_content)]
        for fr_id in required_frs:
            if fr_id and fr_id not in covered_frs:
                stub = _generic_fr_stub(fr_id, srs_content)
                if stub:
                    path = stub["path"]
                    full = f"{canon['api_base_url'].rstrip('/')}{path}"
                    key = f"{stub['method']}:{full}"
                    if key not in seen_paths:
                        new_eps.append({
                            "id": f"ep-stub-{fr_id.lower()}",
                            "module": stub["module"],
                            "method": stub["method"],
                            "path": path,
                            "full_path": full,
                            "description": stub["description"],
                            "linked_fr": fr_id,
                            "auth_required": stub["auth_required"],
                            "mvp_scope": stub.get("mvp_scope", "v2"),
                            "request_body": {},
                            "response_200": {},
                            "response_errors": {},
                            "cookies_set": [],
                            "file": "",
                        })
                        covered_frs.add(fr_id)

        if len(new_eps) > 32 and glossary_entities:
            for ep in new_eps:
                if str(ep.get("module") or "").lower() not in v1_modules:
                    ep["mvp_scope"] = "v2"

        api_doc["endpoints"] = new_eps
        fixed["doc_api"] = api_doc

    # Frontend — align auth and api_calls to API
    fe_doc = fixed.get("doc_frontend")
    api_doc_fixed = fixed.get("doc_api") or {}
    if fe_doc:
        fe_doc = _deep_replace_strings(fe_doc, canon)
        fe_doc["auth"] = canon["auth_strategy"]
        fe_doc["api_client"] = (
            "lib/api.ts — fetch with credentials:include to FastAPI "
            f"{canon['api_base_url']}"
        )
        fe_doc = sync_frontend_api_calls(api_doc_fixed, fe_doc, canon)
        fixed["doc_frontend"] = fe_doc

    # Security — align roles and auth
    sec_doc = fixed.get("doc_security")
    if sec_doc:
        sec_doc = _deep_replace_strings(sec_doc, canon)
        sec_doc["auth_mechanism"] = {
            **(sec_doc.get("auth_mechanism") or {}),
            "type": "JWT HttpOnly cookies",
            "issuer": "FastAPI backend",
            "login_endpoint": "POST /api/v1/auth/login",
            "register_endpoint": "POST /api/v1/auth/register",
            "no_nextauth": True,
        }
        sec_doc = align_security_to_api(api_doc_fixed, sec_doc, canon)
        fixed["doc_security"] = sec_doc

    # UI/UX
    ui_doc = fixed.get("doc_uiux")
    if ui_doc:
        fixed["doc_uiux"] = _deep_replace_strings(ui_doc, canon)

    for field in DOC_FIELDS:
        doc = fixed.get(field)
        if doc:
            fixed[field] = sanitize_doc_diagrams(doc)

    return fixed


def collect_docs_from_architecture(arch: Any) -> dict[str, dict[str, Any] | None]:
    return {field: getattr(arch, field, None) for field in DOC_FIELDS}


def persist_fixed_docs(arch: Any, fixed: dict[str, dict[str, Any] | None]) -> None:
    for field in DOC_FIELDS:
        if fixed.get(field) is not None:
            setattr(arch, field, fixed[field])


def validate_suite(
    docs: dict[str, dict[str, Any] | None],
    srs_content: dict[str, Any],
    suite_canon: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score suite on 8 criteria (0-10 each)."""
    issues: list[str] = []
    canon = suite_canon or build_suite_canon_from_srs(
        srs_content, srs_content.get("project_name", "Project")
    )

    sys_doc = docs.get("doc_system_arch") or {}
    api_doc = docs.get("doc_api") or {}
    db_doc = docs.get("doc_database") or {}
    fe_doc = docs.get("doc_frontend") or {}
    sec_doc = docs.get("doc_security") or {}

    # 1. Product vision
    vision_score = 10
    pname = canon.get("project_name", "").lower()
    if pname and pname not in str(sys_doc.get("overview", "")).lower():
        vision_score -= 2
        issues.append("System overview may not reference project vision")

    # 2. SRS traceability
    required_frs = [_normalize_fr_id(x) for x in _fr_ids_from_srs(srs_content)]
    endpoints = api_doc.get("endpoints") or []
    covered = {
        _normalize_fr_id(str(e.get("linked_fr") or ""))
        for e in endpoints
        if e.get("linked_fr")
    }
    missing_frs = [f for f in required_frs if f and f not in covered]
    if not required_frs:
        srs_score = 8
    elif not missing_frs:
        srs_score = 10
    else:
        srs_score = max(4, 10 - len(missing_frs) * 2)
        issues.append(f"API missing FR coverage: {missing_frs}")

    # 3. API ↔ Database — canonical entities must exist as tables, drift terms must not
    tables = {str(t.get("name", "")).lower() for t in (db_doc.get("tables") or [])}
    api_db_score = 10
    glossary = {str(k).lower() for k in (canon.get("entity_glossary") or {})}
    drift_terms = [t for e, pats in _KNOWN_ENTITY_DRIFT.items() if e in glossary for t in ("folders",)]
    for term in drift_terms:
        if term in str(db_doc).lower():
            api_db_score -= 3
            issues.append(f"Database still references non-canonical term: {term}")
        api_text_l = str(api_doc).lower()
        if re.search(rf"\b{term}\b", api_text_l) or f"/{term}" in api_text_l:
            api_db_score -= 2
            issues.append(f"API still references non-canonical term: {term}")
    if tables and glossary:
        missing_entities = [
            e for e in glossary
            if not _glossary_entity_covered(e, tables)
        ][:5]
        if missing_entities:
            api_db_score -= min(3, len(missing_entities))
            issues.append(f"Database missing canonical entity tables: {missing_entities}")

    # 4. API ↔ Frontend
    api_paths = {
        str(e.get("full_path") or e.get("path") or "")
        for e in endpoints
        if e.get("full_path") or e.get("path")
    }
    fe_calls: list[str] = []
    for page in fe_doc.get("pages") or []:
        fe_calls.extend(str(c) for c in (page.get("api_calls") or []))
    fe_text = str(fe_doc).lower()
    fe_text_clean = re.sub(r"no next-?auth", "", fe_text, flags=re.I)
    api_fe_score = 10
    if re.search(r"next-?auth", fe_text_clean, re.I) or "/api/auth/" in fe_text:
        api_fe_score -= 4
        issues.append("Frontend still uses NextAuth or /api/auth paths")
    # Use fuzzy path matching: treat a call as matched if any API path ends with or contains it
    def _path_covered(call: str) -> bool:
        if call in api_paths:
            return True
        # Partial suffix match: /notebooks matches /api/v1/notebooks
        return any(p.endswith(call) or call.endswith(p.split("/")[-1]) for p in api_paths if p)

    mismatches = sum(1 for call in fe_calls if call and not _path_covered(call))
    if mismatches > 0:
        api_fe_score -= min(6, mismatches * 2)
        issues.append(f"Frontend has {mismatches} api_calls not matching API paths")

    # 5. System ↔ stack
    sys_score = 10
    pattern = str(sys_doc.get("architecture_pattern", "")).lower()
    if "microservice" in pattern:
        sys_score -= 4
        issues.append("System doc describes microservices vs monolith stack")
    comps = sys_doc.get("components") or []
    if len(comps) > 10:
        sys_score -= 2
        issues.append("Too many deployable components for MVP")

    # 6. Security ↔ API
    sec_score = 10
    sec_auth = str(sec_doc.get("auth_mechanism", {})).lower()
    api_auth = str(api_doc.get("auth", "")).lower()
    if re.search(r"(?<!no_)next-?auth", sec_auth, re.I):
        sec_score -= 3
    if "httponly" not in sec_auth and "cookie" not in sec_auth:
        sec_score -= 2
    rbac_roles = sec_doc.get("rbac", {}).get("roles") or []
    role_names = {
        (r.get("name") if isinstance(r, dict) else str(r)).lower()
        for r in rbac_roles
    }
    for role in canon["roles"]:
        if role.lower() not in role_names:
            sec_score -= 1

    # 7. MVP scope
    mvp_score = 10
    v1_count = sum(1 for e in endpoints if e.get("mvp_scope") == "v1")
    if len(endpoints) > 0 and v1_count == 0:
        mvp_score -= 4
        issues.append("No endpoints tagged mvp_scope=v1")
    v2_count = sum(1 for e in endpoints if e.get("mvp_scope") == "v2")
    if len(endpoints) > 40 and v2_count < len(endpoints) // 2:
        mvp_score -= 2
        issues.append("API endpoint count high for MVP without v2 tagging")

    # 8. Dev-ready
    ready_score = 10
    for field, doc in docs.items():
        if not doc:
            ready_score -= 2
            issues.append(f"Missing document: {field}")
    if missing_frs:
        ready_score -= min(4, len(missing_frs) * 2)
    if api_fe_score < 9:
        ready_score -= 2

    scores = {
        "product_vision": min(10, max(0, vision_score)),
        "srs_traceability": min(10, max(0, srs_score)),
        "api_database_alignment": min(10, max(0, api_db_score)),
        "api_frontend_alignment": min(10, max(0, api_fe_score)),
        "system_stack_alignment": min(10, max(0, sys_score)),
        "security_api_alignment": min(10, max(0, sec_score)),
        "mvp_scope": min(10, max(0, mvp_score)),
        "dev_ready": min(10, max(0, ready_score)),
    }
    overall = round(sum(scores.values()) / len(scores), 1)
    return {
        "scores": scores,
        "overall": overall,
        "issues": issues,
        "missing_frs": missing_frs,
        "endpoint_count": len(endpoints),
        "fr_coverage": f"{len(covered & set(required_frs))}/{len(required_frs)}",
    }
