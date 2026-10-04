# added by shubham - GNews API client: fetches General/Sports/Technology headlines and stores them in the DB
"""
Pages never call GNews directly. They read from the database, and
``refresh_if_stale()`` re-fetches a category only when its last fetch is older
than NEWS_REFRESH_MINUTES. With 3 categories every 60 minutes that is ~72
requests/day, inside the GNews free plan (100/day).
"""
import logging
from datetime import timedelta, timezone as dt_timezone

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import FetchLog, News

logger = logging.getLogger(__name__)

GNEWS_URL = 'https://gnews.io/api/v4/top-headlines'
REQUEST_TIMEOUT = 8  # seconds; a slow API must not hang the page
MAX_ARTICLES = 10  # GNews free plan returns at most 10 per request

# Our category -> GNews category
API_CATEGORIES = {
    'General': 'general',
    'Sports': 'sports',
    'Technology': 'technology',
}

LOCK_KEY = 'news:refresh-lock'
CHECKED_KEY = 'news:checked:{}'


class NewsAPIError(Exception):
    """Raised for any problem talking to GNews; the message is safe to show admins."""


def api_configured():
    return bool(settings.GNEWS_API_KEY)


def should_auto_refresh():
    """Pages refresh stale news themselves unless NEWS_AUTO_REFRESH is off (e.g. when a scheduler runs fetch_news)."""
    return settings.NEWS_AUTO_REFRESH and api_configured()


def _scrub(text):
    # Never leak the API key into logs or the admin (requests puts the URL in error messages).
    key = settings.GNEWS_API_KEY
    return text.replace(key, '***') if key else text


def _call_gnews(api_category):
    params = {
        'category': api_category,
        'lang': settings.GNEWS_LANG,
        'max': MAX_ARTICLES,
        'apikey': settings.GNEWS_API_KEY,
    }
    if settings.GNEWS_COUNTRY:
        params['country'] = settings.GNEWS_COUNTRY

    try:
        response = requests.get(GNEWS_URL, params=params, timeout=REQUEST_TIMEOUT)
    except requests.Timeout:
        raise NewsAPIError('GNews did not respond in time.')
    except requests.RequestException as exc:
        raise NewsAPIError(_scrub(f'Could not reach GNews: {exc}'))

    if response.status_code == 401:
        raise NewsAPIError('GNews rejected the API key (401). Check GNEWS_API_KEY in .env.')
    if response.status_code == 403:
        raise NewsAPIError('GNews daily request limit reached (403). News will refresh tomorrow.')
    if response.status_code == 429:
        raise NewsAPIError('Too many requests to GNews (429). Slow down the refresh interval.')
    if response.status_code != 200:
        raise NewsAPIError(f'GNews returned HTTP {response.status_code}.')

    try:
        data = response.json()
    except ValueError:
        raise NewsAPIError('GNews returned an invalid (non-JSON) response.')

    articles = data.get('articles')
    if not isinstance(articles, list):
        raise NewsAPIError('GNews response had no article list.')
    return articles


def _clean(article, category):
    """Turn one GNews article dict into News field values, or None if unusable."""
    url = (article.get('url') or '').strip()
    title = (article.get('title') or '').strip()
    if not url or not title or len(url) > 1000:
        return None

    image = (article.get('image') or '').strip()
    if len(image) > 1000 or not image.startswith(('http://', 'https://')):
        image = ''

    description = (article.get('description') or '').strip()
    content = (article.get('content') or '').strip() or description
    source_name = ((article.get('source') or {}).get('name') or '').strip()
    published = parse_datetime(article.get('publishedAt') or '') or timezone.now()
    if timezone.is_naive(published):
        published = timezone.make_aware(published, dt_timezone.utc)

    return {
        'external_url': url,
        'title': title[:300],
        'description': description,
        'content': content,
        'image': image,
        'source_name': source_name[:200],
        'author': (source_name or 'GNews')[:100],
        'published_at': published,
        'category': category,
    }


def save_articles(raw_articles, category):
    """Insert new articles and refresh existing ones. Returns number created."""
    created = 0
    with transaction.atomic():
        for raw in raw_articles:
            values = _clean(raw, category)
            if values is None:
                continue
            existing = News.objects.filter(external_url=values['external_url']).first()
            if existing is None and News.objects.filter(  # added by shubham - same story, different URL: skip
                source_type=News.SOURCE_API, title__iexact=values['title'],
            ).exists():
                continue
            if existing is None:
                News.objects.create(source_type=News.SOURCE_API, **values)
                created += 1
            else:
                # Keep the first category and the admin's is_active choice; refresh the text/image.
                for field in ('title', 'description', 'content', 'image', 'source_name'):
                    setattr(existing, field, values[field])
                existing.save()
    return created


def prune_old_articles():
    cutoff = timezone.now() - timedelta(days=settings.NEWS_KEEP_DAYS)
    deleted, _ = News.objects.filter(source_type=News.SOURCE_API, published_at__lt=cutoff).delete()
    return deleted


def fetch_category(category):
    """Fetch one category from GNews right now. Always records a FetchLog row."""
    if category not in API_CATEGORIES:
        raise ValueError(f'Unknown API category: {category}')

    log = FetchLog(category=category)
    if not api_configured():
        log.error = 'GNEWS_API_KEY is not set in .env.'
        log.save()
        return log

    try:
        raw = _call_gnews(API_CATEGORIES[category])
        log.articles_received = len(raw)
        log.articles_created = save_articles(raw, category)
        log.success = True
        logger.info('Fetched %s: %s received, %s new', category, log.articles_received, log.articles_created)
    except NewsAPIError as exc:
        log.error = str(exc)
        logger.warning('News fetch failed for %s: %s', category, exc)
    except Exception as exc:  # never let an unexpected API shape break the site
        log.error = _scrub(f'Unexpected error: {exc}')
        logger.exception('Unexpected error fetching %s', category)
    log.save()
    cache.delete(CHECKED_KEY.format(category))
    return log


def is_stale(category):
    """True when the category should be fetched again."""
    last = FetchLog.objects.filter(category=category).first()
    if last is None:
        return True
    wait = settings.NEWS_REFRESH_MINUTES if last.success else settings.NEWS_RETRY_MINUTES
    return timezone.now() - last.fetched_at >= timedelta(minutes=wait)


def refresh_if_stale(categories=None, force=False):
    """
    Fetch every category whose data is out of date. Cheap to call on each page
    load: a 60s cache flag skips the DB check, and a cache lock stops two
    requests fetching at the same time. Returns the FetchLogs created.
    """
    if not api_configured():
        return []
    categories = categories or list(API_CATEGORIES)

    if not force:
        categories = [c for c in categories if not cache.get(CHECKED_KEY.format(c))]
        if not categories:
            return []

    if not cache.add(LOCK_KEY, True, timeout=60):
        return []  # another request is already fetching
    try:
        logs = []
        for category in categories:
            if force or is_stale(category):
                logs.append(fetch_category(category))
            cache.set(CHECKED_KEY.format(category), True, timeout=60)
        if any(log.success for log in logs):
            prune_old_articles()
        return logs
    finally:
        cache.delete(LOCK_KEY)


def last_updated():
    """Time of the most recent successful fetch, for the 'Updated x ago' label."""
    log = FetchLog.objects.filter(success=True).first()
    return log.fetched_at if log else None
