from django.core.paginator import Paginator
from django.db.models import Case, Count, F, IntegerField, Q, Value, When
from django.http import HttpResponseBadRequest
from django.shortcuts import render

from .models import ACTIVE_BOOK_STATUSES, Author, Book, BookStatus, Language, Movie

PAGE_SIZE_OPTIONS = (10, 25, 50, 100)
DEFAULT_PAGE_SIZE = 25


def _build_querystring(request, **updates):
    params = request.GET.copy()
    for key, value in updates.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value

    query_string = params.urlencode()
    return f"{request.path}?{query_string}" if query_string else request.path


def _sort_link(request, selected_sort, field):
    is_active = selected_sort.lstrip("-") == field
    next_sort = f"-{field}" if selected_sort == field else field
    aria_sort = (
        "ascending"
        if selected_sort == field
        else "descending"
        if selected_sort == f"-{field}"
        else "none"
    )
    direction = "▲" if selected_sort == field else "▼" if selected_sort == f"-{field}" else "↕"
    return {
        "url": _build_querystring(request, sort=next_sort, page=1),
        "aria_sort": aria_sort,
        "direction": direction,
        "is_active": is_active,
    }


def _selected_page_size(request):
    try:
        page_size = int(request.GET.get("page_size", DEFAULT_PAGE_SIZE))
    except ValueError:
        return DEFAULT_PAGE_SIZE

    return page_size if page_size in PAGE_SIZE_OPTIONS else DEFAULT_PAGE_SIZE


def _authors_with_active_books():
    return Author.objects.filter(books__status__in=ACTIVE_BOOK_STATUSES).distinct().order_by("name")


def _apply_language_filter(books, languages, selected_language):
    return _apply_id_filter(books, languages, selected_language, "language_id")


def _apply_author_filter(books, authors, selected_author):
    return _apply_id_filter(books, authors, selected_author, "author_id")


def _apply_id_filter(books, choices, selected_id, field):
    if not selected_id:
        return books, ""
    try:
        chosen_id = int(selected_id)
    except ValueError:
        return books, ""
    if not choices.filter(id=chosen_id).exists():
        return books, ""
    return books.filter(**{field: chosen_id}), selected_id


_BOOK_DEFAULT_SORT = (F("finished_at").desc(nulls_last=True), "title")
_MOVIE_DEFAULT_SORT = (F("watched_at").desc(nulls_last=True), "title")


def _nullable(field, descending=False):
    expression = F(field).desc(nulls_last=True) if descending else F(field).asc(nulls_last=True)
    return (expression, "title")


def _orderings_both_ways(key, ascending, descending):
    return {key: ascending, f"-{key}": descending}


def _nullable_orderings(key, field):
    return _orderings_both_ways(key, _nullable(field), _nullable(field, descending=True))


def _book_sort_orderings():
    status_order = Case(
        When(status=BookStatus.WILL_READ, then=Value(0)),
        When(status=BookStatus.READING, then=Value(1)),
        When(status=BookStatus.READ, then=Value(2)),
        output_field=IntegerField(),
    )
    return {
        **_orderings_both_ways("title", ("title",), ("-title",)),
        **_nullable_orderings("author", "author__name"),
        **_nullable_orderings("language", "language__name"),
        **_orderings_both_ways("status", (status_order, "title"), (status_order.desc(), "title")),
        **_nullable_orderings("started_at", "started_at"),
        **_nullable_orderings("finished_at", "finished_at"),
        **_nullable_orderings("rating", "rating"),
    }


def _movie_sort_orderings():
    return {
        **_nullable_orderings("release_year", "release_year"),
        **_orderings_both_ways("title", ("title",), ("-title",)),
        **_nullable_orderings("language", "language__name"),
        **_nullable_orderings("watched_at", "watched_at"),
        **_nullable_orderings("rating", "rating"),
    }


def _apply_sort(queryset, selected_sort, orderings, default):
    return queryset.order_by(*orderings.get(selected_sort, default))


def _preserved_params(**selected):
    return [(name, value) for name, value in selected.items() if value]


def _available_years(queryset, field):
    dates = queryset.filter(**{f"{field}__isnull": False}).dates(field, "year", order="DESC")
    return [d.year for d in dates]


def _apply_year_filter(items, years, selected_year, field):
    try:
        year = int(selected_year)
    except ValueError:
        return items, ""
    if year not in years:
        return items, ""
    return items.filter(**{f"{field}__year": year}), selected_year


