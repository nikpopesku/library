from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .forms import MovieForm
from .models import (
    MAX_BOOK_COVER_IMAGE_HEIGHT,
    MAX_BOOK_COVER_IMAGE_SIZE_BYTES,
    MAX_BOOK_COVER_IMAGE_WIDTH,
    Language,
    Movie,
)
from .tests import make_image_file
from .views import DEFAULT_PAGE_SIZE


def titles(response):
    return [movie.title for movie in response.context["movies"]]


class MovieModelTests(TestCase):
    def test_str_is_the_title(self):
        self.assertEqual(str(Movie(title="Stalker")), "Stalker")

    def test_accepts_half_point_rating(self):
        movie = Movie.objects.create(title="Stalker", rating=Decimal("8.5"))
        movie.full_clean()

    def test_rating_outside_scale_is_rejected(self):
        for rating in (Decimal("0.5"), Decimal("10.5")):
            with self.subTest(rating=rating):
                with self.assertRaises(ValidationError):
                    Movie(title="Stalker", rating=rating).full_clean()

    def test_database_rejects_rating_outside_scale(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Movie.objects.create(title="Stalker", rating=Decimal("11"))

    def test_poster_rejects_non_image_extensions(self):
        movie = Movie(title="Stalker", poster=SimpleUploadedFile("poster.gif", b"gif data"))
        with self.assertRaises(ValidationError):
            movie.full_clean()

    def test_poster_rejects_oversized_files(self):
        image = make_image_file()
        oversized = SimpleUploadedFile(
            "poster.png",
            image.read() + b"0" * (MAX_BOOK_COVER_IMAGE_SIZE_BYTES + 1),
            content_type="image/png",
        )
        with self.assertRaisesMessage(ValidationError, "Poster images must be 2 MB or smaller."):
            Movie(title="Stalker", poster=oversized).full_clean()

    def test_poster_rejects_large_dimensions(self):
        poster = make_image_file(
            width=MAX_BOOK_COVER_IMAGE_WIDTH + 1, height=MAX_BOOK_COVER_IMAGE_HEIGHT + 1
        )
        with self.assertRaises(ValidationError):
            Movie(title="Stalker", poster=poster).full_clean()


class MovieListViewTests(TestCase):
    def test_page_is_public_and_empty_state_is_shown(self):
        response = self.client.get(reverse("movie-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No movies yet.")

    def test_lists_movies_newest_watched_first(self):
        Movie.objects.create(title="Old", watched_at=date(2023, 1, 1))
        Movie.objects.create(title="New", watched_at=date(2025, 1, 1))
        Movie.objects.create(title="Undated")

        response = self.client.get(reverse("movie-list"))

        self.assertEqual(titles(response), ["New", "Old", "Undated"])

    def test_row_shows_poster_language_date_and_rating(self):
        russian = Language.objects.get_or_create(name="Russian")[0]
        Movie.objects.create(
            title="Stalker",
            poster=make_image_file(name="poster.png"),
            language=russian,
            watched_at=date(2024, 5, 6),
            rating=Decimal("9.5"),
        )

        response = self.client.get(reverse("movie-list"))

        self.assertContains(response, "Stalker")
        self.assertContains(response, "Poster for Stalker")
        self.assertContains(response, "Russian")
        self.assertContains(response, "9.5/10")

    def test_filters_by_year_and_ignores_invalid_year(self):
        Movie.objects.create(title="In 2024", watched_at=date(2024, 3, 1))
        Movie.objects.create(title="In 2025", watched_at=date(2025, 3, 1))

        for value, expected in (
            ("2024", ["In 2024"]),
            ("1999", ["In 2025", "In 2024"]),
            ("x", ["In 2025", "In 2024"]),
        ):
            with self.subTest(year=value):
                response = self.client.get(reverse("movie-list"), {"year": value})
                self.assertEqual(titles(response), expected)

    def test_filters_by_language_and_ignores_unknown_language(self):
        russian = Language.objects.get_or_create(name="Russian")[0]
        Movie.objects.create(title="Russian film", language=russian)
        Movie.objects.create(title="No language")

        filtered = self.client.get(reverse("movie-list"), {"language": russian.id})
        ignored = self.client.get(reverse("movie-list"), {"language": "999999"})

        self.assertEqual(titles(filtered), ["Russian film"])
        self.assertEqual(len(titles(ignored)), 2)

    def test_sorts_by_rating_with_unrated_last_in_both_directions(self):
        Movie.objects.create(title="Low", rating=Decimal("3"))
        Movie.objects.create(title="High", rating=Decimal("9"))
        Movie.objects.create(title="Unrated")

        ascending = self.client.get(reverse("movie-list"), {"sort": "rating"})
        descending = self.client.get(reverse("movie-list"), {"sort": "-rating"})

        self.assertEqual(titles(ascending), ["Low", "High", "Unrated"])
        self.assertEqual(titles(descending), ["High", "Low", "Unrated"])

    def test_unknown_sort_falls_back_to_default(self):
        Movie.objects.create(title="A", watched_at=date(2024, 1, 1))
        Movie.objects.create(title="B", watched_at=date(2025, 1, 1))

        response = self.client.get(reverse("movie-list"), {"sort": "bogus"})

        self.assertEqual(titles(response), ["B", "A"])

    def test_paginates_and_keeps_filters_in_page_links(self):
        for index in range(DEFAULT_PAGE_SIZE + 1):
            Movie.objects.create(title=f"Movie {index:02d}", watched_at=date(2024, 1, 1))

        response = self.client.get(reverse("movie-list"), {"year": "2024"})

        self.assertEqual(len(titles(response)), DEFAULT_PAGE_SIZE)
        self.assertTrue(response.context["is_paginated"])
        self.assertContains(response, "/movies/?year=2024&amp;page=2")


class SideNavTests(TestCase):
    def test_reading_is_active_on_the_default_page(self):
        response = self.client.get(reverse("book-list"))

        self.assertContains(response, 'href="/" aria-current="page">Reading</a>')
        self.assertNotContains(response, 'aria-current="page">Movies</a>')

    def test_movies_is_active_on_the_movies_page(self):
        response = self.client.get(reverse("movie-list"))

        self.assertContains(response, 'href="/movies/" aria-current="page">Movies</a>')
        self.assertNotContains(response, 'aria-current="page">Reading</a>')


class MovieAdminTests(TestCase):
    def test_changelist_and_language_changelist_load(self):
        user = get_user_model().objects.create_superuser(
            username="movie-admin", email="a@example.invalid", password="test-only-password"
        )
        self.client.force_login(user)
        Movie.objects.create(title="Stalker", poster=make_image_file(name="poster.png"))

        for name in ("admin:books_movie_changelist", "admin:books_language_changelist"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)


class SeedExampleMoviesTests(TestCase):
    def test_command_is_idempotent(self):
        call_command("seed_example_movies", stdout=StringIO())
        first_count = Movie.objects.count()
        call_command("seed_example_movies", stdout=StringIO())

        self.assertGreater(first_count, 0)
        self.assertEqual(Movie.objects.count(), first_count)


class MovieReleaseYearTests(TestCase):
    def test_model_accepts_blank_and_boundary_years(self):
        for year in (None, 1888, date.today().year + 1):
            with self.subTest(year=year):
                Movie(title="Film", release_year=year).full_clean()

    def test_model_and_form_reject_out_of_range_years(self):
        for year in (-1, 0, 1887, date.today().year + 2):
            with self.subTest(year=year):
                with self.assertRaises(ValidationError) as error:
                    Movie(title="Film", release_year=year).full_clean()
                self.assertIn("release_year", error.exception.message_dict)
                form = MovieForm(data={"title": "Film", "release_year": year})
                self.assertFalse(form.is_valid())
                self.assertIn("release_year", form.errors)

    def test_upper_bound_advances_without_restarting(self):
        with patch("reading.models.date") as clock:
            clock.today.return_value = date(2030, 1, 1)
            Movie(title="Future film", release_year=2031).full_clean()
            with self.assertRaises(ValidationError):
                Movie(title="Future film", release_year=2032).full_clean()

    def test_form_saves_year_and_allows_clearing_it(self):
        form = MovieForm(data={"title": "Stalker", "release_year": 1979})
        self.assertTrue(form.is_valid(), form.errors)
        movie = form.save()
        self.assertEqual(movie.release_year, 1979)
        cleared = MovieForm(data={"title": "Stalker", "release_year": ""}, instance=movie)
        self.assertTrue(cleared.is_valid(), cleared.errors)
        self.assertIsNone(cleared.save().release_year)

    def test_release_year_is_part_of_title_without_a_separate_column(self):
        Movie.objects.create(title="Stalker", release_year=1979)
        Movie.objects.create(title="Unknown")
        response = self.client.get(reverse("movie-list"))
        self.assertContains(response, '<div class="movie-release-year">1979</div>', html=True)
        self.assertContains(
            response, '<td class="cell-title" data-label="Title">Unknown</td>', html=True
        )
        self.assertNotContains(response, 'data-label="Year"')
        self.assertNotContains(response, "sort=release_year")
        self.assertNotIn("release_year", response.context["sort_links"])

    def test_admin_can_display_filter_and_search_years(self):
        user = get_user_model().objects.create_superuser(username="year-admin", password="test")
        self.client.force_login(user)
        Movie.objects.create(title="Stalker", release_year=1979)
        Movie.objects.create(title="Parasite", release_year=2019)
        url = reverse("admin:books_movie_changelist")
        for params in ({"q": "1979"}, {"release_year": "1979"}, {"q": "Stalker"}):
            with self.subTest(params=params):
                response = self.client.get(url, params)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Stalker")
                self.assertNotContains(response, "Parasite")
                self.assertContains(response, "column-release_year")

    def test_seed_populates_years_and_backfills_without_overwriting_existing_data(self):
        existing = Movie.objects.create(title="Stalker", notes="Keep my notes", rating=7)
        custom = Movie.objects.create(title="Parasite", release_year=2020)
        for _ in range(2):
            call_command("seed_example_movies", stdout=StringIO())
        existing.refresh_from_db()
        custom.refresh_from_db()
        self.assertEqual(existing.release_year, 1979)
        self.assertEqual(existing.notes, "Keep my notes")
        self.assertEqual(existing.rating, 7)
        self.assertIsNone(existing.watched_at)
        self.assertEqual(custom.release_year, 2020)
        self.assertEqual(Movie.objects.count(), 7)
        self.assertEqual(Movie.objects.get(title="Cinema Paradiso").release_year, 1988)
        self.assertFalse(Movie.objects.filter(release_year__isnull=True).exists())
