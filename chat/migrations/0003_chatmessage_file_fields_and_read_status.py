# Generated manually for file upload and read status features

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0002_initial'),
    ]

    operations = [
        # Add read status fields
        migrations.AddField(
            model_name='chatmessage',
            name='is_read',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='read_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        # Add file upload fields
        migrations.AddField(
            model_name='chatmessage',
            name='file',
            field=models.FileField(blank=True, null=True, upload_to='chat_files/%Y/%m/%d/'),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='file_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='file_size',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='file_type',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        # Make content field optional (for file-only messages)
        migrations.AlterField(
            model_name='chatmessage',
            name='content',
            field=models.TextField(blank=True),
        ),
        # Add ordering
        migrations.AlterModelOptions(
            name='chatmessage',
            options={'ordering': ['timestamp']},
        ),
    ]

