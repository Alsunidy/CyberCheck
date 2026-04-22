from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('compliance', '0004_assessment_run'),
    ]

    operations = [
        migrations.AddField(
            model_name='assessmentresult',
            name='report_file',
            field=models.FileField(blank=True, null=True, upload_to='reports/'),
        ),
    ]
