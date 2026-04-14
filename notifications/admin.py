from django.contrib import admin
from .models import Activity


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'title', 'actor_name', 'target_name', 'visibility', 'created_at')
    list_filter = ('event_type', 'visibility', 'created_at')
    search_fields = ('title', 'actor_name', 'target_name', 'actor_id', 'target_id')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