def book_list(request):
    selected_status = request.GET.get("status", "")
    selected_year = request.GET.get("year", "")
    selected_language = request.GET.get("language", "")
    selected_author = request.GET.get("author", "")
    selected_sort = request.GET.get("sort", "")

    base_books = (
        Book.objects.exclude(status=BookStatus.DELETED)
        .select_related("author", "language")
        .prefetch_related("tags")
    )
    books = base_books
    if selected_status:
        if selected_status not in [status.value for status in ACTIVE_BOOK_STATUSES]:
            return HttpResponseBadRequest("Unknown status")
        books = books.filter(status=selected_status)

    years = sorted(
        {
            d.year
            for d in Book.objects.exclude(status=BookStatus.DELETED)
            .filter(Q(finished_at__isnull=False) | Q(started_at__isnull=False))
            .values_list("finished_at", "started_at")
            for d in (d[0] or d[1],)
            if d is not None
        },
        reverse=True,
    )

    if selected_year:
        try:
            year_int = int(selected_year)
            if year_int not in years:
                selected_year = ""
            else:
                books = books.filter(Q(finished_at__year=year_int) | Q(started_at__year=year_int))
        except ValueError:
            selected_year = ""

    languages = Language.objects.order_by("name")
    books, selected_language = _apply_language_filter(books, languages, selected_language)

    authors = _authors_with_active_books()
    books, selected_author = _apply_author_filter(books, authors, selected_author)

    books = _apply_sort(books, selected_sort, _book_sort_orderings(), _BOOK_DEFAULT_SORT)

    counts_by_status = {
        row["status"]: row["total"]
        for row in base_books.order_by().values("status").annotate(total=Count("id"))
    }
    counts = {
        status.value: counts_by_status.get(status.value, 0) for status in ACTIVE_BOOK_STATUSES
    }

    page_size = _selected_page_size(request)
    paginator = Paginator(books, page_size)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return render(
        request,
        "reading/book_list.html",
        {
            "books": page_obj.object_list,
            "page_obj": page_obj,
            "page_range": paginator.get_elided_page_range(page_obj.number),
            "is_paginated": page_obj.has_other_pages(),
            "page_sizes": PAGE_SIZE_OPTIONS,
            "selected_page_size": page_size,
            "preserved_params": _preserved_params(
                status=selected_status,
                year=selected_year,
                language=selected_language,
                author=selected_author,
                sort=selected_sort,
            ),
            "statuses": ACTIVE_BOOK_STATUSES,
            "selected_status": selected_status,
            "selected_year": selected_year,
            "languages": languages,
            "selected_language": selected_language,
            "authors": authors,
            "selected_author": selected_author,
            "selected_sort": selected_sort,
            "sort_links": {
                "title": _sort_link(request, selected_sort, "title"),
                "author": _sort_link(request, selected_sort, "author"),
                "language": _sort_link(request, selected_sort, "language"),
                "status": _sort_link(request, selected_sort, "status"),
                "started_at": _sort_link(request, selected_sort, "started_at"),
                "finished_at": _sort_link(request, selected_sort, "finished_at"),
                "rating": _sort_link(request, selected_sort, "rating"),
            },
            "years": years,
            "counts": counts,
            "total_count": books.count(),
            "all_count": base_books.count(),
        },
    )


def movie_list(request):
    selected_year = request.GET.get("year", "")
    selected_language = request.GET.get("language", "")
    selected_sort = request.GET.get("sort", "")

    base_movies = Movie.objects.select_related("language").prefetch_related("actors")
    years = _available_years(base_movies, "watched_at")
    movies, selected_year = _apply_year_filter(base_movies, years, selected_year, "watched_at")

    languages = Language.objects.filter(movies__isnull=False).distinct().order_by("name")
    movies, selected_language = _apply_id_filter(
        movies, languages, selected_language, "language_id"
    )
    movies = _apply_sort(movies, selected_sort, _movie_sort_orderings(), _MOVIE_DEFAULT_SORT)

    page_size = _selected_page_size(request)
    paginator = Paginator(movies, page_size)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return render(
        request,
        "reading/movie_list.html",
        {
            "movies": page_obj.object_list,
            "page_obj": page_obj,
            "page_range": paginator.get_elided_page_range(page_obj.number),
            "is_paginated": page_obj.has_other_pages(),
            "page_sizes": PAGE_SIZE_OPTIONS,
            "selected_page_size": page_size,
            "preserved_params": _preserved_params(
                year=selected_year, language=selected_language, sort=selected_sort
            ),
            "years": years,
            "selected_year": selected_year,
            "languages": languages,
            "selected_language": selected_language,
            "selected_sort": selected_sort,
            "sort_links": {
                key: _sort_link(request, selected_sort, key)
                for key in ("title", "release_year", "language", "watched_at", "rating")
            },
            "total_count": movies.count(),
        },
    )
