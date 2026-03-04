from django.db import models
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