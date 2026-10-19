"""Configuração do app Moedas do Plano Real.

Tudo que muda entre teste e produção vem de variáveis de ambiente (.env).
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(nome, padrao=False):
    return os.environ.get(nome, str(padrao)).strip().lower() in ("1", "true", "sim", "yes", "on")


def env_list(nome, padrao=""):
    return [v.strip() for v in os.environ.get(nome, padrao).split(",") if v.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-inseguro-troque-no-env")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.microsoft",
    "allauth.socialaccount.providers.apple",
    "colecao",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "colecao.context.app",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Banco: se DB_HOST estiver definido usa Postgres (VM dedicada);
# sem ele cai num SQLite local, útil só para desenvolvimento/testes.
if os.environ.get("DB_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": os.environ["DB_HOST"],
            "PORT": os.environ.get("DB_PORT", "5432"),
            "NAME": os.environ.get("DB_NAME", "moedas"),
            "USER": os.environ.get("DB_USER", "moedas"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Boa_Vista"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
if "test" in sys.argv:  # testes não dependem do collectstatic
    STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}

LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "account_login"

# ---------- Contas (django-allauth) ----------
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
ACCOUNT_ADAPTER = "colecao.adapters.ContaAdapter"
SOCIALACCOUNT_ADAPTER = "colecao.adapters.ContaSocialAdapter"
ACCOUNT_LOGIN_METHODS = {"email", "username"}  # e-mail para todos; usuário "rhauan" continua valendo
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_SESSION_REMEMBER = True
# none = entra direto após cadastrar; mandatory = exige confirmar o e-mail (precisa de SMTP)
ACCOUNT_EMAIL_VERIFICATION = os.environ.get("ACCOUNT_EMAIL_VERIFICATION") or "none"
CADASTRO_ABERTO = env_bool("CADASTRO_ABERTO", True) if os.environ.get("CADASTRO_ABERTO") else True

# Login com Google conecta na conta que já tenha o mesmo e-mail (o Google verifica o e-mail).
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_PROVIDERS = {}
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    SOCIALACCOUNT_PROVIDERS["google"] = {
        "APPS": [{"client_id": GOOGLE_CLIENT_ID, "secret": GOOGLE_CLIENT_SECRET, "key": ""}],
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "OAUTH_PKCE_ENABLED": True,
    }

# Login com Microsoft (contas pessoais Outlook/Hotmail e contas de trabalho/escola).
# O e-mail da Microsoft não vem marcado como verificado, então não conecta sozinho a uma conta existente.
MICROSOFT_CLIENT_ID = os.environ.get("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET = os.environ.get("MICROSOFT_CLIENT_SECRET", "")
if MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET:
    SOCIALACCOUNT_PROVIDERS["microsoft"] = {
        "APPS": [{"client_id": MICROSOFT_CLIENT_ID, "secret": MICROSOFT_CLIENT_SECRET, "key": ""}],
        "TENANT": "common",
        "SCOPE": ["User.Read"],
    }

# Login com Apple (exige Apple Developer Program e site em HTTPS; não funciona em localhost).
APPLE_CLIENT_ID = os.environ.get("APPLE_CLIENT_ID", "")  # "Services ID"
APPLE_KEY_ID = os.environ.get("APPLE_KEY_ID", "")
APPLE_TEAM_ID = os.environ.get("APPLE_TEAM_ID", "")
APPLE_PRIVATE_KEY = os.environ.get("APPLE_PRIVATE_KEY", "").replace("\\n", "\n")  # conteúdo do .p8
if APPLE_CLIENT_ID and APPLE_KEY_ID and APPLE_TEAM_ID and APPLE_PRIVATE_KEY:
    SOCIALACCOUNT_PROVIDERS["apple"] = {
        "APPS": [{
            "client_id": APPLE_CLIENT_ID,
            "secret": APPLE_KEY_ID,
            "key": APPLE_TEAM_ID,
            "settings": {"certificate_key": APPLE_PRIVATE_KEY},
        }],
    }

# E-mail (recuperar senha / confirmar cadastro). Sem EMAIL_HOST, os e-mails só saem no log.
if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT") or 587)
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL") or "Moedas do Real <nao-responda@localhost>"

# ---------- Notificações (Web Push) ----------
# Gere as chaves com:  python manage.py gerar_chaves_push
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_EMAIL = os.environ.get("VAPID_EMAIL", "")

# Contato exibido na política de privacidade
CONTATO_EMAIL = os.environ.get("CONTATO_EMAIL", "")

# Login fica salvo no celular por 90 dias.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 90

# Atrás do Cloudflare Tunnel o acesso chega por HTTPS; o túnel informa isso
# pelo cabeçalho X-Forwarded-Proto. Em teste pela rede local (http) deixe
# DJANGO_SECURE_COOKIES=False, senão o login não funciona.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", False)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
