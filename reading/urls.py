from django.urls import path

from . import views

urlpatterns = [
    path("", views.book_list, name="book-list"),
    path("movies/", views.movie_list, name="movie-list"),
]
