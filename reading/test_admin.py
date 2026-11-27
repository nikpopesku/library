from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.formats import get_format

from .models import Book, BookStatus


class BookAdminChangelistTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="book-admin-test", email="admin@example.invalid", password="test-only-password"
        )
        Book.objects.create(title="Older", finished_at=date(2024, 1, 1), status=BookStatus.READ)
        Book.objects.create(
            title="Zulu newer", finished_at=date(2024, 2, 1), status=BookStatus.READ
        )
        Book.objects.create(title="Alpha newer", finished_at=date(2024, 2, 1))
        Book.objects.create(title="Unfinished", status=BookStatus.READING)
        Book.objects.create(title="Also unfinished")

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("admin:books_book_changelist")

    def test_defaults_to_latest_finished_date_with_unfinished_books_last(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._titles(response),
            ["Alpha newer", "Zulu newer", "Older", "Also unfinished", "Unfinished"],
        )
        self.assertEqual(response.context["cl"].get_ordering_field_columns()[7], "desc")

    def test_finished_date_filter_is_available_without_excluding_books_by_default(self):
        response = self.client.get(self.url)

        self.assertContains(response, 'data-filter-title="finished at"')
        self.assertContains(response, "No date")
        self.assertContains(response, "Has date")
        self.assertEqual(response.context["cl"].result_count, 5)

    def test_finished_date_range_preserves_default_ordering(self):
        response = self.client.get(
            self.url, {"finished_at__gte": "2024-02-01", "finished_at__lt": "2024-03-01"}
        )

        self.assertEqual(self._titles(response), ["Alpha newer", "Zulu newer"])

    def test_can_filter_to_unfinished_books(self):
        response = self.client.get(self.url, {"finished_at__isnull": "True"})

        self.assertEqual(self._titles(response), ["Also unfinished", "Unfinished"])

    def test_user_selected_title_order_overrides_default(self):
        response = self.client.get(self.url, {"o": "2"})

        self.assertEqual(
            self._titles(response),
            ["Alpha newer", "Also unfinished", "Older", "Unfinished", "Zulu newer"],
        )

    def test_user_can_reverse_finished_date_order(self):
        response = self.client.get(self.url, {"o": "7", "finished_at__isnull": "False"})

        self.assertEqual(self._titles(response), ["Older", "Alpha newer", "Zulu newer"])

    def _titles(self, response):
        return [book.title for book in response.context["cl"].result_list]


class AdminCalendarTests(TestCase):
    def test_week_starts_on_monday(self):
        self.assertEqual(get_format("FIRST_DAY_OF_WEEK"), 1)

    def test_admin_js_catalog_serves_monday_start(self):
        user = get_user_model().objects.create_superuser(
            username="calendar-test",
            email="calendar@example.invalid",
            password="test-only-password",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:jsi18n"))

        self.assertContains(response, '"FIRST_DAY_OF_WEEK": 1,')
