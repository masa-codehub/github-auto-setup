from django.test import TestCase, Client, override_settings
from rest_framework import status
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock
from .models import ParsedDataCache
from core_logic.github_automation_tool.domain.models import ParsedRequirementData, IssueData, CreateGitHubResourcesResult
from io import BytesIO
import uuid
import json
from django.utils import timezone
import datetime
from core_logic.github_automation_tool.adapters.github_rest_client import GitHubRestClient
from rest_framework.test import APIClient, force_authenticate
from django.contrib.auth import get_user_model


class AuthenticatedAPITestMixin:
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='testuser', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)


class HealthCheckAPITest(TestCase):
    def test_health_check_api_status_code(self):
        response = self.client.get('/api/v1/healthcheck/')
        self.assertEqual(response.status_code, 200)

    def test_health_check_api_content(self):
        response = self.client.get('/api/v1/healthcheck/')
        self.assertTrue(response.get(
            'Content-Type', '').startswith('application/json'))
        self.assertEqual(response.json(), {
                         "status": "ok", "message": "Django REST Framework is working!"})

    def test_browsable_api_enabled(self):
        response = self.client.get(
            '/api/v1/healthcheck/', HTTP_ACCEPT='text/html')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.get('Content-Type', ''))
        self.assertContains(response, 'Django REST framework')


class FileUploadAPIViewTest(AuthenticatedAPITestMixin, TestCase):
    @patch('app.models.ParsedDataCache.objects.create')
    @patch('core_logic.github_automation_tool.adapters.ai_parser.AIParser.parse')
    def test_upload_valid_markdown_file(self, mock_ai_parse, mock_cache_create):
        # モックのIssueDataを正確に修正
        mock_ai_parse.return_value = ParsedRequirementData(issues=[
            IssueData(title="Test Issue", description="test body",
                      temp_id="issue-1", labels=None, milestone=None, assignees=None)
        ])
        mock_cache_create.return_value.id = uuid.uuid4()
        file_content = b"# Issue\n- title: Test Issue\n- body: test body"
        file = BytesIO(file_content)
        file.name = 'test.md'
        response = self.client.post(
            '/api/v1/upload-issue-file/', {'issue_file': file}, format='multipart')
        self.assertEqual(response.status_code, 200)
        resp_json = response.json()
        self.assertIn('session_id', resp_json)
        self.assertIn('issues', resp_json)
        self.assertEqual(resp_json['issues'][0]['title'], 'Test Issue')
        self.assertEqual(resp_json['issues'][0]['description'], 'test body')
        mock_cache_create.assert_called_once()

    def test_upload_no_file(self):
        response = self.client.post(
            '/api/v1/upload-issue-file/', {}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.json())


