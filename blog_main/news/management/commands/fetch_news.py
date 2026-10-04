# added by shubham - `python manage.py fetch_news` pulls the latest GNews headlines (use with Task Scheduler/cron)
from django.core.management.base import BaseCommand, CommandError

from news import services


class Command(BaseCommand):
    help = 'Fetch the latest General, Sports and Technology headlines from GNews.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--category', choices=list(services.API_CATEGORIES),
            help='Only fetch this category (default: all).',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Fetch even if the stored news is still fresh.',
        )

    def handle(self, *args, **options):
        if not services.api_configured():
            raise CommandError('GNEWS_API_KEY is not set. Add it to blog_main/.env')

        categories = [options['category']] if options['category'] else None
        logs = services.refresh_if_stale(categories, force=options['force'])
        if not logs:
            self.stdout.write('News is already fresh; nothing fetched. Use --force to fetch anyway.')
        for log in logs:
            if log.success:
                self.stdout.write(self.style.SUCCESS(
                    f'{log.category}: {log.articles_received} received, {log.articles_created} new'
                ))
            else:
                self.stdout.write(self.style.ERROR(f'{log.category}: {log.error}'))
