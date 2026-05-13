from django.db import models
from django.contrib.auth.models import User


class Standard(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()

    def __str__(self):
        return self.name


class Domain(models.Model):
    standard = models.ForeignKey(Standard, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class Control(models.Model):
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    keywords = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.title


class AssessmentRun(models.Model):
    """
    One completed or in-progress assessment pass for a standard (e.g. per company, branch, or quarter).
    Answers (AssessmentResult) are scoped to a run so the same user can keep multiple assessments.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='assessment_runs',
    )
    standard = models.ForeignKey(
        Standard,
        on_delete=models.CASCADE,
        related_name='assessment_runs',
    )
    title = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.user} — {self.standard} — {self.title}'


class AssessmentResult(models.Model):
    STATUS_CHOICES = [
        ('compliant', 'Compliant'),
        ('partial', 'Partially Compliant'),
        ('non_compliant', 'Non-Compliant'),
    ]

    REVIEW_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('partial', 'Partial'),
        ('rejected', 'Rejected'),
    ]

    assessment_run = models.ForeignKey(
        AssessmentRun,
        on_delete=models.CASCADE,
        related_name='results',
    )
    control = models.ForeignKey(Control, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    notes = models.TextField(blank=True)
    report_file = models.FileField(upload_to='reports/', blank=True, null=True)
    evidence_file = models.FileField(upload_to='evidence/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    ai_score = models.FloatField(null=True, blank=True)
    review_status = models.CharField(
        max_length=20,
        choices=REVIEW_STATUS_CHOICES,
        default='pending',
    )
    review_status_admin_override = models.BooleanField(default=False)
    matched_keywords = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('assessment_run', 'control'),
                name='compliance_assessmentresult_unique_run_control',
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.control} - {self.status}"


class EvidenceValidationLog(models.Model):
    """
    Audit log row produced by the AI evidence analysis.

    BUG FIX: compliance/models.py had the OLD schema (only message + extra).
    The root models.py had the NEW AI fields but was never imported by the app.
    This consolidated version adds all AI fields to the compliance app model
    so that views.py can create logs that templates can display.

    After updating this file run:
        python manage.py makemigrations compliance
        python manage.py migrate
    """

    COMPLIANCE_CHOICES = [
        ("FC", "Full Compliance"),
        ("SC", "Substantial Compliance"),
        ("MC", "Minimal Compliance"),
        ("NC", "Non-Compliance"),
        ("NA", "Not Applicable"),
    ]

    CATEGORY_CHOICES = [
        ("C", "Commendation"),
        ("R", "Recommendation"),
    ]

    assessment_result = models.ForeignKey(
        AssessmentResult, on_delete=models.CASCADE, related_name="validation_logs"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # --- AI-generated fields ---
    quoted_standard = models.TextField(
        null=True, blank=True,
        help_text="Direct quote from the standards document",
    )
    analysis = models.TextField(
        null=True, blank=True,
        help_text="Independent AI evaluation of compliance",
    )
    compliance_level = models.CharField(
        max_length=2, choices=COMPLIANCE_CHOICES, default="NA"
    )
    justification = models.TextField(null=True, blank=True)
    recommendations = models.TextField(
        null=True, blank=True,
        help_text="Actionable suggestions for improvement",
    )
    result_category = models.CharField(
        max_length=1, choices=CATEGORY_CHOICES, default="R"
    )

    # Kept for backward-compatibility with the keyword-scoring pipeline
    message = models.TextField(blank=True)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_compliance_level_display()} — {self.assessment_result.control.title}"