class CreateGitHubResourcesAPIViewTest(AuthenticatedAPITestMixin, TestCase):
    @patch('app.models.ParsedDataCache.objects.get')
    @patch('core_logic.github_automation_tool.use_cases.create_github_resources.CreateGitHubResourcesUseCase.execute')
    @patch('core_logic.github_automation_tool.infrastructure.config.load_settings')
    @patch('githubkit.GitHub', spec=True)
    @patch('core_logic.github_automation_tool.use_cases.create_repository.isinstance', return_value=True)
    @patch('app.views.GitHubRestClient', return_value=MagicMock(spec=GitHubRestClient))
    @patch('core_logic.github_automation_tool.adapters.github_graphql_client.GitHubGraphQLClient', spec=True)
    @patch('app.views.AssigneeValidator', spec=True)
    @patch('core_logic.github_automation_tool.use_cases.create_repository.CreateRepositoryUseCase', spec=True)
    @patch('core_logic.github_automation_tool.use_cases.create_issues.CreateIssuesUseCase', spec=True)
    @patch('core_logic.github_automation_tool.use_cases.create_github_resources.isinstance', return_value=True)
    @patch('core_logic.github_automation_tool.use_cases.create_issues.isinstance', return_value=True)
    def test_create_github_resources_success(self, mock_isinstance_issues, mock_isinstance_repo, mock_isinstance, mock_create_issues_uc, mock_create_repo_uc, mock_assignee_validator, mock_graphql_client, mock_rest_client, mock_github, mock_load_settings, mock_execute, mock_cache_get):
        # キャッシュデータのモック
        parsed_data = ParsedRequirementData(issues=[
            IssueData(title="Test Issue", description="test body",
                      temp_id="issue-1", labels=None, milestone=None, assignees=None)
        ])
        mock_cache_entry = MagicMock()
        mock_cache_entry.data = parsed_data.model_dump()
        mock_cache_entry.expires_at = timezone.now() + timezone.timedelta(minutes=5)
        mock_cache_get.return_value = mock_cache_entry
        # UseCaseの戻り値モック
        mock_execute.return_value = CreateGitHubResourcesResult(
            repository_url="http://example.com/test-repo",
            project_name="test-project",
            dry_run=True,
            created_labels=[],
            processed_milestones=[],
            failed_labels=[],
            failed_milestones=[],
            issue_result=None,
            project_items_added_count=0,
            project_items_failed=[],
            fatal_error=None
        )
        payload = {
            "repo_name": "test-repo",
            "project_name": "test-project",
            "dry_run": True,
            "session_id": str(uuid.uuid4()),
            "selected_issue_temp_ids": ["issue-1"]
        }
        response = self.client.post('/api/v1/create-github-resources/',
                                    data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('repository_url', response.json())
        self.assertTrue(response.json()['dry_run'])
        mock_cache_get.assert_called_once()
        mock_execute.assert_called_once()

    @patch('app.models.ParsedDataCache.objects.get', side_effect=ParsedDataCache.DoesNotExist)
    def test_create_github_resources_invalid_session(self, mock_cache_get):
        payload = {
            "repo_name": "test-repo",
            "project_name": "test-project",
            "dry_run": True,
            "session_id": str(uuid.uuid4()),
            "selected_issue_temp_ids": ["issue-1"]
        }
        response = self.client.post('/api/v1/create-github-resources/',
                                    data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.json())

    def test_create_github_resources_missing_session_or_ids(self):
        payload = {"repo_name": "test-repo",
                   "project_name": "test-project", "dry_run": True}
        response = self.client.post('/api/v1/create-github-resources/',
                                    data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.json())


class StaticFilesNotServedTest(TestCase):
    def test_static_file_returns_404(self):
        response = self.client.get('/static/assets/css/custom.css')
        self.assertEqual(response.status_code, 404)


class ParsedDataCacheModelTest(TestCase):
    def test_save_and_load(self):
        data = {"foo": "bar"}
        cache = ParsedDataCache.objects.create(data=data)
        loaded = ParsedDataCache.objects.get(id=cache.id)
        self.assertEqual(loaded.data, data)
        self.assertIsInstance(loaded.id, uuid.UUID)
        self.assertIsNotNone(loaded.created_at)
        self.assertIsNotNone(loaded.expires_at)
        self.assertTrue(loaded.expires_at > loaded.created_at)

    def test_expires_at_auto_set(self):
        data = {"foo": "bar"}
        cache = ParsedDataCache(data=data)
        cache.save()
        self.assertIsNotNone(cache.expires_at)
        # expires_atは作成時刻+10分以内
        delta = cache.expires_at - cache.created_at
        self.assertLessEqual(delta, datetime.timedelta(minutes=10, seconds=1))

    def test_expired_entry(self):
        data = {"foo": "bar"}
        expired_time = timezone.now() - datetime.timedelta(minutes=1)
        cache = ParsedDataCache.objects.create(
            data=data, expires_at=expired_time)
        # 有効期限切れのものは通常のgetで取得できるが、期限切れ判定はアプリ側で行う
        loaded = ParsedDataCache.objects.get(id=cache.id)
        self.assertTrue(loaded.expires_at < timezone.now())


class CORSTest(TestCase):
    def test_allowed_origin(self):
        client = Client(HTTP_ORIGIN='http://localhost:3000')
        response = client.get(reverse('api_v1:health_check_api'))
        self.assertEqual(response.status_code, 200)
        # DEBUG=True時は'*'、DEBUG=False時はオリジンが返る
        self.assertIn(response.get('Access-Control-Allow-Origin'),
                      ['*', 'http://localhost:3000'])

    def test_disallowed_origin(self):
        with override_settings(DEBUG=False, CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=["http://localhost:3000"]):
            client = Client(HTTP_ORIGIN='http://evil.com')
            response = client.get(reverse('api_v1:health_check_api'))
            self.assertNotIn('Access-Control-Allow-Origin', response)


class SecurityHeadersTest(TestCase):
    def test_security_headers_present(self):
        response = self.client.get(reverse('api_v1:health_check_api'))
        self.assertEqual(response.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(response.get('X-Frame-Options'), 'DENY')
        # Content-Security-Policy等も必要に応じて追加
