from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import FileUploadForm
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import ParsedDataCache, UserAiSettings
from django.utils import timezone
from core_logic.domain.models import ParsedRequirementData, IssueData
from core_logic.infrastructure.config import load_settings
from core_logic.adapters.ai_parser import AIParser
from core_logic.adapters.markdown_issue_parser import MarkdownIssueParser
from core_logic.adapters.yaml_issue_parser import YamlIssueParser
from core_logic.adapters.json_issue_parser import JsonIssueParser
from core_logic.domain.exceptions import AiParserError, ParsingError
from core_logic.use_cases.create_github_resources import CreateGitHubResourcesUseCase
from githubkit import GitHub
from core_logic.adapters.github_rest_client import GitHubRestClient
from core_logic.adapters.github_graphql_client import GitHubGraphQLClient
from core_logic.adapters.assignee_validator import AssigneeValidator
from core_logic.use_cases.create_repository import CreateRepositoryUseCase
from core_logic.use_cases.create_issues import CreateIssuesUseCase
from core_logic.domain.exceptions import GitHubClientError, GitHubAuthenticationError, GitHubValidationError
from core_logic.services import parse_issue_file_service
from .authentication import CustomAPIKeyAuthentication
from webapp.app.permissions import HasValidAPIKey
from .serializers import ParsedRequirementDataSerializer, CreateGitHubResourcesResultSerializer
from core_logic.use_cases.local_save_use_case import LocalSaveUseCase


import logging
import os
import uuid

logger = logging.getLogger(__name__)

settings = load_settings()
ai_parser = AIParser(settings=settings)
parse_issue_file_service = parse_issue_file_service.ParseIssueFileService(
    ai_parser)


@api_view(['GET'])
def health_check_api_view(request):
    """
    シンプルなヘルスチェックAPI。
    DRFが正しくセットアップされているかを確認するために使用。
    """
    return Response({"status": "ok", "message": "Django REST Framework is working!"}, status=status.HTTP_200_OK)


def api_root(request):
    """
    API専用サーバーであることを明示するルート用エンドポイント。
    """
    return JsonResponse({
        "message": "This server provides backend APIs only. See /api/ for endpoints."
    })


