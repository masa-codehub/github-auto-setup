from rest_framework.permissions import BasePermission


class HasValidAPIKey(BasePermission):
    """
    有効なAPIキーを持つリクエストのみ許可するパーミッションクラス。
    """

    def has_permission(self, request, view):
        return request.successful_authenticator is not None
