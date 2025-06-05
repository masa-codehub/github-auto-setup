"""
URL configuration for webapp_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from app.views import api_root

urlpatterns = [
    # path('admin/', admin.site.urls),  # 管理画面不要ならコメントアウト
    path('', api_root, name='api_root_base'),
    path('api/v1/', include(('app.urls', 'api_v1'), namespace='api_v1')),
    path('api/', include('rest_framework.urls', namespace='rest_framework_docs')),
]
