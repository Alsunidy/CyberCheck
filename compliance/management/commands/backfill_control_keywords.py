from django.core.management.base import BaseCommand

from compliance.models import Control
from compliance.services.keywords import build_keywords_from_text


class Command(BaseCommand):
    help = (
        'Fill empty Control.keywords from title/description (same logic as seed / AI fallback). '
        'Use after migrations so evidence scoring has keywords in admin too.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite existing keywords (default: only rows with empty keywords).',
        )

    def handle(self, *args, **options):
        force = options['force']
        if force:
            qs = Control.objects.all()
        else:
            empty_pks = [
                c.pk
                for c in Control.objects.only('pk', 'keywords').iterator()
                if not c.keywords
            ]
            qs = Control.objects.filter(pk__in=empty_pks)

        updated = 0
        for control in qs.iterator():
            control.keywords = build_keywords_from_text(control.title, control.description)
            control.save(update_fields=['keywords'])
            updated += 1

        self.stdout.write(self.style.SUCCESS(f'Updated keywords on {updated} control(s).'))
