from django.db import models
import uuid
from apps.users.models import CustomUser
from apps.core.constants import OrganizationUserRole, SubscriptionPlan, OrganizationCategory

class Organization(models.Model):
    organization_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, blank=True, null=True)
    category = models.CharField(
        max_length=20,
        choices=OrganizationCategory.choices,
    )
    subscription_plan = models.CharField(
        max_length=20,
        choices=SubscriptionPlan.choices,
        default=SubscriptionPlan.FREE
    )
    contact_info = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name}"

class OrganizationUser(models.Model):
    organization_id = models.ForeignKey(Organization, on_delete=models.CASCADE)
    user_id = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    role = models.CharField(max_length=50, choices=OrganizationUserRole.choices)

    class Meta:
        unique_together = ('organization_id', 'user_id')

    def __str__(self):
        return f"{self.user_id.username} - {self.organization_id.name} - {self.role}"
