from rest_framework.authentication import BaseAuthentication
from rest_framework import exceptions
import os


class CustomAPIKeyAuthentication(BaseAuthentication):
    """
    DRF用カスタムAPIキー認証クラス。
    X-API-KEY, X-GitHub-PAT, X-AI-API-KEY のいずれかが有効なら認証成功とする。
    """

    def authenticate(self, request):
        api_key = request.headers.get('X-API-KEY')
        github_pat = request.headers.get('X-GitHub-PAT')
        ai_api_key = request.headers.get('X-AI-API-KEY')
        valid_key = os.environ.get('API_KEY')
        valid_github_pat = os.environ.get('GITHUB_PAT')
        valid_ai_api_key = os.environ.get('AI_API_KEY')
        if api_key and valid_key and api_key == valid_key:
            return (None, None)
        if github_pat and valid_github_pat and github_pat == valid_github_pat:
            return (None, None)
        if ai_api_key and valid_ai_api_key and ai_api_key == valid_ai_api_key:
            return (None, None)
        raise exceptions.AuthenticationFailed('有効なAPIキーが指定されていません')
