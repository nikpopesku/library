from django.contrib import admin
from django.db.models import Count, F
from django.utils.html import format_html

from .forms import AuthorForm, BookForm, MovieForm
from .models import Actor, Author, Book, Language, Movie, Tag


def _thumbnail(image, noun, title):
    if not image:
        return "—"
    return format_html(
        (
            '<img src="{}" alt="{} for {}" '
            'style="width: 36px; height: 54px; object-fit: cover; border-radius: 4px;" />'
        ),
        image.url,
        noun,
        title,
    )


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    form = BookForm
    list_display = (
        "cover_thumbnail",
        "title",
        "author",
        "language",
        "status",
        "started_at",
        "finished_at",
        "rating",
    )
    list_filter = ("finished_at", "status", "language", "rating")
    search_fields = ("title", "author__name", "notes", "tags__name", "language__name")
    ordering = (F("finished_at").desc(nulls_last=True), "title")
    autocomplete_fields = ("author", "language", "tags")

    @admin.display(description="Cover")
    def cover_thumbnail(self, obj):
        return _thumbnail(obj.cover_image, "Cover", obj.title)


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    form = MovieForm
    list_display = ("poster_thumbnail", "title", "language", "watched_at", "rating")
    list_filter = ("watched_at", "language", "rating")
    search_fields = ("title", "notes", "language__name", "actors__name")
    ordering = (F("watched_at").desc(nulls_last=True), "title")
    autocomplete_fields = ("language", "actors")

    @admin.display(description="Poster")
    def poster_thumbnail(self, obj):
        return _thumbnail(obj.poster, "Poster", obj.title)


@admin.register(Actor)
class ActorAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    form = AuthorForm
    list_display = ("name", "book_count")
    search_fields = ("name",)
    ordering = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(books_total=Count("books", distinct=True))

    @admin.display(description="Books", ordering="books_total")
    def book_count(self, obj):
        return obj.books_total


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "book_count", "is_used")
    search_fields = ("name",)
    ordering = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(books_total=Count("books", distinct=True))

    @admin.display(description="Books", ordering="books_total")
    def book_count(self, obj):
        return obj.books_total

    @admin.display(boolean=True, description="Used")
    def is_used(self, obj):
        return obj.books_total > 0


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ("name", "book_count", "movie_count")
    search_fields = ("name",)
    ordering = ("name",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                books_total=Count("books", distinct=True),
                movies_total=Count("movies", distinct=True),
            )
        )

    @admin.display(description="Books", ordering="books_total")
    def book_count(self, obj):
        return obj.books_total

    @admin.display(description="Movies", ordering="movies_total")
    def movie_count(self, obj):
        return obj.movies_total