class FileUploadAPIView(APIView):
    parser_classes = [MultiPartParser]
    authentication_classes = [CustomAPIKeyAuthentication]
    permission_classes = []

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get('issue_file')
        if not uploaded_file:
            return Response({"detail": "No file uploaded."}, status=status.HTTP_400_BAD_REQUEST)
        # 10MB超過チェック
        max_size = 10 * 1024 * 1024  # 10MB
        if uploaded_file.size > max_size:
            return Response({"detail": "File size exceeds 10MB limit."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            parsed_data = parse_issue_file_service.parse(
                uploaded_file.name, uploaded_file.read())
            if not parsed_data.issues:
                return Response({"detail": "No issues extracted from file."}, status=status.HTTP_400_BAD_REQUEST)
            # パース結果を一時保存
            cached_entry = ParsedDataCache.objects.create(
                data=parsed_data.model_dump())
            unique_session_id = str(cached_entry.id)
            # UI に返すのは必要最小限の情報
            minimal_issues_data = [
                {
                    "temp_id": issue.temp_id,
                    "title": issue.title,
                    "description": issue.description,
                    "assignees": issue.assignees,
                    "labels": issue.labels,
                    "tasks": issue.tasks,
                    "acceptance": issue.acceptance,
                    "milestone": issue.milestone,
                    "relational_definition": issue.relational_definition,
                    "relational_issues": issue.relational_issues,
                }
                for issue in parsed_data.issues
            ]
            return Response({
                "session_id": unique_session_id,
                "issues": minimal_issues_data
            }, status=status.HTTP_200_OK)
        except (ParsingError, AiParserError) as e:
            logger.error(f"File parsing error: {e}", exc_info=True)
            return Response({"detail": f"File parsing failed: {e}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(
                f"Unexpected error during file upload and parsing: {e}")
            return Response({"detail": f"An unexpected error occurred: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateGitHubResourcesAPIView(APIView):
    authentication_classes = [CustomAPIKeyAuthentication]
    permission_classes = []

    def post(self, request, *args, **kwargs):
        repo_name = request.data.get('repo_name', '').strip()
        project_name = request.data.get('project_name', '').strip() or None
        dry_run = request.data.get('dry_run', False)
        session_id = request.data.get('session_id')
        selected_issue_temp_ids = request.data.get(
            'selected_issue_temp_ids', [])

        if not session_id or not selected_issue_temp_ids:
            return Response({"detail": "Missing session ID or selected issues."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            cached_entry = ParsedDataCache.objects.get(id=session_id)
            if cached_entry.expires_at < timezone.now():
                cached_entry.delete()
                return Response({"detail": "Parsed data session expired."}, status=status.HTTP_400_BAD_REQUEST)
            full_parsed_data = ParsedRequirementData(**cached_entry.data)
            selected_issues = [
                issue for issue in full_parsed_data.issues
                if issue.temp_id in selected_issue_temp_ids
            ]
            if not selected_issues:
                return Response({"detail": "No selected issues found matching the provided IDs within the cached data."}, status=status.HTTP_400_BAD_REQUEST)
            parsed_data_for_use_case = ParsedRequirementData(
                issues=selected_issues)
        except ParsedDataCache.DoesNotExist:
            return Response({"detail": "Parsed data session not found or expired."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(
                f"Failed to load or process cached data: {e}", exc_info=True)
            return Response({"detail": "Failed to retrieve parsed issue data."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        try:
            settings = load_settings()
            github_instance = GitHub(settings.github_pat.get_secret_value())
            rest_client = GitHubRestClient(github_instance=github_instance)
            graphql_client = GitHubGraphQLClient(
                github_instance=github_instance)
            assignee_validator = AssigneeValidator(rest_client=rest_client)
            create_repo_uc = CreateRepositoryUseCase(github_client=rest_client)
            create_issues_uc = CreateIssuesUseCase(
                rest_client=rest_client, assignee_validator=assignee_validator)
            main_use_case = CreateGitHubResourcesUseCase(
                rest_client=rest_client,
                graphql_client=graphql_client,
                create_repo_uc=create_repo_uc,
                create_issues_uc=create_issues_uc
            )
            result = main_use_case.execute(
                parsed_data=parsed_data_for_use_case,
                repo_name_input=repo_name,
                project_name=project_name,
                dry_run=dry_run
            )
            serializer = CreateGitHubResourcesResultSerializer(
                result.model_dump())
            return Response(serializer.data, status=status.HTTP_200_OK)
        except (GitHubAuthenticationError, GitHubClientError, GitHubValidationError) as e:
            logger.error(f"GitHub operation failed: {e}", exc_info=True)
            return Response({"detail": f"GitHub operation failed: {e}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(
                f"Unexpected error during GitHub resource creation: {e}")
            return Response({"detail": f"An unexpected error occurred: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GitHubCreateIssuesAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request, *args, **kwargs):
        repo_name = request.data.get('repo_name', '').strip()
        project_name = request.data.get('project_name', '').strip() or None
        dry_run = request.data.get('dry_run', False)
        issue_ids = request.data.get('issue_ids', [])
        # session_idは現状未対応のため、仮で全件取得
        if not issue_ids:
            return Response({'detail': 'No issue IDs provided.'}, status=status.HTTP_400_BAD_REQUEST)
        # TODO: 本来はParsedDataCacheからsession_idで取得し、該当issueのみ抽出
        # ここではダミーで成功レスポンス
        return Response({'detail': 'GitHub登録API呼び出し成功（ダミー）', 'issue_ids': issue_ids}, status=status.HTTP_200_OK)


class SaveLocallyAPIView(APIView):
    authentication_classes = [CustomAPIKeyAuthentication]
    permission_classes = []

    def post(self, request, *args, **kwargs):
        session_id = request.data.get('session_id')
        selected_issue_temp_ids = request.data.get(
            'selected_issue_temp_ids', [])
        dry_run = request.data.get('dry_run', False)
        if not session_id or not selected_issue_temp_ids:
            return Response({"detail": "Missing session ID or selected issues."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            cached_entry = ParsedDataCache.objects.get(id=session_id)
            if cached_entry.expires_at < timezone.now():
                cached_entry.delete()
                return Response({"detail": "Parsed data session expired."}, status=status.HTTP_400_BAD_REQUEST)
            full_parsed_data = ParsedRequirementData(**cached_entry.data)
            selected_issues = [
                issue for issue in full_parsed_data.issues
                if issue.temp_id in selected_issue_temp_ids
            ]
            if not selected_issues:
                return Response({"detail": "No selected issues found matching the provided IDs within the cached data."}, status=status.HTTP_400_BAD_REQUEST)
            parsed_data_for_use_case = ParsedRequirementData(
                issues=selected_issues)
        except ParsedDataCache.DoesNotExist:
            return Response({"detail": "Parsed data session not found or expired."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(
                f"Failed to load or process cached data: {e}", exc_info=True)
            return Response({"detail": "Failed to retrieve parsed issue data."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        try:
            result = LocalSaveUseCase().execute(
                parsed_data=parsed_data_for_use_case, dry_run=dry_run)
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception(f"Unexpected error during local save: {e}")
            return Response({"detail": f"An unexpected error occurred: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UploadAndParseView(APIView):
    parser_classes = [MultiPartParser]
    authentication_classes = [CustomAPIKeyAuthentication]
    permission_classes = [HasValidAPIKey]

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({"detail": "No file uploaded."}, status=status.HTTP_400_BAD_REQUEST)
        max_size = 10 * 1024 * 1024
        if uploaded_file.size > max_size:
            return Response({"detail": "File size exceeds 10MB limit."}, status=status.HTTP_400_BAD_REQUEST)
        allowed_exts = ['md', 'yml', 'yaml', 'json']
        ext = uploaded_file.name.split('.')[-1].lower()
        if ext not in allowed_exts:
            return Response({"detail": "Unsupported file extension."}, status=status.HTTP_400_BAD_REQUEST)
        github_pat = request.headers.get('X-GitHub-PAT')
        ai_api_key = request.headers.get('X-AI-API-KEY')
        if not github_pat or not ai_api_key:
            return Response({"detail": "API key missing."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            parsed_data = parse_issue_file_service.parse(
                uploaded_file.name, uploaded_file.read())
            serializer = ParsedRequirementDataSerializer(parsed_data)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except (ParsingError, AiParserError) as e:
            return Response({"detail": f"File parsing failed: {e}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": f"Unexpected error: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserAiSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAiSettings
        fields = [
            'ai_provider', 'openai_model', 'gemini_model', 'openai_api_key', 'gemini_api_key'
        ]


class AiSettingsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            settings = UserAiSettings.objects.get(user=request.user)
            serializer = UserAiSettingsSerializer(settings)
            return Response(serializer.data, status=200)
        except UserAiSettings.DoesNotExist:
            # デフォルト値を返す
            return Response({
                'ai_provider': 'openai',
                'openai_model': 'gpt-4o',
                'gemini_model': 'gemini-1.5-flash',
                'openai_api_key': '',
                'gemini_api_key': ''
            }, status=200)

    def post(self, request):
        obj, _ = UserAiSettings.objects.get_or_create(user=request.user)
        serializer = UserAiSettingsSerializer(
            obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)


@ensure_csrf_cookie
def top_page_view(request):
    form = FileUploadForm()
    return render(request, 'top_page.html', {'upload_form': form, 'issue_count': 0, 'issue_list': []})