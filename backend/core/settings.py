# backend/core/settings.py
import os
import sys
from dotenv import load_dotenv
from pathlib import Path
from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent 
load_dotenv(BASE_DIR / ".env")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY and not DEBUG:
    raise ImproperlyConfigured("SECRET_KEY must be set")
elif not SECRET_KEY:
    SECRET_KEY = 'django-insecure-prod-key-for-local-dev-change-me'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party packages
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',
    
    # Custom apps
    'users',
    'classification',
    'safety',
    'webui',
    # 'marketplace',

    # 'impact',
    # 'gamification',
    # 'notifications',
    # 'audit',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'
ASGI_APPLICATION = 'core.asgi.application'

# Database configuration (PostgreSQL production / SQLite local development fallback)
DB_NAME = os.environ.get('DB_NAME', 'wastetrack')
DB_USER = os.environ.get('DB_USER', 'wt_admin')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'securepassword123')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')

# Check if GDAL/GEOS is available for PostGIS, fallback to standard postgresql if not
try:
    from django.contrib.gis.geos import GEOSGeometry
    HAS_GDAL = True
except ImproperlyConfigured:
    HAS_GDAL = False

DB_ENGINE = 'django.contrib.gis.db.backends.postgis' if HAS_GDAL else 'django.db.backends.postgresql'

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    import urllib.parse as urlparse
    url = urlparse.urlparse(DATABASE_URL)
    DATABASES = {
        'default': {
            'ENGINE': DB_ENGINE,
            'NAME': url.path[1:],
            'USER': url.username,
            'PASSWORD': url.password,
            'HOST': url.hostname,
            'PORT': url.port or 5432,
        }
    }
elif os.environ.get('USE_POSTGRES', 'False').lower() == 'true':
    DATABASES = {
        'default': {
            'ENGINE': DB_ENGINE,
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': DB_HOST,
            'PORT': DB_PORT,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Storage Configuration (Local FileSystem locally, Google Cloud Storage in production if GS_BUCKET_NAME is set)
GS_BUCKET_NAME = os.environ.get('GS_BUCKET_NAME')
if GS_BUCKET_NAME:
    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.gcloud.GoogleCloudStorage',
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        }
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/hour',
        'user': '300/hour',
    }
}

# SimpleJWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': os.environ.get('JWT_SECRET_KEY', SECRET_KEY),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# OpenAPI Docs Setup
SPECTACULAR_SETTINGS = {
    'TITLE': 'WasteTrack+ API',
    'DESCRIPTION': 'AI-powered waste classification and reuse marketplace system APIs',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# Redis Cache configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
USE_LOCAL_CACHE = os.environ.get('USE_LOCAL_CACHE', 'False').lower() in ('true', '1', 't')
if 'test' in sys.argv or USE_LOCAL_CACHE:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'safety-test-cache',
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        }
    }

# Celery Configuration
CELERY_TASK_ALWAYS_EAGER = os.environ.get('CELERY_TASK_ALWAYS_EAGER', str(USE_LOCAL_CACHE)).lower() in ('true', '1', 't')
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', REDIS_URL)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_TASK_DEFAULT_RETRY_DELAY = 60
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ROUTES = {
    "classification.tasks.*": {"queue": "classification"},
    "users.tasks.*": {"queue": "notifications"},
    "safety.tasks.*": {"queue": "safety"},
}

# Celery Beat Schedule for periodic tasks
CELERY_BEAT_SCHEDULE = {
    'reap-stuck-classifications': {
        'task': 'classification.tasks.reap_stuck_classifications_task',
        'schedule': timedelta(minutes=5),
    },
    'reap-stuck-safety-tasks': {
        'task': 'safety.tasks.reap_stuck_safety_tasks',
        'schedule': timedelta(minutes=5),
    },
    'escalate-overdue-reviews': {
        'task': 'safety.tasks.escalate_overdue_reviews_task',
        'schedule': timedelta(minutes=30),
    },
}

# CORS Configuration
CORS_ALLOWED_ORIGINS = os.environ.get('CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')

# Logger Settings
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

# Production Security Headers (Active when DEBUG is False)
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Email Configuration
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend'
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@wastetrackplus.com')

# AI APIs
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# File and Data Upload Limits (15MB to allow high-res images)
DATA_UPLOAD_MAX_MEMORY_SIZE = 15728640
FILE_UPLOAD_MAX_MEMORY_SIZE = 15728640