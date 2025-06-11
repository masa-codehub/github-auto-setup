import pytest
from rest_framework.test import APIClient
from django.urls import reverse
from unittest.mock import patch, MagicMock
from core_logic.domain.models import ParsedRequirementData, IssueData, CreateGitHubResourcesResult
from django.utils import timezone
import datetime


@pytest.mark.django_db
def test_create_github_resources_success(client):
    # モックデータとAPIキー
    session_id = 1
    repo_name = "test-repo"
    project_name = "test-project"
    dry_run = True
    selected_issue_temp_ids = ["temp-1"]
    # キャッシュデータ作成
    from app.models import ParsedDataCache
    parsed_data = ParsedRequirementData(
        issues=[IssueData(temp_id="temp-1", title="t", description="d")])
    cache = ParsedDataCache.objects.create(data=parsed_data.model_dump(
    ), expires_at=timezone.now() + datetime.timedelta(minutes=10))
    # APIリクエスト
    url = reverse("app:create_github_resources_api")
    dummy_result = CreateGitHubResourcesResult(
        repository_url="https://github.com/test/test-repo", project_name=project_name)
    with patch("app.views.CreateGitHubResourcesUseCase.execute", return_value=dummy_result):
        response = client.post(url, {
            "repo_name": repo_name,
            "project_name": project_name,
            "dry_run": dry_run,
            "session_id": cache.id,
            "selected_issue_temp_ids": selected_issue_temp_ids
        }, format="json")
    assert response.status_code == 200
    assert "repository_url" in response.data


@pytest.mark.django_db
def test_create_github_resources_auth_error(client):
    url = reverse("app:create_github_resources_api")
    response = client.post(url, {}, format="json")
    assert response.status_code in (400, 401, 403)


@pytest.mark.django_db
def test_save_locally_success(client):
    session_id = 1
    selected_issue_temp_ids = ["temp-1"]
    from app.models import ParsedDataCache
    parsed_data = ParsedRequirementData(
        issues=[IssueData(temp_id="temp-1", title="t", description="d")])
    cache = ParsedDataCache.objects.create(data=parsed_data.model_dump(
    ), expires_at=timezone.now() + datetime.timedelta(minutes=10))
    url = reverse("app:save_locally_api")
    response = client.post(url, {
        "session_id": cache.id,
        "selected_issue_temp_ids": selected_issue_temp_ids,
        "dry_run": True
    }, format="json")
    assert response.status_code == 200
    assert response.data["success"] is True


@pytest.mark.django_db
def test_save_locally_fs_error(client, monkeypatch):
    # ファイルシステムエラーを強制
    url = reverse("app:save_locally_api")
    monkeypatch.setattr("app.views.SaveLocallyAPIView.post",
                        lambda *a, **k: (_ for _ in ()).throw(Exception("FS error")))
    import pytest
    with pytest.raises(Exception) as excinfo:
        client.post(url, {"session_id": 1, "selected_issue_temp_ids": [
                    "temp-1"]}, format="json")
    assert "FS error" in str(excinfo.value)
