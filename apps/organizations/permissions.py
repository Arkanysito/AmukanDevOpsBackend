from rest_framework.permissions import BasePermission
from apps.organizations.models import OrganizationUser

class OrganizationChecker(BasePermission):
    message = "Debes pertenecer a una organización para acceder."
    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return OrganizationUser.objects.filter(user_id=user).exists()