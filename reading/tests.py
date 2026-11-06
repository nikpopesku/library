import struct
import tempfile
import zlib
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.shortcuts import resolve_url
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    MAX_BOOK_COVER_IMAGE_HEIGHT,
    MAX_BOOK_COVER_IMAGE_SIZE_BYTES,
    MAX_BOOK_COVER_IMAGE_WIDTH,
    Author,
    Book,
    BookStatus,
    Language,
    Tag,
)
from .views import DEFAULT_PAGE_SIZE


def make_png_bytes(*, width=48, height=72, color=(36, 93, 99)):
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(
        ">IIBBBBB",
        width,
        height,
        8,
        2,
        0,
        0,
        0,
    )
    ihdr_body = b"IHDR" + ihdr_data
    ihdr = (
        struct.pack(">I", len(ihdr_data))
        + ihdr_body
        + struct.pack(">I", zlib.crc32(ihdr_body) & 0xFFFFFFFF)
    )

    row = bytes([0]) + bytes(color) * width
    raw = row * height
    compressed = zlib.compress(raw)
    idat_body = b"IDAT" + compressed
    idat = (
        struct.pack(">I", len(compressed))
        + idat_body
        + struct.pack(">I", zlib.crc32(idat_body) & 0xFFFFFFFF)
    )

    iend_body = b"IEND"
    iend = struct.pack(">I", 0) + iend_body + struct.pack(">I", zlib.crc32(iend_body) & 0xFFFFFFFF)
    return signature + ihdr + idat + iend


def make_image_file(*, width=48, height=72, name="cover.png"):
    return SimpleUploadedFile(
        name, make_png_bytes(width=width, height=height), content_type="image/png"
    )


def make_author(name="Author"):
    return Author.objects.create(name=name)


class BookModelTests(TestCase):
    def test_book_defaults_to_will_read(self):
        book = Book.objects.create(title="Dune", author=make_author("Frank Herbert"))

        self.assertEqual(book.status, BookStatus.WILL_READ)
        self.assertEqual(str(book), "Dune by Frank Herbert")

    def test_book_without_author_uses_title_for_string(self):
        book = Book.objects.create(title="Sapiens")

        self.assertEqual(str(book), "Sapiens")

    def test_book_rating_uses_ten_point_scale(self):
        book = Book(title="Deep Work", rating=10)

        book.full_clean()

        with self.assertRaises(ValidationError):
            Book(title="Invalid", rating=11).full_clean()

    def test_book_accepts_half_point_rating(self):
        book = Book.objects.create(title="Deep Work", rating=Decimal("6.5"))

        book.full_clean()
        self.assertEqual(book.rating, Decimal("6.5"))

        with self.assertRaises(ValidationError):
            Book(title="Invalid", rating=Decimal("0.5")).full_clean()

    def test_book_can_have_tags(self):
        book = Book.objects.create(title="Dune")
        fiction = Tag.objects.create(name="fiction")
        classics = Tag.objects.create(name="classics")

        book.tags.add(fiction, classics)

        self.assertEqual(
            list(book.tags.order_by("name").values_list("name", flat=True)),
            ["classics", "fiction"],
        )

    def test_default_languages_are_seeded(self):
        self.assertEqual(
            list(Language.objects.values_list("name", flat=True)),
            ["Italian", "Romanian", "Russian"],
        )

    def test_book_cover_image_can_be_uploaded_and_displayed_as_thumbnail(self):
        book = Book.objects.create(
            title="Dune",
            author=make_author("Frank Herbert"),
            cover_image=make_image_file(),
        )

        response = self.client.get(reverse("book-list"))

        self.assertContains(response, book.cover_image.url)
        self.assertContains(response, 'class="book-cover-thumb"', html=False)

    def test_book_cover_media_file_is_served_when_debug_is_disabled(self):
        with tempfile.TemporaryDirectory() as media_root:
            cover_path = Path(media_root) / "book-covers" / "cover.png"
            cover_path.parent.mkdir(parents=True)
            cover_path.write_bytes(make_png_bytes())

            with override_settings(DEBUG=False, MEDIA_ROOT=media_root):
                response = self.client.get("/media/book-covers/cover.png")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "image/png")

    def test_book_cover_image_rejects_non_image_extensions(self):
        book = Book(title="Dune", cover_image=SimpleUploadedFile("cover.gif", b"gif data"))

        with self.assertRaises(ValidationError):
            book.full_clean()

    def test_book_cover_image_rejects_images_that_are_too_large(self):
        image = make_image_file()
        oversized = SimpleUploadedFile(
            "cover.png",
            image.read() + b"0" * (MAX_BOOK_COVER_IMAGE_SIZE_BYTES + 1),
            content_type="image/png",
        )
        book = Book(title="Dune", cover_image=oversized)

        with self.assertRaises(ValidationError):
            book.full_clean()

    def test_book_cover_image_rejects_images_with_large_dimensions(self):
        book = Book(
            title="Dune",
            cover_image=make_image_file(
                width=MAX_BOOK_COVER_IMAGE_WIDTH + 1,
                height=MAX_BOOK_COVER_IMAGE_HEIGHT + 1,
            ),
        )

        with self.assertRaises(ValidationError):
            book.full_clean()


class BookViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="admin", password="password")

    def test_homepage_is_public(self):
        response = self.client.get(reverse("book-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Library")

    def test_homepage_has_meta_description_and_allows_indexing(self):
        response = self.client.get(reverse("book-list"))

        self.assertContains(response, '<meta name="description"')
        self.assertContains(response, '<meta name="robots" content="index, follow">')

    def test_robots_txt_allows_indexing(self):
        response = self.client.get("/robots.txt")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")
        self.assertContains(response, "Allow: /")
        self.assertContains(response, "Disallow: /admin/")

    def test_homepage_renders_books_table(self):
        Book.objects.create(title="Reading now", author=make_author(), status=BookStatus.READING)

        response = self.client.get(reverse("book-list"))

        self.assertContains(response, "<table", html=False)
        self.assertContains(response, "Reading now")
        self.assertContains(response, "Author")

    def test_homepage_paginates_books_by_default(self):
        author = make_author()
        for index in range(DEFAULT_PAGE_SIZE + 1):
            Book.objects.create(title=f"Book {index:02d}", author=author)

        response = self.client.get(reverse("book-list"))

        self.assertEqual(response.context["page_obj"].paginator.per_page, DEFAULT_PAGE_SIZE)
        self.assertEqual(len(response.context["books"]), DEFAULT_PAGE_SIZE)
        self.assertEqual(response.context["total_count"], DEFAULT_PAGE_SIZE + 1)
        self.assertContains(response, "Books per page")
        self.assertContains(response, "Next")

    def test_user_can_change_page_size(self):
        for index in range(12):
            Book.objects.create(title=f"Book {index:02d}")

        response = self.client.get(reverse("book-list"), {"page_size": 10})

        self.assertEqual(response.context["page_obj"].paginator.per_page, 10)
        self.assertEqual(len(response.context["books"]), 10)

    def test_homepage_displays_book_tags(self):
        book = Book.objects.create(title="Tagged", status=BookStatus.READING)
        fiction = Tag.objects.create(name="fiction")
        classics = Tag.objects.create(name="classics")
        book.tags.add(fiction, classics)

        response = self.client.get(reverse("book-list"))

        self.assertContains(response, "fiction")
        self.assertContains(response, "classics")

    def test_user_can_filter_books_without_login(self):
        Book.objects.create(title="Reading now", status=BookStatus.READING)
        Book.objects.create(title="Later", status=BookStatus.WILL_READ)

        response = self.client.get(reverse("book-list"), {"status": BookStatus.READING})

        self.assertContains(response, "Reading now")
        self.assertNotContains(response, "Later")

    def test_user_can_filter_books_by_language(self):
        italian = Language.objects.get(name="Italian")
        russian = Language.objects.get(name="Russian")
        Book.objects.create(title="War and Peace", status=BookStatus.READ, language=russian)
        Book.objects.create(title="The Betrothed", status=BookStatus.READING, language=italian)

        response = self.client.get(reverse("book-list"), {"language": russian.id})

        self.assertContains(response, "War and Peace")
        self.assertContains(response, "Russian")
        self.assertNotContains(response, "The Betrothed")

    def test_user_can_filter_books_by_author(self):
        tolstoy = Author.objects.create(name="Leo Tolstoy")
        manzoni = Author.objects.create(name="Alessandro Manzoni")
        Book.objects.create(title="War and Peace", status=BookStatus.READ, author=tolstoy)
        Book.objects.create(title="The Betrothed", status=BookStatus.READING, author=manzoni)

        response = self.client.get(reverse("book-list"), {"author": tolstoy.id})

        self.assertContains(response, "War and Peace")
        self.assertNotContains(response, "The Betrothed")
        self.assertEqual(response.context["selected_author"], str(tolstoy.id))

    def test_author_filter_combines_with_status_filter(self):
        tolstoy = Author.objects.create(name="Leo Tolstoy")
        Book.objects.create(title="War and Peace", status=BookStatus.READ, author=tolstoy)
        Book.objects.create(title="Anna Karenina", status=BookStatus.READING, author=tolstoy)

        response = self.client.get(
            reverse("book-list"), {"author": tolstoy.id, "status": BookStatus.READ}
        )

        self.assertContains(response, "War and Peace")
        self.assertNotContains(response, "Anna Karenina")

    def test_invalid_or_unknown_author_filter_is_ignored(self):
        tolstoy = Author.objects.create(name="Leo Tolstoy")
        Book.objects.create(title="War and Peace", status=BookStatus.READ, author=tolstoy)
        Book.objects.create(title="No author", status=BookStatus.READ)

        for value in ("abc", "999999"):
            with self.subTest(value=value):
                response = self.client.get(reverse("book-list"), {"author": value})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["selected_author"], "")
                self.assertEqual(len(response.context["books"]), 2)

    def test_author_dropdown_only_lists_authors_with_visible_books(self):
        visible = Author.objects.create(name="Visible Author")
        deleted_only = Author.objects.create(name="Deleted Only")
        Author.objects.create(name="No Books")
        Book.objects.create(title="Shown", status=BookStatus.READ, author=visible)
        Book.objects.create(title="Hidden", status=BookStatus.DELETED, author=deleted_only)

        response = self.client.get(reverse("book-list"))

        self.assertEqual(list(response.context["authors"]), [visible])

    def test_other_filter_forms_keep_selected_author(self):
        tolstoy = Author.objects.create(name="Leo Tolstoy")
        Book.objects.create(
            title="War and Peace",
            status=BookStatus.READ,
            author=tolstoy,
            finished_at=date(2024, 1, 1),
        )

        response = self.client.get(reverse("book-list"), {"author": tolstoy.id})

        self.assertContains(
            response, f'<input type="hidden" name="author" value="{tolstoy.id}">', count=4
        )

    def test_user_can_filter_and_paginate_books_together(self):
        for index in range(11):
            Book.objects.create(title=f"Reading {index:02d}", status=BookStatus.READING)
        Book.objects.create(title="Later", status=BookStatus.WILL_READ)

        response = self.client.get(
            reverse("book-list"),
            {"status": BookStatus.READING, "page_size": 10, "page": 2},
        )

        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(len(response.context["books"]), 1)
        self.assertEqual(
            list(response.context["books"].values_list("title", flat=True)),
            ["Reading 10"],
        )
        self.assertNotContains(response, "Later")

    def test_user_can_sort_books_by_status(self):
        Book.objects.create(title="Read", status=BookStatus.READ)
        Book.objects.create(title="Will read", status=BookStatus.WILL_READ)
        Book.objects.create(title="Reading", status=BookStatus.READING)

        response = self.client.get(reverse("book-list"), {"sort": "status"})

        self.assertEqual(
            list(response.context["books"].values_list("title", flat=True)),
            ["Will read", "Reading", "Read"],
        )

    def test_default_sort_is_by_finished_date_descending(self):
        Book.objects.create(title="Older", status=BookStatus.READ, finished_at=date(2024, 1, 1))
        Book.objects.create(title="Newer", status=BookStatus.READ, finished_at=date(2024, 2, 1))
        Book.objects.create(title="Unfinished", status=BookStatus.WILL_READ)

        response = self.client.get(reverse("book-list"))

        self.assertEqual(
            list(response.context["books"].values_list("title", flat=True)),
            ["Newer", "Older", "Unfinished"],
        )

    def test_user_can_sort_books_by_title(self):
        Book.objects.create(title="Zulu", status=BookStatus.READ)
        Book.objects.create(title="Alpha", status=BookStatus.WILL_READ)
        Book.objects.create(title="Mike", status=BookStatus.READING)

        response = self.client.get(reverse("book-list"), {"sort": "title"})

        self.assertEqual(
            list(response.context["books"].values_list("title", flat=True)),
            ["Alpha", "Mike", "Zulu"],
        )

    def test_user_can_sort_books_by_author(self):
        Book.objects.create(title="Zulu", author=make_author("Zed"))
        Book.objects.create(title="Alpha", author=make_author("Alice"))
        Book.objects.create(title="Mike", author=make_author("Mike"))

        response = self.client.get(reverse("book-list"), {"sort": "author"})

        self.assertEqual(
            list(response.context["books"].values_list("author__name", flat=True)),
            ["Alice", "Mike", "Zed"],
        )

    def test_admin_can_select_author_when_creating_a_book(self):
        admin_user = get_user_model().objects.create_superuser(
            username="authoradmin", password="password", email="author@example.com"
        )
        self.client.force_login(admin_user)
        author = make_author("Albert Camus")

        response = self.client.post(
            reverse("admin:books_book_add"),
            {
                "title": "The Stranger",
                "author": str(author.id),
                "language": "",
                "status": BookStatus.WILL_READ,
                "started_at": "",
                "finished_at": "",
                "rating": "",
                "notes": "",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        book = Book.objects.get(title="The Stranger")
        self.assertEqual(book.author, author)

    def test_populate_authors_command_normalizes_existing_authors(self):
        messy_author = make_author("  Albert Camus  ")
        book = Book.objects.create(title="The Stranger", author=messy_author)

        call_command("populate_authors")

        book.refresh_from_db()
        self.assertEqual(book.author.name, "Albert Camus")

    def test_user_can_sort_books_by_language(self):
        italian = Language.objects.get(name="Italian")
        romanian = Language.objects.get(name="Romanian")
        russian = Language.objects.get(name="Russian")
        Book.objects.create(title="Zulu", language=russian)
        Book.objects.create(title="Alpha", language=italian)
        Book.objects.create(title="Mike", language=romanian)
        Book.objects.create(title="No language")

        response = self.client.get(reverse("book-list"), {"sort": "language"})

        self.assertEqual(
            list(response.context["books"].values_list("title", flat=True)),
            ["Alpha", "Mike", "Zulu", "No language"],
        )

    def test_user_can_sort_books_by_finished_date(self):
        Book.objects.create(title="Older", status=BookStatus.READ, finished_at=date(2024, 1, 1))
        Book.objects.create(title="Newer", status=BookStatus.READ, finished_at=date(2024, 2, 1))
        Book.objects.create(title="Unfinished", status=BookStatus.READ)

        response = self.client.get(reverse("book-list"), {"sort": "-finished_at"})

        self.assertEqual(
            list(response.context["books"].values_list("title", flat=True)),
            ["Newer", "Older", "Unfinished"],
        )

    def test_user_can_sort_books_by_started_date(self):
        Book.objects.create(title="Older", status=BookStatus.READING, started_at=date(2024, 1, 1))
        Book.objects.create(title="Newer", status=BookStatus.READING, started_at=date(2024, 2, 1))
        Book.objects.create(title="Unstarted", status=BookStatus.READING)

        response = self.client.get(reverse("book-list"), {"sort": "started_at"})

        self.assertEqual(
            list(response.context["books"].values_list("title", flat=True)),
            ["Older", "Newer", "Unstarted"],
        )

    def test_user_can_sort_books_by_rating(self):
        Book.objects.create(title="Low", status=BookStatus.READ, rating=2)
        Book.objects.create(title="High", status=BookStatus.READ, rating=9)
        Book.objects.create(title="Unrated", status=BookStatus.READ)

        response = self.client.get(reverse("book-list"), {"sort": "-rating"})

        self.assertEqual(
            list(response.context["books"].values_list("title", flat=True)),
            ["High", "Low", "Unrated"],
        )

    def test_deleted_books_are_hidden_from_library(self):
        Book.objects.create(title="Visible", status=BookStatus.READING)
        Book.objects.create(title="Hidden", status=BookStatus.DELETED)

        response = self.client.get(reverse("book-list"))

        self.assertContains(response, "Visible")
        self.assertNotContains(response, "Hidden")

    def test_admin_tag_changelist_shows_usage_counts(self):
        admin_user = get_user_model().objects.create_superuser(
            username="superadmin", password="password", email="admin@example.com"
        )
        self.client.force_login(admin_user)
        used_tag = Tag.objects.create(name="used")
        Tag.objects.create(name="unused")
        book = Book.objects.create(title="Tagged", status=BookStatus.READING)
        book.tags.add(used_tag)

        response = self.client.get(reverse("admin:books_tag_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "used")
        self.assertContains(response, "unused")
        self.assertContains(response, "1")
        self.assertContains(response, "0")

    def test_admin_can_set_language_when_creating_a_book(self):
        admin_user = get_user_model().objects.create_superuser(
            username="languageadmin", password="password", email="language@example.com"
        )
        self.client.force_login(admin_user)
        author = make_author("Albert Camus")
        language = Language.objects.get(name="Romanian")

        response = self.client.post(
            reverse("admin:books_book_add"),
            {
                "title": "The Stranger",
                "author": str(author.id),
                "language": str(language.id),
                "status": BookStatus.WILL_READ,
                "started_at": "",
                "finished_at": "",
                "rating": "",
                "notes": "",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        book = Book.objects.get(title="The Stranger")
        self.assertEqual(book.language, language)

    def test_admin_login_is_available(self):
        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_auth_redirect_settings_resolve(self):
        self.assertEqual(resolve_url(settings.LOGIN_URL), reverse("admin:login"))
        self.assertEqual(resolve_url(settings.LOGOUT_REDIRECT_URL), reverse("admin:login"))

    def test_admin_logout_redirects_to_login_and_ends_session(self):
        admin_user = get_user_model().objects.create_superuser(
            username="logout-admin", email="logout@example.invalid", password="test-pass"
        )
        self.client.force_login(admin_user)

        response = self.client.post(reverse("admin:logout"))

        self.assertRedirects(response, reverse("admin:login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])
