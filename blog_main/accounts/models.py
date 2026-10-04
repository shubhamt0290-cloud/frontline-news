from django.conf import settings
from django.db import models


class LoginRecord(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='login_records'
    )
    logged_in_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-logged_in_at', '-id']

    def __str__(self):
        return f'{self.user} at {self.logged_in_at:%Y-%m-%d %H:%M}'
