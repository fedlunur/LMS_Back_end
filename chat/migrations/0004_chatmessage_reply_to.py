# Generated manually for reply to message feature

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0003_chatmessage_file_fields_and_read_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatmessage',
            name='reply_to',
            field=models.ForeignKey(
                blank=True,
                help_text='The message this is replying to',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='replies',
                to='chat.chatmessage'
            ),
        ),
    ]

