from django.db import models
from django.contrib.auth.models import User

# Create your models here.

class Standard(models.Model):
    # The name of the standard (e.g., NIST, ISO 27001)
    name = models.CharField(max_length=200)
    description = models.TextField()

    def __str__(self):
        return self.name


class Domain(models.Model):
    # The domain or category within the standard (e.g., Access Control, Risk Management)
    standard = models.ForeignKey(Standard, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class Control(models.Model):
    # The specific control or requirement within the domain (e.g., "Implement multi-factor authentication")
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()

    def __str__(self):
        return self.title
    
class AssessmentResult(models.Model):
    # The result of an assessment for a specific control, including the status (compliant, partially compliant, non-compliant), notes, and any evidence files.
    STATUS_CHOICES = [
        ('compliant', 'Compliant'),
        ('partial', 'Partially Compliant'),
        ('non_compliant', 'Non-Compliant'),
    ]

    control = models.ForeignKey(Control, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    notes = models.TextField(blank=True)
    evidence_file = models.FileField(upload_to='evidence/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.control} - {self.status}"