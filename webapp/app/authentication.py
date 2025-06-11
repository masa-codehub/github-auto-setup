from rest_framework.authentication import BaseAuthentication
from rest_framework import exceptions
import os


class CustomAPIKeyAuthentication(BaseAuthentication):
    """
    DRF用カスタムAPIキー認証クラス。
    リクエストヘッダー 'X-API-KEY' からAPIキーを取得し、
    環境変数(API_KEY)または設定ファイルの値と照合する。
    """

    def authenticate(self, request):
        api_key = request.headers.get('X-API-KEY')
        valid_key = os.environ.get('API_KEY')
        if not valid_key:
            raise exceptions.AuthenticationFailed('APIキーがサーバーに設定されていません')
        if not api_key:
            raise exceptions.AuthenticationFailed('APIキーが指定されていません')
        if api_key != valid_key:
            raise exceptions.AuthenticationFailed('APIキーが不正です')
        # 認証成功時は (ユーザー, None) を返す。匿名ユーザー扱いでOK
        return (None, None)
