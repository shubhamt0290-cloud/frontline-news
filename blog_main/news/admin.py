from django.contrib import admin

from .models import FetchLog, News  # added by shubham - removed duplicate import, added FetchLog


@admin.register(News)
class NewsAdmin(admin.ModelAdmin):

    list_display = (
        'title',
        'category',
        'source_type',  # added by shubham - manual post vs GNews
        'source_name',  # added by shubham
        'author',
        'created_by',  # added by shubham - owner of manual posts
        'published_at',  # added by shubham
        'is_active',  # added by shubham
    )

    list_filter = ('category', 'source_type', 'is_active', 'published_at')  # added by shubham - more filters

    search_fields = ('title', 'description', 'source_name', 'author')  # added by shubham - search source/author too

    list_editable = ('is_active',)  # added by shubham - hide/show straight from the list
    date_hierarchy = 'published_at'  # added by shubham - browse by date
    list_select_related = ('created_by',)  # added by shubham - avoid one query per row
    readonly_fields = ('external_url', 'created_at', 'updated_at')  # added by shubham
    actions = ('hide_articles', 'show_articles')  # added by shubham
    change_list_template = 'admin/news/news/change_list.html'  # added by shubham - adds "Fetch latest news" button

    # added by shubham - group the form fields
    fieldsets = (
        (None, {'fields': ('title', 'category', 'description', 'content', 'image')}),
        ('Byline & ownership', {'fields': ('author', 'created_by')}),
        ('Source', {'fields': ('source_type', 'source_name', 'external_url', 'published_at')}),
        ('Status', {'fields': ('is_active', 'created_at', 'updated_at')}),
    )

    def save_model(self, request, obj, form, change):  # added by shubham - admin-written posts belong to the admin
        if not change and obj.source_type == News.SOURCE_MANUAL and obj.created_by is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description='Hide selected articles')  # added by shubham
    def hide_articles(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} article(s) hidden.')

    @admin.action(description='Show selected articles')  # added by shubham
    def show_articles(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} article(s) visible again.')


# added by shubham - read-only history of every GNews call
@admin.register(FetchLog)
class FetchLogAdmin(admin.ModelAdmin):
    list_display = ('category', 'fetched_at', 'success', 'articles_received', 'articles_created', 'error')
    list_filter = ('success', 'category')
    readonly_fields = ('category', 'fetched_at', 'success', 'articles_received', 'articles_created', 'error')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
