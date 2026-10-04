from datetime import timedelta  # added by shubham
from io import StringIO  # added by shubham - capture command output
from unittest import mock  # added by shubham - fake GNews responses

import requests  # added by shubham
from django.contrib.auth.models import User  # added by shubham
from django.core.cache import cache  # added by shubham
from django.core.management import call_command  # added by shubham
from django.test import TestCase, override_settings  # added by shubham - override_settings
from django.urls import reverse
from django.utils import timezone  # added by shubham

from . import services  # added by shubham
from .models import FetchLog, News  # added by shubham - FetchLog


def make_news(title, category='Other'):
    return News.objects.create(
        title=title,
        category=category,
        description=f'{title} summary',
        content=f'{title} body',
    )


class HomeViewTests(TestCase):

    def test_home_renders_without_articles(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['hero'])

    def test_home_groups_articles_into_sections(self):
        cricket = make_news('Cricket story', 'Cricket')
        tech = make_news('Tech story', 'Technology')
        other = make_news('Other story', 'Other')
        response = self.client.get(reverse('home'))
        self.assertEqual(response.context['hero'], other)
        self.assertEqual(list(response.context['sports_stories']), [cricket])
        self.assertEqual(list(response.context['tech_stories']), [tech])
        self.assertEqual(list(response.context['news_stories']), [other])


class DetailViewTests(TestCase):

    def test_detail_shows_article(self):
        article = make_news('Big story')
        response = self.client.get(article.get_absolute_url())
        self.assertContains(response, 'Big story body')

    def test_missing_article_is_404(self):
        response = self.client.get(reverse('news:detail', args=[999]))
        self.assertEqual(response.status_code, 404)
        


class CategoryViewTests(TestCase):

    def test_category_lists_only_that_category(self):
        make_news('Football story', 'Football')
        make_news('Tech story', 'Technology')
        response = self.client.get(reverse('news:category', args=['Football']))
        self.assertContains(response, 'Football story')
        self.assertNotContains(response, 'Tech story')

    def test_unknown_category_is_404(self):
        response = self.client.get(reverse('news:category', args=['Nope']))
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# added by shubham - tests for rendered pages, search, CRUD permissions and GNews
# ---------------------------------------------------------------------------

def make_api_news(title, category='General', url=None, **extra):  # added by shubham
    fields = {
        'title': title, 'category': category, 'description': f'{title} summary', 'content': f'{title} body',
        'source_type': News.SOURCE_API, 'source_name': 'Example Times',
        'external_url': url or f'https://example.com/{title.replace(" ", "-")}',
    }
    fields.update(extra)
    return News.objects.create(**fields)


def gnews_article(n, **overrides):  # added by shubham - one article in GNews' response shape
    article = {
        'title': f'Headline {n}',
        'description': f'Summary {n}',
        'content': f'Body {n}... [1520 chars]',
        'url': f'https://news.example.com/story-{n}',
        'image': f'https://img.example.com/{n}.jpg',
        'publishedAt': '2026-10-04T09:30:00Z',
        'source': {'name': 'Example Wire', 'url': 'https://news.example.com'},
    }
    article.update(overrides)
    return article


def fake_response(status=200, payload=None):  # added by shubham
    response = mock.Mock(status_code=status)
    response.json.return_value = payload if payload is not None else {'articles': []}
    return response


