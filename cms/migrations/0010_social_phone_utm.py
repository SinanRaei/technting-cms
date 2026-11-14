# Social profiles, phone and WhatsApp settings; utm_medium and utm_content on page views.

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0009_form_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='hit',
            name='medium',
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name='hit',
            name='content',
            field=models.CharField(blank=True, max_length=80),
        ),
    ]
