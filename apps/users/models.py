from django.db import models
import uuid
from django.contrib.auth.models import AbstractUser
from apps.core.constants import Currency, Language, Nationality, Gender

class TravelerType(models.Model):
    traveler_type_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    recommendation_model_version = models.IntegerField()

    def __str__(self):
        return f"{self.name}"
    

class CustomUser(AbstractUser):
    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    traveler_type_id = models.ForeignKey(
        TravelerType,
        null=True, blank=True,
        on_delete=models.SET_NULL
    )
    gender = models.CharField(max_length=1, choices=Gender.choices, default=Gender.UNSPECIFIED)
    nationality = models.CharField(max_length=2, choices=Nationality.choices)
    language = models.CharField(max_length=2, choices=Language.choices)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    recommendation_model_version = models.IntegerField(null=True, blank=True)

    email = models.EmailField(unique=True)

    def __str__(self):
        return self.username or self.email

class Interest(models.Model):
    interest_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name}"

class UserInterest(models.Model):
    user_id = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    interest_id = models.ForeignKey(Interest, on_delete=models.CASCADE)
    weight = models.DecimalField(max_digits=3, decimal_places=2)

    class Meta:
        unique_together = ('user_id', 'interest_id')

    def __str__(self):
        return f"{self.user_id.username} - {self.interest_id.name}"

class UserTravelerTypeHistory(models.Model):
    history_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    traveler_type_id = models.ForeignKey(TravelerType, on_delete=models.SET_NULL, null=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    recommendation_model_score = models.DecimalField(max_digits=5, decimal_places=4)
    recommendation_model_version = models.IntegerField()

    def __str__(self):
        return f"{self.user_id.username} - {self.traveler_type_id.name}"