class RenderedPageTests(TestCase):  # added by shubham - the old homepage was hardcoded; check real HTML now

    def test_home_shows_real_article_titles(self):
        make_news('Rendered general story', 'General')
        make_api_news('Rendered tech story', 'Technology')
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Rendered general story')
        self.assertContains(response, 'Rendered tech story')
        self.assertNotContains(response, 'Headline goes here')

    def test_hidden_article_is_not_public(self):
        article = make_news('Secret story')
        article.is_active = False
        article.save()
        self.assertNotContains(self.client.get(reverse('home')), 'Secret story')
        self.assertEqual(self.client.get(article.get_absolute_url()).status_code, 404)
        User.objects.create_user('boss', password='pw', is_staff=True)
        self.client.login(username='boss', password='pw')
        self.assertEqual(self.client.get(article.get_absolute_url()).status_code, 200)

    def test_category_url_is_case_insensitive(self):
        make_news('Football story', 'Football')
        self.assertContains(self.client.get('/news/category/football/'), 'Football story')

    def test_sports_page_includes_sub_categories(self):
        make_news('Cricket story', 'Cricket')
        make_api_news('API sports story', 'Sports')
        response = self.client.get(reverse('news:category', args=['Sports']))
        self.assertContains(response, 'Cricket story')
        self.assertContains(response, 'API sports story')

    def test_api_article_links_to_source_and_hides_truncation_marker(self):
        article = make_api_news('Linked story', content='Some text... [1520 chars]')
        response = self.client.get(article.get_absolute_url())
        self.assertContains(response, article.external_url)
        self.assertNotContains(response, '[1520 chars]')

    def test_category_pagination(self):
        for i in range(15):
            make_news(f'Tech {i}', 'Technology')
        response = self.client.get(reverse('news:category', args=['Technology']))
        self.assertEqual(len(response.context['page_obj']), 12)
        response = self.client.get(reverse('news:category', args=['Technology']) + '?page=2')
        self.assertEqual(len(response.context['page_obj']), 3)

    def test_load_more_markup(self):  # added by shubham - hooks used by static/js/load-more.js
        for i in range(15):
            make_news(f'Tech {i}', 'Technology')
        response = self.client.get(reverse('news:category', args=['Technology']))
        self.assertContains(response, 'data-list')
        self.assertContains(response, 'class="next" href="?page=2"')
        self.assertContains(response, 'js/load-more.js')
        response = self.client.get(reverse('news:search'), {'q': 'tech'})
        self.assertContains(response, 'class="next" href="?q=tech&page=2"')


class SearchTests(TestCase):  # added by shubham

    def test_search_matches_title_and_source(self):
        make_news('Monsoon arrives early', 'General')
        make_api_news('Chip shortage eases', 'Technology')
        make_news('Unrelated story', 'Other')
        response = self.client.get(reverse('news:search'), {'q': 'monsoon'})
        self.assertContains(response, 'Monsoon arrives early')
        self.assertNotContains(response, 'Unrelated story')
        response = self.client.get(reverse('news:search'), {'q': 'Example Times'})
        self.assertContains(response, 'Chip shortage eases')

    def test_search_category_filter(self):
        make_news('Election football match', 'Football')
        make_news('Election results', 'General')
        response = self.client.get(reverse('news:search'), {'q': 'election', 'category': 'Sports'})
        self.assertContains(response, 'Election football match')
        self.assertNotContains(response, 'Election results')

    def test_empty_search_shows_prompt(self):
        make_news('Anything')
        response = self.client.get(reverse('news:search'))
        self.assertIsNone(response.context['page_obj'])
        self.assertContains(response, 'Type something')

    def test_hidden_articles_not_searchable(self):
        make_news('Hidden monsoon story')
        News.objects.update(is_active=False)
        response = self.client.get(reverse('news:search'), {'q': 'monsoon'})
        self.assertNotContains(response, 'Hidden monsoon story')


