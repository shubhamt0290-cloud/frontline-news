from django.contrib import messages  # added by shubham - flash messages after CRUD / refresh
from django.contrib.admin.views.decorators import staff_member_required  # added by shubham - staff-only refresh
from django.contrib.auth.decorators import login_required  # added by shubham - my posts page
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin  # added by shubham - CRUD permissions
from django.core.paginator import Paginator  # added by shubham - paginate long lists
from django.db.models import Q  # added by shubham - search across several fields
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy  # added by shubham
from django.utils.http import url_has_allowed_host_and_scheme  # added by shubham - safe redirect after refresh
from django.views.decorators.http import require_POST  # added by shubham
from django.views.generic import CreateView, DeleteView, UpdateView  # added by shubham - CRUD views

from . import services  # added by shubham - GNews refresh
from .forms import NewsForm  # added by shubham
from .models import News

PER_PAGE = 12  # added by shubham - cards per page on list pages

# Homepage sections and the model categories that feed each one.
SECTIONS = {
    'news': ['General', 'Other'],  # added by shubham - General (from GNews) now feeds the News section
    'sports': ['Sports', 'Cricket', 'Football', 'Basketball'],  # added by shubham - GNews Sports added
    'tech': ['Technology'],
}

# added by shubham - a category page also shows its sub-categories (e.g. Sports includes Cricket)
CATEGORY_GROUPS = {
    'General': ['General', 'Other'],
    'Sports': ['Sports', 'Cricket', 'Football', 'Basketball'],
}

VALID_CATEGORIES = {value for value, _ in News.CATEGORY_CHOICES}
CATEGORY_LOOKUP = {value.lower(): value for value in VALID_CATEGORIES}  # added by shubham - case-insensitive URLs


def visible_news():  # added by shubham - hidden articles never reach public pages
    return News.objects.filter(is_active=True)


def paginate(request, queryset):  # added by shubham - shared pagination helper
    return Paginator(queryset, PER_PAGE).get_page(request.GET.get('page'))


def home(request):
    if services.should_auto_refresh():  # added by shubham - fetch from GNews only when stored news is stale
        services.refresh_if_stale()
    latest = list(visible_news()[:4])  # added by shubham - only active articles
    context = {
        'hero': latest[0] if latest else None,
        'side_stories': latest[1:],
        'last_updated': services.last_updated(),  # added by shubham - "Updated x ago" label
        'api_configured': services.api_configured(),  # added by shubham - staff hint when key is missing
    }
    for section, categories in SECTIONS.items():
        context[f'{section}_stories'] = visible_news().filter(category__in=categories)[:6]  # added by shubham - 3 -> 6 cards
    return render(request, 'home.html', context)


def detail(request, pk):
    article = get_object_or_404(News, pk=pk)
    if not article.is_active and not request.user.is_staff:  # added by shubham - hidden articles 404 for the public
        raise Http404('Article not found')
    related = visible_news().filter(category=article.category).exclude(pk=pk)[:3]  # added by shubham - only active
    return render(request, 'news/detail.html', {
        'article': article,
        'related': related,
        'can_edit': article.can_edit(request.user),  # added by shubham - show Edit/Delete only to owner/staff
        'share_url': request.build_absolute_uri(article.get_absolute_url()),  # added by shubham - full link for share buttons
    })


def category(request, category):
    category = CATEGORY_LOOKUP.get(category.lower())  # added by shubham - /category/sports/ works as well as /Sports/
    if category is None:
        raise Http404('Unknown category')
    if services.should_auto_refresh() and category in services.API_CATEGORIES:  # added by shubham
        services.refresh_if_stale([category])
    categories = CATEGORY_GROUPS.get(category, [category])  # added by shubham
    return render(request, 'news/category.html', {
        'category': category,
        'page_obj': paginate(request, visible_news().filter(category__in=categories)),  # added by shubham - paginated
        'last_updated': services.last_updated(),  # added by shubham
    })


# added by shubham - search across manual posts and API articles
def search(request):
    query = request.GET.get('q', '').strip()[:100]
    selected = CATEGORY_LOOKUP.get(request.GET.get('category', '').lower(), '')
    page_obj = None
    if query:
        results = visible_news().filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(content__icontains=query)
            | Q(source_name__icontains=query)
        )
        if selected:
            results = results.filter(category__in=CATEGORY_GROUPS.get(selected, [selected]))
        page_obj = paginate(request, results)
    return render(request, 'news/search.html', {
        'query': query,
        'selected': selected,
        'categories': [value for value, _ in News.CATEGORY_CHOICES],
        'page_obj': page_obj,
    })


# added by shubham - the logged-in user's own posts
@login_required
def my_posts(request):
    return render(request, 'news/my_posts.html', {
        'page_obj': paginate(request, News.objects.filter(created_by=request.user)),
    })


# added by shubham - staff button to force a GNews refresh now
@staff_member_required
@require_POST
def refresh(request):
    if not services.api_configured():
        messages.error(request, 'GNEWS_API_KEY is not set in .env, so live news is off.')
    else:
        logs = services.refresh_if_stale(force=True)
        if not logs:
            messages.info(request, 'A refresh is already running. Try again in a minute.')
        for log in logs:
            if log.success:
                messages.success(request, f'{log.category}: {log.articles_created} new articles.')
            else:
                messages.error(request, f'{log.category}: {log.error}')
    next_url = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = 'home'
    return redirect(next_url)


# added by shubham - CRUD: any logged-in user can write; only owner or staff can edit/delete
class OwnerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.get_object().can_edit(self.request.user)


class NewsCreateView(LoginRequiredMixin, CreateView):
    model = News
    form_class = NewsForm
    template_name = 'news/form.html'

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.author = self.request.user.get_full_name() or self.request.user.username
        form.instance.source_type = News.SOURCE_MANUAL
        messages.success(self.request, 'Your post has been published.')
        return super().form_valid(form)


class NewsUpdateView(OwnerRequiredMixin, UpdateView):
    model = News
    form_class = NewsForm
    template_name = 'news/form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Post updated.')
        return super().form_valid(form)


class NewsDeleteView(OwnerRequiredMixin, DeleteView):
    model = News
    template_name = 'news/confirm_delete.html'
    success_url = reverse_lazy('news:my_posts')

    def form_valid(self, form):
        messages.success(self.request, 'Post deleted.')
        return super().form_valid(form)
