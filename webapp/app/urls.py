from django.urls import path
from .views import health_check_api_view, FileUploadAPIView, GitHubCreateIssuesAPIView, LocalSaveIssuesAPIView, top_page_view, AiSettingsAPIView, UploadAndParseView, CreateGitHubResourcesAPIView

app_name = "app"

urlpatterns = [
    path('', top_page_view, name='top_page'),
    path('healthcheck/', health_check_api_view, name='health_check_api'),
    path('upload-issue-file/', FileUploadAPIView.as_view(),
         name='upload_issue_file_api'),
    path('parse-file/', FileUploadAPIView.as_view(), name='parse_file_api'),
    path('github-create-issues/', GitHubCreateIssuesAPIView.as_view(),
         name='github_create_issues_api'),
    path('local-save-issues/', LocalSaveIssuesAPIView.as_view(),
         name='local_save_issues_api'),
    path('ai-settings/', AiSettingsAPIView.as_view(), name='ai_settings_api'),
    path('upload-and-parse/', UploadAndParseView.as_view(),
         name='upload_and_parse_api'),
    path('api/upload-and-parse/', UploadAndParseView.as_view(),
         name='upload_and_parse_api_explicit'),
    path('v1/create-github-resources/', CreateGitHubResourcesAPIView.as_view(),
         name='create_github_resources_api'),
    path('api/v1/create-github-resources/',
         CreateGitHubResourcesAPIView.as_view(), name='create_github_resources_api'),
]
