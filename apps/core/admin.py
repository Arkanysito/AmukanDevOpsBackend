from django.contrib import admin
from .models import Image

@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "filename",
        "content_type",
        "size_bytes",
        "bucket",
        "object_key",
        "status",
        "created_by",
        "created_at",
    )
    search_fields = ("filename", "object_key")
    list_filter = ("bucket", "content_type", "status", "created_at")
