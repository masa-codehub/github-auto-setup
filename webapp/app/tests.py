from django.test import TestCase, Client, override_settings
from rest_framework import status
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock
from .models import ParsedDataCache
from core_logic.domain.models import ParsedRequirementData, IssueData, CreateGitHubResourcesResult
from io import BytesIO
import uuid
import json
from django.utils import timezone
import datetime
from core_logic.adapters.github_rest_client import GitHubRestClient
from rest_framework.test import APIClient, force_authenticate
from django.contrib.auth import get_user_model
from core_logic.domain.exceptions import AiParserError, ParsingError
import os


class AuthenticatedAPITestMixin:
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='testuser', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)


@override_settings(API_KEY='test-api-key')
class HealthCheckAPITest(TestCase):
    def setUp(self):
        self.api_key = 'test-api-key'
        self.client = APIClient()
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        os.environ['API_KEY'] = self.api_key

    def test_health_check_api_status_code(self):
        response = self.client.get(
            '/api/v1/healthcheck/', HTTP_X_API_KEY=self.api_key)
        self.assertEqual(response.status_code, 200)

    def test_health_check_api_content(self):
        response = self.client.get(
            '/api/v1/healthcheck/', HTTP_X_API_KEY=self.api_key)
        self.assertTrue(response.get(
            'Content-Type', '').startswith('application/json'))
        self.assertEqual(response.json(), {
                         "status": "ok", "message": "Django REST Framework is working!"})

    def test_browsable_api_enabled(self):
        response = self.client.get(
            '/api/v1/healthcheck/', HTTP_ACCEPT='text/html', HTTP_X_API_KEY=self.api_key)
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.get('Content-Type', ''))
        self.assertContains(response, 'Django REST framework')


class FileUploadAPIViewTest(AuthenticatedAPITestMixin, TestCase):
    @patch('app.models.ParsedDataCache.objects.create')
    @patch('core_logic.adapters.ai_parser.AIParser.parse')
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

    @patch('app.models.ParsedDataCache.objects.create')
    @patch('core_logic.adapters.ai_parser.AIParser.parse')
    def test_upload_unsupported_extension(self, mock_ai_parse, mock_cache_create):
        file_content = b"dummy content"
        file = BytesIO(file_content)
        file.name = 'test.txt'  # サポート外拡張子
        response = self.client.post(
            '/api/v1/upload-issue-file/', {'issue_file': file}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.json())
        self.assertIn('Unsupported file extension', response.json()['detail'])

    @patch('app.models.ParsedDataCache.objects.create')
    @patch('core_logic.adapters.ai_parser.AIParser.parse')
    def test_upload_file_size_exceeded(self, mock_ai_parse, mock_cache_create):
        # 10MB + 1byte のダミーファイル
        file_content = b"0" * (10 * 1024 * 1024 + 1)
        file = BytesIO(file_content)
        file.name = 'test.md'
        response = self.client.post(
            '/api/v1/upload-issue-file/', {'issue_file': file}, format='multipart')
        # 実装によっては400, 413, 422などもあり得るが、要件通り400
        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.json())
        self.assertIn('file size', response.json()['detail'].lower())

    @patch('app.models.ParsedDataCache.objects.create')
    @patch('core_logic.adapters.ai_parser.AIParser.parse', side_effect=AiParserError('AI解析エラー'))
    def test_upload_ai_parser_error(self, mock_ai_parse, mock_cache_create):
        file_content = b"# Issue\n- title: Test Issue\n- body: test body"
        file = BytesIO(file_content)
        file.name = 'test.md'
        response = self.client.post(
            '/api/v1/upload-issue-file/', {'issue_file': file}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.json())
        self.assertIn('AI解析エラー', response.json()['detail'])

    @patch('app.models.ParsedDataCache.objects.create')
    @patch('core_logic.adapters.ai_parser.AIParser.parse', side_effect=Exception('予期せぬ例外'))
    def test_upload_unexpected_exception(self, mock_ai_parse, mock_cache_create):
        file_content = b"# Issue\n- title: Test Issue\n- body: test body"
        file = BytesIO(file_content)
        file.name = 'test.md'
        response = self.client.post(
            '/api/v1/upload-issue-file/', {'issue_file': file}, format='multipart')
        self.assertEqual(response.status_code, 500)
        self.assertIn('detail', response.json())
        self.assertIn('予期せぬ例外', response.json()['detail'])


