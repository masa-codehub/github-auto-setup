from django.urls import path
from .views import health_check_api_view, FileUploadAPIView, CreateGitHubResourcesAPIView

app_name = "api_v1"

urlpatterns = [
    path('healthcheck/', health_check_api_view, name='health_check_api'),
    path('upload-issue-file/', FileUploadAPIView.as_view(), name='upload_issue_file_api'),
    path('create-github-resources/', CreateGitHubResourcesAPIView.as_view(), name='create_github_resources_api'),
]
