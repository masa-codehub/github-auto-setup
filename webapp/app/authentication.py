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
        valid_key = os.environ.get('BACKEND_API_KEY')
        if api_key and valid_key and api_key == valid_key:
            return (None, None)
        raise exceptions.AuthenticationFailed('有効なAPIキーが指定されていません')
