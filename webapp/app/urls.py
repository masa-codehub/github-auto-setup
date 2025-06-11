from django.urls import path
from .views import health_check_api_view, FileUploadAPIView, GitHubCreateIssuesAPIView, top_page_view, AiSettingsAPIView, CreateGitHubResourcesAPIView, SaveLocallyAPIView

app_name = "app"

urlpatterns = [
    path('', top_page_view, name='top_page'),
    path('healthcheck/', health_check_api_view, name='health_check_api'),
    path('upload-issue-file/', FileUploadAPIView.as_view(),
         name='upload_issue_file_api'),
    path('parse-file/', FileUploadAPIView.as_view(), name='parse_file_api'),
    path('github-create-issues/', GitHubCreateIssuesAPIView.as_view(),
         name='github_create_issues_api'),
    path('save-locally/', SaveLocallyAPIView.as_view(), name='save_locally_api'),
    path('ai-settings/', AiSettingsAPIView.as_view(), name='ai_settings_api'),
    path('create-github-resources/', CreateGitHubResourcesAPIView.as_view(),
         name='create_github_resources_api'),
]
