import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Organization',
            fields=[
                ('organization_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('email', models.EmailField(blank=True, max_length=255, null=True)),
                ('category', models.CharField(choices=[('EDUCATION', 'Educación'), ('HEALTHCARE', 'Salud'), ('NONPROFIT', 'ONG'), ('GOVERNMENT', 'Gobierno'), ('PRIVATE', 'Privada'), ('OTHER', 'Otro')], max_length=20)),
                ('subscription_plan', models.CharField(choices=[('FREE', 'Free'), ('BASIC', 'Basic'), ('PRO', 'Pro'), ('ENTERPRISE', 'Enterprise')], default='FREE', max_length=20)),
                ('contact_info', models.JSONField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='OrganizationUser',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('ADMIN', 'Administrator'), ('STAFF', 'Staff'), ('MANAGER', 'Manager'), ('VIEWER', 'Viewer')], max_length=50)),
                ('organization_id', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='organizations.organization')),
                ('user_id', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('organization_id', 'user_id')},
            },
        ),
    ]
