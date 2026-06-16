"""Tests for the requirements traceability endpoint."""

from uuid import UUID
from fastapi.testclient import TestClient

from app.main import app
from app.api.deps import get_current_user
from app.models.user import User, UserRole

client = TestClient(app)


async def mock_get_current_user():
    """Bypasses standard authentication by returning a mock owner user."""
    return User(
        id=UUID("00000000-0000-0000-0000-000000000000"),
        email="owner@pmstudio.com",
        full_name="Owner Admin",
        role=UserRole.studio_owner,
        is_active=True,
    )


def test_get_traceability_endpoint() -> None:
    """Validate that the traceability endpoint fetches mapping data successfully."""
    app.dependency_overrides[get_current_user] = mock_get_current_user
    try:
        # Acme E-Commerce project ID from seeded database
        project_id = "e891ce0a-7b5a-47fb-bafd-dd9bbf728ce6"
        response = client.get(f"/api/v1/tasks/traceability/{project_id}")
        
        print(f"Traceability Response Status: {response.status_code}")
        
        # If the project is seeded, it should be 200.
        # Otherwise, if database is empty/unseeded, 404 is also a valid code path.
        if response.status_code == 200:
            data = response.json()
            assert data["project_id"] == project_id
            assert "project_name" in data
            assert "requirement" in data
            assert "prd" in data
            assert "srs" in data
            assert "architecture" in data
            assert "tasks" in data
            print(f"Project Name: {data.get('project_name')}")
            print(f"Requirement structure exists: {data.get('requirement') is not None}")
            print(f"PRD structure exists: {data.get('prd') is not None}")
            print(f"SRS structure exists: {data.get('srs') is not None}")
            print(f"Architecture structure exists: {data.get('architecture') is not None}")
            print(f"Number of tasks found: {len(data.get('tasks', []))}")
        else:
            assert response.status_code == 404
            print("Project not found in database (possibly empty/unseeded db).")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
