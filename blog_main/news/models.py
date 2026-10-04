import re  # added by shubham - clean truncated API content

from django.conf import settings  # added by shubham - for the created_by user link
from django.db import models
from django.urls import reverse
from django.utils import timezone  # added by shubham - default for published_at


class News(models.Model):

    CATEGORY_CHOICES = [
        ('General', 'General'),  # added by shubham - GNews "general" category
        ('Sports', 'Sports'),  # added by shubham - GNews "sports" category
        ('Cricket', 'Cricket'),
        ('Football', 'Football'),
        ('Basketball', 'Basketball'),
        ('Technology', 'Technology'),
        ('Other', 'Other'),
    ]

    # added by shubham - where an article came from
    SOURCE_MANUAL = 'manual'
    SOURCE_API = 'api'
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, 'Written on site'),
        (SOURCE_API, 'GNews API'),
    ]

    title = models.CharField(max_length=300)  # added by shubham - 200 -> 300, API headlines can be long

    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        db_index=True,  # added by shubham - category pages filter on this
    )

    description = models.TextField()

    content = models.TextField()

    image = models.URLField(max_length=1000, blank=True)  # added by shubham - API image URLs can exceed 200 chars

    author = models.CharField(
        max_length=100,
        default='Admin'
    )

    # added by shubham - the site user who owns a manual post (empty for API articles)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='news_posts',
    )

    # added by shubham - fields for articles fetched from GNews
    source_type = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=SOURCE_MANUAL, db_index=True)
    source_name = models.CharField(max_length=200, blank=True)
    external_url = models.URLField(max_length=1000, unique=True, null=True, blank=True)
    published_at = models.DateTimeField(default=timezone.now, db_index=True)
    is_active = models.BooleanField(default=True, help_text='Untick to hide this article from the site.')
    updated_at = models.DateTimeField(auto_now=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-published_at', '-id']  # added by shubham - newest by publish time (API articles have real publish dates)
        verbose_name = 'news article'
        verbose_name_plural = 'news'

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('news:detail', args=[self.pk])

    # added by shubham - helpers used by templates and permission checks
    @property
    def is_from_api(self):
        return self.source_type == self.SOURCE_API

    @property
    def display_content(self):
        """GNews free plan truncates content with a trailing '[1234 chars]' marker; hide it."""
        return re.sub(r'\s*\[\+?\d+ chars\]\s*$', '', self.content)

    def can_edit(self, user):
        """Only the owner or staff may edit/delete, and never API articles."""
        if self.is_from_api or not user.is_authenticated:
            return False
        return user.is_staff or self.created_by_id == user.pk


# added by shubham - one row per GNews call, so admins can see what happened and we can throttle
class FetchLog(models.Model):
    category = models.CharField(max_length=50, db_index=True)
    fetched_at = models.DateTimeField(auto_now_add=True, db_index=True)
    success = models.BooleanField(default=False)
    articles_received = models.PositiveIntegerField(default=0)
    articles_created = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ['-fetched_at', '-id']

    def __str__(self):
        status = 'ok' if self.success else 'failed'
        return f'{self.category} {status} at {self.fetched_at:%Y-%m-%d %H:%M}'
