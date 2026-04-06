"""
Root URL configuration — جذر المشروع (كل المسارات تتجمّع هنا).

`urlpatterns` tells Django which view runs for each path.
Django docs: https://docs.djangoproject.com/en/stable/topics/http/urls/

Note: several `path("", include(...))` share the same prefix — order matters (الأول يفوز).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

# -----------------------------------------------------------------------------
# URL table — جدول المسارات
# -----------------------------------------------------------------------------
urlpatterns = [
    # Django admin site — لوحة الإدارة الافتراضية
    path("admin/", admin.site.urls),
    # Language switch (POST to set cookie) — تبديل اللغة عبر /i18n/setlang/
    path("i18n/", include("django.conf.urls.i18n")),
    # Public pages: home, login, dashboard, … — صفحات الموقع العامة
    path("", include("pages.urls")),
    # Compliance: standards, assessments, reports — مسارات الامتثال والتقييم
    path("", include("compliance.urls")),
]

# Serve uploaded files in development only — ملفات الميديا أثناء التطوير (DEBUG)
# In production use nginx/S3/etc. (بالإنتاج خدمها من السيرفر أو التخزين السحابي)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
