<!-- added by shubham - setup and usage guide -->
# Front Line — Blog + Live News (Django)

A Django news/blog site. Users can register, log in and write their own posts, and
the site automatically pulls the latest **General, Sports and Technology** headlines
from the [GNews API](https://gnews.io).

## Setup

```bash
python -m venv env
env\Scripts\activate            # Windows
pip install -r blog_main/requirements.txt

cd blog_main
copy .env.example .env          # then edit .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### `.env` values

| Key | Meaning |
|---|---|
| `DJANGO_SECRET_KEY` | Long random string (required) |
| `DJANGO_DEBUG` | `True` for local development, `False` in production |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names |
| `GNEWS_API_KEY` | Your free key from gnews.io. Leave empty to turn live news off |
| `GNEWS_LANG` / `GNEWS_COUNTRY` | e.g. `en` / `in` |
| `NEWS_REFRESH_MINUTES` | How old stored news may get before it is re-fetched (default 60) |

## How live news works

* Pages always read news from the **database**, never straight from the API.
* When a page loads and a category's news is older than `NEWS_REFRESH_MINUTES`,
  the site fetches that category once, saves new articles and skips duplicates
  (matched by URL). A cache lock stops two visitors triggering the same fetch.
* A failed fetch (no internet, bad key, daily limit) is logged and retried after
  30 minutes; the site keeps showing the last saved news.
* 3 categories every 60 minutes is about 72 requests/day, inside the free 100/day.
* API articles older than 30 days are deleted automatically.

Fetch by hand (or from Windows Task Scheduler):

```bash
python manage.py fetch_news            # only stale categories
python manage.py fetch_news --force    # everything, now
python manage.py fetch_news --category Sports
```

If you schedule `fetch_news`, you can set `NEWS_AUTO_REFRESH=False` in `.env` so
page loads never wait for the API.

## Who can do what

| | Read | Write a post | Edit / delete |
|---|---|---|---|
| Visitor | ✅ | ➜ login | ❌ |
| Logged-in user | ✅ | ✅ | own posts only |
| Staff / admin | ✅ | ✅ | all manual posts; hide any article in admin |

API articles cannot be edited on the site; admins can hide them in `/admin/`.

## Admin

* **News**: filter by category, source (site/GNews), visibility, date; hide or show
  in bulk; the **Fetch latest news from GNews** button forces a refresh.
* **Fetch logs**: every API call with its result or error message.
* **Login records**: who logged in, when, and from which IP.

## Tests

```bash
cd blog_main
python manage.py test
```
All API calls in tests are mocked, so tests never use your GNews quota.
