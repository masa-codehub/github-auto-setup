import pytest
from rest_framework.test import APIClient
import os


@pytest.fixture(autouse=True)
def client():
    os.environ['BACKEND_API_KEY'] = 'test-api-key'  # テスト用APIキーを環境変数にセット
    client = APIClient()
    client.credentials(HTTP_X_API_KEY='test-api-key')
    return client
