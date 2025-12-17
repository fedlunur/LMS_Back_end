# Generated manually for H5P integration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0047_alter_finalcourseassessment_max_attempts'),
    ]

    operations = [
        migrations.AddField(
            model_name='videolesson',
            name='h5p_iframe',
            field=models.TextField(blank=True, help_text='H5P iframe HTML code including script tag'),
        ),
        migrations.AddField(
            model_name='quizlesson',
            name='h5p_iframe',
            field=models.TextField(blank=True, help_text='H5P iframe HTML code including script tag. If provided, quiz questions are not required.'),
        ),
    ]

