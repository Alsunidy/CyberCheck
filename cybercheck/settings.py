"""
Django settings — مشروع CyberCheck
Started with Django 6.0.2. Docs: https://docs.djangoproject.com/en/stable/ref/settings/
"""

from __future__ import annotations

import os
from pathlib import Path

# -----------------------------------------------------------------------------
# Paths — مسارات المشروع
# -----------------------------------------------------------------------------
# BASE_DIR = folder that holds manage.py / apps / templates (مجلد جذر المشروع)
BASE_DIR = Path(__file__).resolve().parent.parent


# -----------------------------------------------------------------------------
# Core / security — الأمان والوضع التشغيلي
# -----------------------------------------------------------------------------
# SECRET_KEY: don’t leak this in production (السر لازم يبقى خاص، وغيّره بالإنتاج)
SECRET_KEY = "django-insecure-_qm$pa914djiq_gv5pd8ros4)r-o5t#2_qg)clsld_bw66e=&2"

# DEBUG True = detailed errors for dev only (تطوير بس؛ بالإنتاج خلّها False)
DEBUG = True

# Hostnames the site may use (localhost + tests؛ زوّد القائمة لو تفتح من جهاز ثاني على الشبكة)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]


# -----------------------------------------------------------------------------
# Apps — التطبيقات المثبّتة
# -----------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "pages.apps.PagesConfig",
    "compliance.apps.ComplianceConfig",
]


# -----------------------------------------------------------------------------
# Middleware — طبقة الطلبات (ترتيب مهم، لا تخلط بدون سبب)
# -----------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",  # language from cookie / Accept-Language (اللغة)
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "cybercheck.urls"
WSGI_APPLICATION = "cybercheck.wsgi.application"


# -----------------------------------------------------------------------------
# Templates — القوالب
# -----------------------------------------------------------------------------
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
                "django.template.context_processors.i18n",  # LANGUAGE_CODE & i18n in templates (عربي/English)
            ],
        },
    },
]


# -----------------------------------------------------------------------------
# Database — قاعدة البيانات 
# -----------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# -----------------------------------------------------------------------------
# Password validation — قوة كلمات المرور
# -----------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# -----------------------------------------------------------------------------
# Internationalization — الترجمة والوقت
# -----------------------------------------------------------------------------
# Default UI language: Arabic first (المستخدم يقدر يحوّل للإنجليزي من زر اللغة).
# New user-facing strings: wrap in {% trans %} / _('...') and add msgstr in locale/ar/LC_MESSAGES/django.po
LANGUAGE_CODE = "ar"

LANGUAGES = [
    ("en", "English"),
    ("ar", "العربية"),
]

LOCALE_PATHS = [BASE_DIR / "locale"]

TIME_ZONE = "UTC"
USE_I18N = True
USE_L10N = True
USE_TZ = True


# -----------------------------------------------------------------------------
# Static & media — ملفات الموقع والمرفقات
# -----------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# After login / logout — أسماء الـ URL في pages.urls (بدون namespace)
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"


# -----------------------------------------------------------------------------
# OCR (Tesseract) — استخراج نص من الصور للأدلة
# -----------------------------------------------------------------------------
# If tesseract isn’t on PATH, set env TESSERACT_CMD (مسار الـ exe على ويندوز)
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "")
# Folder with traineddata (غالباً .../Tesseract-OCR/tessdata)
TESSDATA_PREFIX = os.environ.get("TESSDATA_PREFIX", "").strip()
# Primary OCR language(s), e.g. eng | ara | ara+eng
TESSERACT_OCR_LANG = os.environ.get("TESSERACT_OCR_LANG", "eng").strip() or "eng"
# Fallback langs if primary returns empty (comma-separated)
TESSERACT_OCR_FALLBACK_LANGS = os.environ.get("TESSERACT_OCR_FALLBACK_LANGS", "").strip()


# -----------------------------------------------------------------------------
# Evidence scoring — تقديم الأدلة  
# -----------------------------------------------------------------------------
# Whole-word match for Latin = fewer false hits (أقل تشويش على كلمات إنجليزي)
EVIDENCE_SCORE_WORD_BOUNDARIES = True
# Too-short extracted text → never “approved” (نص قصير غالباً ضوضاء OCR/PDF)
EVIDENCE_MIN_EXTRACTED_LENGTH = int(os.environ.get("EVIDENCE_MIN_EXTRACTED_LENGTH", "40"))
# Min keyword hits for “approved”; None = auto rule (فارغ من البيئة = تلقائي)
_RAW_APPROVED_MIN = os.environ.get("EVIDENCE_APPROVED_MIN_MATCHES")
EVIDENCE_APPROVED_MIN_MATCHES = (
    int(_RAW_APPROVED_MIN) if _RAW_APPROVED_MIN not in (None, "") else None
)


# -----------------------------------------------------------------------------
# Logging — سجل الأحداث
# -----------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "compliance.evidence": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}
