# backend/core/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Frontend pages
    path('', include('webui.urls')),
    
    # API endpoints prefixed with version
    path('api/v1/auth/', include('users.urls')),
    path('api/v1/classification/', include('classification.urls')),
    path('api/v1/safety/', include('safety.urls')),
    # Other features to be appended as they are created:

    # path('api/v1/marketplace/', include('marketplace.urls')),
    # path('api/v1/gamification/', include('gamification.urls')),
    # path('api/v1/notifications/', include('notifications.urls')),
    # path('api/v1/impact/', include('impact.urls')),
    # path('api/v1/moderation/', include('moderation.urls')),
    
    # OpenAPI Schema paths
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
