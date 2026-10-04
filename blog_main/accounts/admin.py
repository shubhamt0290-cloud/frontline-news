from django.contrib import admin

from .models import LoginRecord


@admin.register(LoginRecord)
class LoginRecordAdmin(admin.ModelAdmin):

    list_display = (
        'user',
        'logged_in_at',
        'ip_address',
        'user_agent'
    )

    list_filter = ('logged_in_at',)

    search_fields = ('user__username', 'user__email', 'ip_address')

    readonly_fields = ('user', 'logged_in_at', 'ip_address', 'user_agent')

    def has_add_permission(self, request):
        return False
