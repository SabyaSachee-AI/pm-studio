"""End-to-end MVP flow: Requirements → PRD → SRS → Kanban → Spec → KB."""

import json
import sys
import time

import requests

BASE = "http://localhost:8000/api/v1"
PROJECT_ID = "e891ce0a-7b5a-47fb-bafd-dd9bbf728ce6"
REQUIREMENT_ID = "c8825af9-c19a-49de-aec4-3d0b2ab22e8b"


def login() -> dict:
    r = requests.post(
        f"{BASE}/auth/login",
        data={"username": "owner@pmstudio.com", "password": "password123"},
        timeout=30,
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def poll_job(job_id: str, label: str, interval: int = 5, max_attempts: int = 120) -> dict:
    print(f"Polling {label} job {job_id}...")
    for i in range(max_attempts):
        r = requests.get(f"{BASE}/jobs/{job_id}", timeout=30)
        data = r.json()
        status = data.get("status", "UNKNOWN")
        print(f"  [{i + 1}] {status}")
        if status in ("SUCCESS", "FAILURE"):
            if status == "FAILURE":
                print("  ERROR:", data.get("error"))
                sys.exit(1)
            return data
        time.sleep(interval)
    print(f"TIMEOUT waiting for {label}")
    sys.exit(1)


def main() -> None:
    headers = login()
    print("=== 1. Requirement ===")
    req = requests.get(f"{BASE}/requirements/{REQUIREMENT_ID}", headers=headers, timeout=30).json()
    print(f"Requirement: {req['original_filename']} status={req['status']}")
    if not req.get("analysis_result"):
        print("Requirement not analyzed — upload/analyze first.")
        sys.exit(1)

    print("\n=== 2. PRD ===")
    prds = requests.get(f"{BASE}/prds/project/{PROJECT_ID}", headers=headers, timeout=30).json()
    prd = next((p for p in prds if p.get("content_json")), None)
    if not prd:
        gen = requests.post(
            f"{BASE}/prds/generate",
            headers=headers,
            json={"project_id": PROJECT_ID, "requirement_id": REQUIREMENT_ID},
            timeout=30,
        ).json()
        poll_job(gen["task_id"], "PRD", interval=5)
        prd = requests.get(f"{BASE}/prds/{gen['prd_id']}", headers=headers, timeout=30).json()

    prd_id = prd["id"]
    print(f"PRD {prd_id} status={prd['status']}")
    if prd["status"] == "draft":
        prd = requests.patch(f"{BASE}/prds/{prd_id}/submit", headers=headers, timeout=30).json()
        print("Submitted PRD")
    if prd["status"] == "submitted":
        prd = requests.patch(f"{BASE}/prds/{prd_id}/approve", headers=headers, timeout=30).json()
        print("Approved PRD")
    if prd["status"] != "approved":
        print("PRD not approved:", prd["status"])
        sys.exit(1)

    print("\n=== 3. SRS ===")
    srs_list = requests.get(f"{BASE}/srs/project/{PROJECT_ID}", headers=headers, timeout=30).json()
    srs = next((s for s in srs_list if s.get("content_json")), None)
    if not srs:
        gen = requests.post(
            f"{BASE}/srs/generate",
            headers=headers,
            json={"project_id": PROJECT_ID, "prd_id": prd_id},
            timeout=30,
        ).json()
        poll_job(gen["task_id"], "SRS", interval=10)
        srs = requests.get(f"{BASE}/srs/{gen['srs_id']}", headers=headers, timeout=30).json()

    srs_id = srs["id"]
    print(f"SRS {srs_id} status={srs['status']}")
    if srs["status"] == "draft":
        srs = requests.patch(f"{BASE}/srs/{srs_id}/submit", headers=headers, timeout=30).json()
        print("Submitted SRS")
    if srs["status"] == "submitted":
        srs = requests.patch(f"{BASE}/srs/{srs_id}/approve", headers=headers, timeout=30).json()
        print("Approved SRS")
    if srs["status"] != "approved":
        print("SRS not approved:", srs["status"])
        sys.exit(1)
    fr_count = len(srs.get("content_json", {}).get("functional_requirements", []))
    print(f"SRS FRs: {fr_count}")

    print("\n=== 4. Extract modules -> Kanban ===")
    ext = requests.post(
        f"{BASE}/tasks/extract-modules",
        headers=headers,
        json={"project_id": PROJECT_ID, "srs_id": srs_id},
        timeout=30,
    )
    print("Extract:", json.dumps(ext.json(), indent=2))
    ext.raise_for_status()
    poll_job(ext.json()["task_id"], "modules", interval=5)
    board = requests.get(f"{BASE}/tasks/kanban/{PROJECT_ID}", headers=headers, timeout=30).json()
    total = sum(len(board[col]) for col in board)
    print(f"Kanban tasks: {total}")
    task = board["backlog"][0] if board["backlog"] else None
    if not task:
        for col in ("assigned", "in_progress", "in_review", "done"):
            if board[col]:
                task = board[col][0]
                break
    if not task:
        print("No tasks on board after extraction")
        sys.exit(1)
    task_id = task["id"]
    print(f"Using task: {task['title']} ({task_id})")

    print("\n=== 5. Generate spec ===")
    try:
        spec_gen = requests.post(
            f"{BASE}/specs/generate",
            headers=headers,
            json={"task_id": task_id},
            timeout=30,
        )
        if spec_gen.status_code == 400 and "already exists" in spec_gen.text:
            spec = requests.get(f"{BASE}/specs/task/{task_id}", headers=headers, timeout=30).json()
            spec_id = spec["id"]
            print(f"Using existing spec {spec_id} status={spec['status']}")
        else:
            spec_gen.raise_for_status()
            body = spec_gen.json()
            spec_id = body["spec_id"]
            poll_job(body["task_id_celery"], "spec", interval=5)
            spec = requests.get(f"{BASE}/specs/{spec_id}", headers=headers, timeout=30).json()
    except requests.HTTPError as e:
        print("Spec error:", e.response.text)
        sys.exit(1)

    print(f"Spec status: {spec['status']}")
    if spec.get("content_json"):
        scope = str(spec["content_json"].get("task_scope", ""))[:120]
        print(f"Scope: {scope}...")
    else:
        print("No spec content")
        sys.exit(1)

    print("\n=== 6. Save to Knowledge Base ===")
    kb = requests.post(
        f"{BASE}/knowledge/items/save-from-source",
        headers=headers,
        json={"source_type": "spec", "source_id": spec_id, "title": task["title"]},
        timeout=30,
    )
    kb.raise_for_status()
    item = kb.json()
    print(f"KB item saved: {item['id']} — {item['title']}")

    items = requests.get(f"{BASE}/knowledge/items", headers=headers, timeout=30).json()
    print(f"Total KB items: {len(items)}")
    print("\n=== E2E FLOW COMPLETE ===")


if __name__ == "__main__":
    main()
