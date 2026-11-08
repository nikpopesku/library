import unicodedata
from difflib import SequenceMatcher

from django import forms
from django.core.exceptions import ValidationError

from .models import ACTIVE_BOOK_STATUSES, Author, Book, Movie


def normalize_author_name(value):
    return " ".join(unicodedata.normalize("NFC", value).split())


def _author_name_key(value):
    return normalize_author_name(value).casefold()


class AuthorForm(forms.ModelForm):
    confirm_similar_name = forms.BooleanField(
        required=False,
        label="Create or rename this author despite similar existing names",
        help_text="Check only after reviewing the similar-name warning.",
    )

    class Meta:
        model = Author
        fields = ["name"]

    def clean(self):
        cleaned = super().clean()
        name = normalize_author_name(cleaned.get("name", ""))
        if not name:
            return cleaned
        cleaned["name"] = name
        others = list(Author.objects.exclude(pk=self.instance.pk))
        if self._reject_equivalent_author(name, others):
            return cleaned
        self._require_similar_name_confirmation(name, others, cleaned)
        return cleaned

    def _reject_equivalent_author(self, name, others):
        for author in others:
            if self._is_equivalent_author(name, author):
                self.add_error("name", self._duplicate_name_error(author))
                return True
        return False

    def _is_equivalent_author(self, name, author):
        return _author_name_key(name) == _author_name_key(author.name)

    def _require_similar_name_confirmation(self, name, others, cleaned):
        matches = [author.name for author in others if self._is_similar_author(name, author)]
        if matches and not cleaned.get("confirm_similar_name"):
            self.add_error("name", self._similar_names_error(matches))

    def _is_similar_author(self, name, author):
        return (
            SequenceMatcher(
                None, _author_name_key(name), _author_name_key(author.name), autojunk=False
            ).ratio()
            >= 0.85
        )

    def _duplicate_name_error(self, author):
        return ValidationError(
            "An author named %(name)s already exists.",
            code="duplicate_author",
            params={"name": author.name},
        )

    def _similar_names_error(self, matches):
        return ValidationError(
            "Similar authors already exist: %(names)s. "
            "Select an existing author, or confirm this is a different name.",
            code="similar_author",
            params={"names": ", ".join(matches[:5])},
        )


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = [
            "title",
            "author",
            "language",
            "cover_image",
            "status",
            "started_at",
            "finished_at",
            "rating",
            "notes",
        ]
        widgets = {
            "cover_image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png"}),
            "started_at": forms.DateInput(attrs={"type": "date"}),
            "finished_at": forms.DateInput(attrs={"type": "date"}),
            "rating": forms.NumberInput(attrs={"step": "0.5", "min": "1", "max": "10"}),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["author"].queryset = Author.objects.order_by("name")
        self.fields["status"].choices = [
            (status.value, status.label) for status in ACTIVE_BOOK_STATUSES
        ]


class MovieForm(forms.ModelForm):
    class Meta:
        model = Movie
        fields = ["title", "poster", "language", "watched_at", "rating", "notes"]
        widgets = {
            "poster": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png"}),
            "watched_at": forms.DateInput(attrs={"type": "date"}),
            "rating": forms.NumberInput(attrs={"step": "0.5", "min": "1", "max": "10"}),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }
