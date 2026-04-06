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
    assessment_result = models.ForeignKey(
        AssessmentResult,
        on_delete=models.CASCADE,
        related_name='validation_logs',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    message = models.TextField()
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.created_at}: {self.message[:50]}"