class CrudPermissionTests(TestCase):  # added by shubham - owner/staff rules

    def setUp(self):
        self.owner = User.objects.create_user('owner', password='pw', first_name='Asha')
        self.other = User.objects.create_user('other', password='pw')
        self.staff = User.objects.create_user('staff', password='pw', is_staff=True)
        self.post = News.objects.create(
            title='Owner post', category='General', description='d', content='c', created_by=self.owner,
        )
        self.form_data = {
            'title': 'New title', 'category': 'Technology',
            'description': 'Short summary', 'content': 'Full text', 'image': '',
        }

    def test_logged_out_user_is_sent_to_login(self):
        response = self.client.get(reverse('news:create'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('news:create')}")

    def test_create_sets_owner_and_author(self):
        self.client.login(username='other', password='pw')
        response = self.client.post(reverse('news:create'), self.form_data)
        post = News.objects.get(title='New title')
        self.assertRedirects(response, post.get_absolute_url())
        self.assertEqual(post.created_by, self.other)
        self.assertEqual(post.author, 'other')
        self.assertEqual(post.source_type, News.SOURCE_MANUAL)

    def test_create_validates_required_fields(self):
        self.client.login(username='other', password='pw')
        response = self.client.post(reverse('news:create'), {'title': ''})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'errorlist')

    def test_owner_can_edit_and_delete(self):
        self.client.login(username='owner', password='pw')
        self.client.post(reverse('news:edit', args=[self.post.pk]), self.form_data)
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, 'New title')
        response = self.client.post(reverse('news:delete', args=[self.post.pk]))
        self.assertRedirects(response, reverse('news:my_posts'))
        self.assertFalse(News.objects.filter(pk=self.post.pk).exists())

    def test_other_user_gets_403(self):
        self.client.login(username='other', password='pw')
        self.assertEqual(self.client.get(reverse('news:edit', args=[self.post.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('news:delete', args=[self.post.pk])).status_code, 403)
        self.assertTrue(News.objects.filter(pk=self.post.pk).exists())

    def test_staff_can_edit_any_manual_post(self):
        self.client.login(username='staff', password='pw')
        self.client.post(reverse('news:edit', args=[self.post.pk]), self.form_data)
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, 'New title')

    def test_api_articles_cannot_be_edited_on_site(self):
        article = make_api_news('Wire story')
        self.client.login(username='staff', password='pw')
        self.assertEqual(self.client.get(reverse('news:edit', args=[article.pk])).status_code, 403)

    def test_edit_buttons_only_for_owner(self):
        self.client.login(username='other', password='pw')
        self.assertNotContains(self.client.get(self.post.get_absolute_url()), reverse('news:edit', args=[self.post.pk]))
        self.client.login(username='owner', password='pw')
        self.assertContains(self.client.get(self.post.get_absolute_url()), reverse('news:edit', args=[self.post.pk]))

    def test_my_posts_lists_only_own_posts(self):
        News.objects.create(title='Someone else', category='General', description='d', content='c', created_by=self.other)
        self.client.login(username='owner', password='pw')
        response = self.client.get(reverse('news:my_posts'))
        self.assertContains(response, 'Owner post')
        self.assertNotContains(response, 'Someone else')


@override_settings(GNEWS_API_KEY='secret-test-key')
class GNewsServiceTests(TestCase):  # added by shubham - every HTTP call is mocked

    def setUp(self):
        cache.clear()

    @mock.patch('news.services.requests.get')
    def test_fetch_saves_articles(self, get):
        get.return_value = fake_response(payload={'articles': [gnews_article(1), gnews_article(2)]})
        log = services.fetch_category('Technology')
        self.assertTrue(log.success)
        self.assertEqual(log.articles_created, 2)
        article = News.objects.get(external_url='https://news.example.com/story-1')
        self.assertEqual(article.category, 'Technology')
        self.assertEqual(article.source_type, News.SOURCE_API)
        self.assertEqual(article.source_name, 'Example Wire')
        self.assertEqual(article.published_at.year, 2026)
        self.assertEqual(get.call_args.kwargs['params']['category'], 'technology')
        self.assertEqual(get.call_args.kwargs['timeout'], services.REQUEST_TIMEOUT)

    @mock.patch('news.services.requests.get')
    def test_duplicates_are_updated_not_duplicated(self, get):
        get.return_value = fake_response(payload={'articles': [gnews_article(1)]})
        services.fetch_category('General')
        get.return_value = fake_response(payload={'articles': [gnews_article(1, title='Updated headline')]})
        log = services.fetch_category('Sports')
        self.assertEqual(log.articles_created, 0)
        self.assertEqual(News.objects.count(), 1)
        article = News.objects.get()
        self.assertEqual(article.title, 'Updated headline')
        self.assertEqual(article.category, 'General')  # first category is kept

    @mock.patch('news.services.requests.get')
    def test_same_headline_with_different_url_is_skipped(self, get):  # added by shubham
        get.return_value = fake_response(payload={'articles': [
            gnews_article(1), gnews_article(2, title='Headline 1', url='https://other.example.com/copy'),
        ]})
        log = services.fetch_category('General')
        self.assertEqual(log.articles_created, 1)
        self.assertEqual(News.objects.count(), 1)

    @mock.patch('news.services.requests.get')
    def test_admin_hidden_article_stays_hidden_after_refetch(self, get):
        get.return_value = fake_response(payload={'articles': [gnews_article(1)]})
        services.fetch_category('General')
        News.objects.update(is_active=False)
        services.fetch_category('General')
        self.assertFalse(News.objects.get().is_active)

    @mock.patch('news.services.requests.get')
    def test_bad_articles_are_skipped(self, get):
        get.return_value = fake_response(payload={'articles': [
            gnews_article(1, url=''), gnews_article(2, title=None), gnews_article(3, image=None, description=None),
        ]})
        log = services.fetch_category('General')
        self.assertEqual(log.articles_created, 1)
        self.assertEqual(News.objects.get().image, '')

    @mock.patch('news.services.requests.get')
    def test_http_errors_are_logged_not_raised(self, get):
        for status, text in [(401, 'API key'), (403, 'limit'), (429, 'Too many'), (500, 'HTTP 500')]:
            get.return_value = fake_response(status=status)
            log = services.fetch_category('General')
            self.assertFalse(log.success)
            self.assertIn(text, log.error)

    @mock.patch('news.services.requests.get')
    def test_network_errors_never_leak_the_key(self, get):
        get.side_effect = requests.ConnectionError('failed for https://gnews.io/?apikey=secret-test-key')
        log = services.fetch_category('General')
        self.assertFalse(log.success)
        self.assertNotIn('secret-test-key', log.error)
        get.side_effect = requests.Timeout()
        self.assertIn('in time', services.fetch_category('General').error)

    @mock.patch('news.services.requests.get')
    def test_bad_json_is_handled(self, get):
        response = fake_response()
        response.json.side_effect = ValueError('not json')
        get.return_value = response
        self.assertIn('non-JSON', services.fetch_category('General').error)
        get.return_value = fake_response(payload={'errors': ['nope']})
        self.assertIn('no article list', services.fetch_category('General').error)

    @mock.patch('news.services.requests.get')
    def test_refresh_only_calls_api_when_stale(self, get):
        get.return_value = fake_response(payload={'articles': [gnews_article(1)]})
        services.refresh_if_stale()
        self.assertEqual(get.call_count, 3)  # General, Sports, Technology
        cache.clear()
        services.refresh_if_stale()
        self.assertEqual(get.call_count, 3)  # still fresh: no new calls
        FetchLog.objects.update(fetched_at=timezone.now() - timedelta(minutes=61))
        cache.clear()
        services.refresh_if_stale()
        self.assertEqual(get.call_count, 6)

    @mock.patch('news.services.requests.get')
    def test_failed_fetch_waits_before_retrying(self, get):
        get.return_value = fake_response(status=500)
        services.refresh_if_stale(['General'])
        cache.clear()
        services.refresh_if_stale(['General'])
        self.assertEqual(get.call_count, 1)

    @mock.patch('news.services.requests.get')
    def test_lock_prevents_parallel_fetches(self, get):
        cache.add(services.LOCK_KEY, True)
        self.assertEqual(services.refresh_if_stale(), [])
        get.assert_not_called()

    @mock.patch('news.services.requests.get')
    @override_settings(GNEWS_API_KEY='')
    def test_no_key_means_no_calls(self, get):
        self.assertEqual(services.refresh_if_stale(), [])
        get.assert_not_called()

    def test_old_api_articles_are_pruned(self):
        make_api_news('Old story', published_at=timezone.now() - timedelta(days=40))
        make_api_news('Fresh story')
        make_news('Old manual post')
        News.objects.filter(title='Old manual post').update(published_at=timezone.now() - timedelta(days=400))
        services.prune_old_articles()
        self.assertEqual(
            sorted(News.objects.values_list('title', flat=True)), ['Fresh story', 'Old manual post'],
        )

    @mock.patch('news.services.requests.get')
    @override_settings(NEWS_AUTO_REFRESH=True)
    def test_homepage_triggers_refresh_when_enabled(self, get):
        get.return_value = fake_response(payload={'articles': [gnews_article(7)]})
        response = self.client.get(reverse('home'))
        self.assertEqual(get.call_count, 3)
        self.assertContains(response, 'Headline 7')

    @mock.patch('news.services.requests.get')
    def test_fetch_news_command(self, get):
        get.return_value = fake_response(payload={'articles': [gnews_article(1)]})
        out = StringIO()
        call_command('fetch_news', '--category', 'Sports', stdout=out)
        self.assertIn('Sports: 1 received, 1 new', out.getvalue())
        out = StringIO()
        call_command('fetch_news', '--category', 'Sports', stdout=out)
        self.assertIn('already fresh', out.getvalue())


class ShareAndContactTests(TestCase):  # added by shubham - share buttons + footer email

    def test_detail_has_share_buttons_with_full_url(self):
        article = make_news('Share me & you')
        response = self.client.get(article.get_absolute_url())
        full_url = f'http%3A%2F%2Ftestserver%2Fnews%2F{article.pk}%2F'
        self.assertContains(response, f'https://wa.me/?text=Share%20me%20%26%20you%20{full_url}')
        self.assertContains(response, f'https://twitter.com/intent/tweet?text=Share%20me%20%26%20you&amp;url={full_url}')
        self.assertContains(response, f'data-url="http://testserver/news/{article.pk}/"')

    @override_settings(CONTACT_EMAIL='shubhamt290@gmail.com')
    def test_footer_shows_contact_email(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'href="mailto:shubhamt290@gmail.com"')

    @override_settings(CONTACT_PHONE='+91 98765 43210')  # added by shubham
    def test_footer_shows_phone_as_call_link(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, '<a href="tel:+919876543210">+91 98765 43210</a>', html=True)

    @override_settings(LINKEDIN_URL='https://www.linkedin.com/in/shubham-tiwari-1729712b8')  # added by shubham
    def test_footer_shows_linkedin(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'href="https://www.linkedin.com/in/shubham-tiwari-1729712b8"')


class AdminTests(TestCase):  # added by shubham - admin list, filters and the "Fetch latest news" button

    def test_admin_pages_render(self):
        admin_user = User.objects.create_superuser('root', 'root@example.com', 'pw')
        self.client.force_login(admin_user)
        make_api_news('Admin story')
        response = self.client.get(reverse('admin:news_news_changelist'))
        self.assertContains(response, 'Admin story')
        self.assertContains(response, 'Fetch latest news from GNews')
        self.assertEqual(self.client.get(reverse('admin:news_fetchlog_changelist')).status_code, 200)

    def test_admin_hide_action(self):
        admin_user = User.objects.create_superuser('root', 'root@example.com', 'pw')
        self.client.force_login(admin_user)
        article = make_api_news('To hide')
        self.client.post(reverse('admin:news_news_changelist'), {
            'action': 'hide_articles', '_selected_action': [article.pk],
        })
        article.refresh_from_db()
        self.assertFalse(article.is_active)


@override_settings(GNEWS_API_KEY='secret-test-key')
class RefreshViewTests(TestCase):  # added by shubham - staff-only "Fetch now" button

    def setUp(self):
        cache.clear()

    def test_non_staff_cannot_refresh(self):
        User.objects.create_user('reader', password='pw')
        self.client.login(username='reader', password='pw')
        with mock.patch('news.services.requests.get') as get:
            self.client.post(reverse('news:refresh'))
        get.assert_not_called()

    @mock.patch('news.services.requests.get')
    def test_staff_refresh_forces_fetch(self, get):
        get.return_value = fake_response(payload={'articles': [gnews_article(1)]})
        User.objects.create_user('boss', password='pw', is_staff=True)
        self.client.login(username='boss', password='pw')
        response = self.client.post(reverse('news:refresh'), {'next': 'https://evil.example.com/'})
        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)  # unsafe next ignored
        self.assertEqual(get.call_count, 3)
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'new articles')
