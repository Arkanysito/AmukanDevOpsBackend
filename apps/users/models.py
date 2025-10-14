from django.db import models
import uuid
from django.contrib.auth.models import AbstractUser
from apps.core.constants import Currency, Language, Nationality, Gender
from uuid import uuid4
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    traveler_type_id = models.ForeignKey(
        TravelerType,
        null=True, blank=True,
        on_delete=models.SET_NULL
    )
    gender = models.CharField(max_length=1, choices=Gender.choices, default=Gender.UNSPECIFIED, null=True, blank=True,)
    nationality = models.CharField(max_length=2, choices=Nationality.choices, default=Nationality.CL, null=True, blank=True,)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.ES, null=True, blank=True,)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.CLP, null=True, blank=True,)
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

class UserFavorite(models.Model):
    """
    Favorito de un usuario sobre un objeto genérico (servicio, evento, lugar, etc.).
    Solo columnas: user_fav_id, user_id, object_id, content_type.
    """
    user_fav_id = models.UUIDField(primary_key=True, default=uuid4, editable=False, db_column="user_fav_id")

    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorites",
        db_index=True,
    )

    # ID del objeto destino (UUID)
    object_id = models.UUIDField(db_column="object_id")

    # FK a ContentType; forzamos nombre de columna EXACTO "content_type"
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        db_column="content_type",
    )


    target = GenericForeignKey("content_type", "object_id")

    class Meta:
        db_table = "users_userfavorite"
        verbose_name = "User Favorite"
        verbose_name_plural = "User Favorites"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "content_type", "object_id"],
                name="uq_userfavorite_user_ct_oid",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "content_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} fav {self.content_type.app_label}.{self.content_type.model}:{self.object_id}"
