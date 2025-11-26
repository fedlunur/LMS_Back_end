from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('courses', '0038_fix_vcr_unique_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='requires_final_assessment',
            field=models.BooleanField(
                default=False,
                help_text='If enabled, student must pass the final assessment before certificate is issued.'
            ),
        ),
    ]


