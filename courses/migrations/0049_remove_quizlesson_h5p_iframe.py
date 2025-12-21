# Generated migration to remove h5p_iframe from QuizLesson

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0048_add_h5p_iframe_fields'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='quizlesson',
            name='h5p_iframe',
        ),
    ]

