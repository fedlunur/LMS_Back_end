from django.db import migrations


def create_default_roles(apps, schema_editor):
    Role = apps.get_model('user_managment', 'Role')
    for name in ['student', 'teacher']:
        Role.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ('user_managment', '0006_alter_user_bio'),
    ]

    operations = [
        migrations.RunPython(create_default_roles, migrations.RunPython.noop),
    ]

