from django.urls import path
from .views import (
    health_check_api_view, 
    FileUploadAPIView, 
    GitHubCreateIssuesAPIView, 
    top_page_view, 
    AiSettingsAPIView, 
    CreateGitHubResourcesAPIView, 
    SaveLocallyAPIView,
    UploadAndParseView
)

app_name = "app"

urlpatterns = [
    # --- Web Page ---
    path('', top_page_view, name='top_page'),

    # --- API Endpoints ---
    path('healthcheck/', health_check_api_view, name='health_check_api'),
    path('ai-settings/', AiSettingsAPIView.as_view(), name='ai_settings_api'),

    # --- File Processing API (mainブランチの新しいエンドポイントを採用) ---
    path('api/upload-and-parse/', UploadAndParseView.as_view(), name='upload_and_parse_api'),

    # --- GitHub Resource Creation and Local Save API (issue#209_01の機能とmainのURL構造を統合) ---
    path('api/v1/create-github-resources/', CreateGitHubResourcesAPIView.as_view(), name='create_github_resources_api'),
    path('api/v1/save-locally/', SaveLocallyAPIView.as_view(), name='save_locally_api'),

    # --- Legacy/Compatibility Endpoints (古いクライアント向けに残すか、将来的に削除) ---
    path('upload-issue-file/', FileUploadAPIView.as_view(), name='upload_issue_file_api'),
    path('parse-file/', FileUploadAPIView.as_view(), name='parse_file_api'),
    path('github-create-issues/', GitHubCreateIssuesAPIView.as_view(), name='github_create_issues_api'),
]