"""
Django admin for the compliance app — لوحة تحكم المسؤول للمعايير والتقييمات.

Registers models so staff can browse standards, controls, runs, and saved answers.
التسجيل هنا يخلّي فريق الإدارة يشوف ويعدّل البيانات من /admin بدون ما يكتب كود.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    AssessmentResult,
    AssessmentRun,
    Control,
    Domain,
    EvidenceValidationLog,
    Standard,
)


# -----------------------------------------------------------------------------
# Inlines — جداول داخل صفحة نموذج ثاني (nested)
# -----------------------------------------------------------------------------
class EvidenceValidationLogInline(admin.TabularInline):
    """
    Read-only history of automated evidence checks for one AssessmentResult.
    سجل تلقائي: ما نقدر نضيف يدوي من هنا؛ النظام يعبيه وقت تحليل الملف.
    """

    model = EvidenceValidationLog
    extra = 0
    can_delete = False
    readonly_fields = ("created_at", "message", "extra")

    def has_add_permission(self, request, obj=None):
        return False


# -----------------------------------------------------------------------------
# Taxonomy — هيكل المعيار: Standard → Domain → Control
# -----------------------------------------------------------------------------
@admin.register(Standard)
class StandardAdmin(admin.ModelAdmin):
    """Top-level framework (e.g. ISO 27001) — أعلى مستوى: اسم المعيار والوصف."""

    search_fields = ("name",)


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    """Chapter / category inside a standard — مجال داخل المعيار (فصل/تصنيف)."""

    list_display = ("name", "standard")
    list_filter = ("standard",)
    search_fields = ("name", "standard__name")
    autocomplete_fields = ("standard",)


@admin.register(Control)
class ControlAdmin(admin.ModelAdmin):
    """Single requirement row + optional keywords for AI evidence scoring — بند + كلمات مفتاح للمطابقة."""

    list_display = ("title", "domain", "keywords_preview")
    list_filter = ("domain",)
    search_fields = ("title", "description")
    autocomplete_fields = ("domain",)

    @admin.display(description=_("Keywords"))
    def keywords_preview(self, obj):
        """Short list in changelist — عرض سريع في الجدول بدل JSON كامل."""
        kws = obj.keywords or []
        if not kws:
            return "—"
        tail = "…" if len(kws) > 5 else ""
        return ", ".join(str(k) for k in kws[:5]) + tail


# -----------------------------------------------------------------------------
# Assessments — جلسات التقييم وإجابات المستخدم
# -----------------------------------------------------------------------------
@admin.register(AssessmentRun)
class AssessmentRunAdmin(admin.ModelAdmin):
    """
    One user’s “attempt” or snapshot for a standard — جلسة تقييم لمستخدم على معيار معيّن.
    raw_id_fields = faster pickers if you have many users (أخف لو عندك آلاف المستخدمين).
    """

    list_display = ("title", "standard", "user", "updated_at")
    list_filter = ("standard",)
    search_fields = ("title", "user__username", "standard__name")
    raw_id_fields = ("user", "standard")


@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
    """
    Saved answer per control inside a run — نتيجة لكل بند (حالة + ملاحظات + دليل).
    Inline shows validation logs without opening another admin page.
    """

    list_display = (
        "assessment_run",
        "user",
        "control",
        "status",
        "ai_score",
        "review_status",
        "review_status_admin_override",
        "created_at",
    )
    list_filter = ("status", "review_status", "review_status_admin_override")
    search_fields = ("user__username", "control__title", "notes", "assessment_run__title")
    readonly_fields = ("created_at", "matched_keywords")
    raw_id_fields = ("user", "control", "assessment_run")
    inlines = (EvidenceValidationLogInline,)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "assessment_run",
                    "user",
                    "control",
                    "status",
                    "notes",
                    "evidence_file",
                ),
            },
        ),
        (
            _("AI evidence review"),
            {
                "fields": (
                    "ai_score",
                    "review_status",
                    "review_status_admin_override",
                    "matched_keywords",
                ),
            },
        ),
        (
            _("Meta"),
            {
                "fields": ("created_at",),
            },
        ),
    )


# -----------------------------------------------------------------------------
# Audit log — سجل النظام (append-only من واجهة الأدمن)
# -----------------------------------------------------------------------------
@admin.register(EvidenceValidationLog)
class EvidenceValidationLogAdmin(admin.ModelAdmin):
    """
    Immutable-style log rows for debugging scoring — للمراجعة فقط، مو مكان إدخال يدوي.
    """

    list_display = ("created_at", "assessment_result", "message")
    list_filter = ("created_at",)
    search_fields = ("message",)
    readonly_fields = ("created_at", "assessment_result", "message", "extra")

    def has_add_permission(self, request):
        """Hide “Add” — ما في زر إضافة؛ السجلات تنخلق من الخدمة البرمجية."""
        return False
