# webui/urls.py
from django.urls import path
from .views import home_view, result_view, login_view, register_view

app_name = 'webui'

urlpatterns = [
    path('', home_view, name='home'),
    path('result/<uuid:item_id>/', result_view, name='result'),
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
]
