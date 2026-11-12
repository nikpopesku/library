from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from reading.models import Language, Movie

EXAMPLE_MOVIES = (
    ("Stalker", 1979, "Russian", date(2024, 2, 11), Decimal("9.5")),
    ("Spirited Away", 2001, "Japanese", date(2024, 5, 3), Decimal("9")),
    ("Parasite", 2019, "Korean", date(2024, 8, 17), Decimal("8.5")),
    ("Amélie", 2001, "French", date(2025, 1, 26), Decimal("8")),
    ("Whiplash", 2014, "English", date(2025, 4, 9), Decimal("9")),
    ("The Lives of Others", 2006, "German", date(2025, 7, 21), Decimal("8.5")),
    ("Cinema Paradiso", 1988, "Italian", date(2025, 10, 5), None),
)


class Command(BaseCommand):
    help = "Create example movies for demo and staging environments. Safe to re-run."

    def handle(self, *args, **options):
        created = sum(self._ensure_movie(*row) for row in EXAMPLE_MOVIES)
        existing = len(EXAMPLE_MOVIES) - created
        self.stdout.write(
            self.style.SUCCESS(f"Example movies: {created} created, {existing} existing.")
        )

    def _ensure_movie(self, title, release_year, language_name, watched_at, rating):
        language, _ = Language.objects.get_or_create(name=language_name)
        movie, was_created = Movie.objects.get_or_create(
            title=title,
            defaults={
                "release_year": release_year,
                "language": language,
                "watched_at": watched_at,
                "rating": rating,
            },
        )
        if movie.release_year is None:
            movie.release_year = release_year
            movie.save(update_fields=["release_year"])
        return was_created
