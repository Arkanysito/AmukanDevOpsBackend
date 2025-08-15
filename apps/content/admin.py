from django.contrib import admin
from .models import Tag, ObjectTag

class TagAdmin(admin.ModelAdmin):
    list_display = ('name',)

class ObjectTagAdmin(admin.ModelAdmin):
    list_display = ('tag_name', 'object_content_type')

    def tag_name(self, obj):
        return obj.tag_id.name
    tag_name.short_description = 'Tag'

    def object_content_type(self, obj):
        return obj.content_type.model
    object_content_type.short_description = "Object Type"

admin.site.register(Tag, TagAdmin)
admin.site.register(ObjectTag, ObjectTagAdmin)