class CreateGitHubResourcesAPIViewTest(AuthenticatedAPITestMixin, TestCase):
    @patch('app.models.ParsedDataCache.objects.get')
    @patch('core_logic.use_cases.create_github_resources.CreateGitHubResourcesUseCase.execute')
    @patch('core_logic.infrastructure.config.load_settings')
    @patch('core_logic.use_cases.create_repository.isinstance', return_value=True)
    @patch('core_logic.adapters.github_graphql_client.GitHubGraphQLClient', spec=True)
    @patch('core_logic.use_cases.create_repository.CreateRepositoryUseCase', spec=True)
    @patch('core_logic.use_cases.create_issues.CreateIssuesUseCase', spec=True)
    @patch('core_logic.use_cases.create_github_resources.isinstance', return_value=True)
    @patch('core_logic.use_cases.create_issues.isinstance', return_value=True)
    def test_create_github_resources_success(self, mock_isinstance_issues, mock_isinstance_github_resources, mock_create_issues_uc, mock_create_repo_uc, mock_graphql_client, mock_isinstance_repo, mock_load_settings, mock_execute, mock_cache_get):
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
    def setUp(self):
        self.api_key = 'test-api-key'
        os.environ['API_KEY'] = self.api_key
        from django.conf import settings as dj_settings
        dj_settings.API_KEY = self.api_key
        self.client = APIClient()
        self.client.credentials(HTTP_X_API_KEY=self.api_key)

    def test_allowed_origin(self):
        response = self.client.get(reverse('api_v1:health_check_api'),
                                   HTTP_ORIGIN='http://localhost:3000', HTTP_X_API_KEY=self.api_key)
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.get('Access-Control-Allow-Origin'),
                      ['*', 'http://localhost:3000'])

    def test_disallowed_origin(self):
        with override_settings(DEBUG=False, CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=["http://localhost:3000"]):
            from django.conf import settings as dj_settings
            dj_settings.API_KEY = self.api_key
            client = APIClient()
            client.credentials(HTTP_X_API_KEY=self.api_key)
            response = client.get(reverse('api_v1:health_check_api'),
                                  HTTP_ORIGIN='http://evil.com', HTTP_X_API_KEY=self.api_key)
            self.assertNotIn('Access-Control-Allow-Origin', response)


class SecurityHeadersTest(TestCase):
    def test_security_headers_present(self):
        response = self.client.get(reverse('api_v1:health_check_api'))
        self.assertEqual(response.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(response.get('X-Frame-Options'), 'DENY')
        # Content-Security-Policy等も必要に応じて追加


class CustomAPIKeyAuthenticationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.valid_key = 'test-api-key'
        os.environ['API_KEY'] = self.valid_key
        self.url = '/api/v1/healthcheck/'

    def tearDown(self):
        if 'API_KEY' in os.environ:
            del os.environ['API_KEY']

    def test_valid_api_key_allows_access(self):
        response = self.client.get(self.url, HTTP_X_API_KEY=self.valid_key)
        self.assertNotIn(response.status_code, [401, 403])

    def test_invalid_api_key_denies_access(self):
        response = self.client.get(self.url, HTTP_X_API_KEY='wrong-key')
        self.assertIn(response.status_code, [401, 403])

    def test_missing_api_key_denies_access(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, [401, 403])

    def test_no_server_api_key_configured(self):
        del os.environ['API_KEY']
        response = self.client.get(self.url, HTTP_X_API_KEY=self.valid_key)
        self.assertIn(response.status_code, [401, 403])

class UserAiSettingsAPITest(AuthenticatedAPITestMixin, TestCase):
    def test_get_default_ai_settings(self):
        response = self.client.get('/api/v1/ai-settings/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('ai_provider', response.json())
        self.assertIn('openai_model', response.json())

    def test_post_and_get_ai_settings(self):
        data = {
            'ai_provider': 'gemini',
            'openai_model': 'gpt-4o',
            'gemini_model': 'gemini-1.5-pro',
            'openai_api_key': 'test-openai',
            'gemini_api_key': 'test-gemini'
        }
        post_resp = self.client.post(
            '/api/v1/ai-settings/', data, format='json')
        self.assertEqual(post_resp.status_code, 200)
        get_resp = self.client.get('/api/v1/ai-settings/')
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()['ai_provider'], 'gemini')
        self.assertEqual(get_resp.json()['gemini_model'], 'gemini-1.5-pro')