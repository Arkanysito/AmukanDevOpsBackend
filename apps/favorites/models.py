from uuid import uuid4
from django.conf import settings
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class UserFavorite(models.Model):
    """
    Favorito de un usuario sobre un objeto genérico (servicio, evento, lugar, etc.).
    Solo columnas: user_fav_id, user_id, object_id, content_type.
    """
    user_fav_id = models.UUIDField(primary_key=True, default=uuid4, editable=False, db_column="user_fav_id")

    # FK a CustomUser → columna será user_id (por convención de Django)
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

    # Ayuda a acceder al objeto en Python (NO crea columnas extra)
    target = GenericForeignKey("content_type", "object_id")

    class Meta:
        verbose_name = "User Favorite"
        verbose_name_plural = "User Favorites"
        # No agrega columnas; solo reglas/índices
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
        return f"{self.user_id} ♥ {self.content_type.app_label}.{self.content_type.model}:{self.object_id}"