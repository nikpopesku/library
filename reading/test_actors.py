from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .forms import MovieForm
from .models import Actor, Movie


class ActorModelTests(TestCase):
    def test_names_are_unique_and_sorted(self):
        Actor.objects.create(name="Zoe Saldana")
        actor = Actor.objects.create(name="Amy Adams")

        self.assertEqual(str(actor), "Amy Adams")
        self.assertEqual(
            list(Actor.objects.values_list("name", flat=True)), ["Amy Adams", "Zoe Saldana"]
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Actor.objects.create(name="Amy Adams")

    def test_actor_can_belong_to_several_movies_and_be_removed_safely(self):
        actor = Actor.objects.create(name="Amy Adams")
        arrival = Movie.objects.create(title="Arrival")
        doubt = Movie.objects.create(title="Doubt")
        arrival.actors.add(actor)
        doubt.actors.add(actor)

        self.assertCountEqual(actor.movies.all(), [arrival, doubt])
        actor.delete()
        self.assertEqual(Movie.objects.count(), 2)
        self.assertFalse(arrival.actors.exists())

    def test_movie_form_accepts_no_actors(self):
        form = MovieForm(data={"title": "Arrival"})

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.save().actors.exists())


class MovieActorAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="actor-admin", email="actors@example.invalid", password="test-only-password"
        )
        cls.amy = Actor.objects.create(name="Amy Adams")
        cls.jeremy = Actor.objects.create(name="Jeremy Renner")

    def setUp(self):
        self.client.force_login(self.user)

    def test_movie_form_offers_multiple_autocomplete_and_add_actor_popup(self):
        response = self.client.get(reverse("admin:books_movie_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_actors"')
        self.assertContains(response, "admin-autocomplete")
        self.assertContains(response, 'data-field-name="actors"')
        widget = response.context["adminform"].form.fields["actors"].widget.widget
        self.assertTrue(widget.allow_multiple_selected)
        self.assertContains(response, 'id="add_id_actors"')
        self.assertContains(response, reverse("admin:books_actor_add"))

    def test_can_assign_replace_and_clear_movie_actors(self):
        response = self.client.post(
            reverse("admin:books_movie_add"),
            {"title": "Arrival", "actors": [self.amy.pk, self.jeremy.pk], "_save": "Save"},
        )

        self.assertEqual(response.status_code, 302)
        movie = Movie.objects.get(title="Arrival")
        self.assertCountEqual(movie.actors.all(), [self.amy, self.jeremy])
        for actor_ids, expected in (([self.amy.pk], [self.amy]), ([], [])):
            with self.subTest(actor_ids=actor_ids):
                response = self.client.post(
                    reverse("admin:books_movie_change", args=[movie.pk]),
                    {"title": "Arrival", "actors": actor_ids, "_save": "Save"},
                )
                self.assertEqual(response.status_code, 302)
                self.assertCountEqual(movie.actors.all(), expected)

    def test_actor_autocomplete_search_returns_matching_existing_actors(self):
        response = self.client.get(
            reverse("admin:autocomplete"),
            {"app_label": "books", "model_name": "movie", "field_name": "actors", "term": "Amy"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["results"], [{"id": str(self.amy.pk), "text": "Amy Adams"}]
        )

    def test_can_create_actor_in_popup_and_reject_duplicate(self):
        url = reverse("admin:books_actor_add")
        response = self.client.post(url, {"name": "Forest Whitaker", "_popup": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-popup-response")
        self.assertTrue(Actor.objects.filter(name="Forest Whitaker").exists())
        duplicate = self.client.post(url, {"name": "Forest Whitaker", "_popup": "1"})
        self.assertContains(duplicate, "already exists")
        self.assertEqual(Actor.objects.filter(name="Forest Whitaker").count(), 1)

    def test_movie_search_by_actor_does_not_duplicate_movies(self):
        movie = Movie.objects.create(title="Arrival")
        movie.actors.add(self.amy, Actor.objects.create(name="Amy Example"))
        Movie.objects.create(title="Unrelated")

        response = self.client.get(reverse("admin:books_movie_changelist"), {"q": "Amy"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["cl"].result_list), [movie])

    def test_actor_changelist_is_searchable(self):
        response = self.client.get(reverse("admin:books_actor_changelist"), {"q": "Renner"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["cl"].result_list), [self.jeremy])

    def test_public_cannot_create_actors(self):
        self.client.logout()
        response = self.client.post(reverse("admin:books_actor_add"), {"name": "Unauthorized"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Actor.objects.filter(name="Unauthorized").exists())


class MovieActorListTests(TestCase):
    def test_actors_render_as_escaped_pills_in_name_order(self):
        movie = Movie.objects.create(title="Arrival")
        movie.actors.add(
            Actor.objects.create(name="Jeremy Renner"), Actor.objects.create(name="Amy <Adams>")
        )
        Movie.objects.create(title="No actors")

        response = self.client.get(reverse("movie-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<span class="tag-pill">Amy &lt;Adams&gt;</span>', html=True)
        self.assertContains(response, '<span class="tag-pill">Jeremy Renner</span>', html=True)
        self.assertNotContains(response, "Amy <Adams>")
        self.assertLess(
            response.content.index(b"Amy &lt;Adams&gt;"), response.content.index(b"Jeremy Renner")
        )
        self.assertContains(response, "No actors")

    def test_actor_rendering_uses_one_prefetch_for_the_page(self):
        actor = Actor.objects.create(name="Amy Adams")
        for index in range(3):
            Movie.objects.create(title=f"Movie {index}").actors.add(actor)

        response = self.client.get(reverse("movie-list"))

        with self.assertNumQueries(0):
            self.assertEqual(
                [
                    [actor.name for actor in movie.actors.all()]
                    for movie in response.context["movies"]
                ],
                [["Amy Adams"]] * 3,
            )
