"""Tests du controle d'acces au catalogue et de la resolution du contenu."""

import base64
import shutil
import tempfile
import uuid
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from . import content
from .models import Book, Category, Class, Student

User = get_user_model()

# Un JPEG minuscule encode en base64 (prefixe /9j/ = signature JPEG).
JPEG_B64 = base64.b64encode(
    bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")
).decode()
PNG_B64 = base64.b64encode(bytes.fromhex("89504e470d0a1a0a")).decode()


def make_book(title, pages=3, **kwargs):
    """Livre de test.

    `status` vaut `done` par defaut : seuls les livres dont le traitement est
    termine sont exposes par l'API.
    """
    return Book.objects.create(
        title=title,
        slug=kwargs.pop("slug", title.lower().replace(" ", "-")),
        publish_state=kwargs.pop("publish_state", "published"),
        page=pages,
        book_format=kwargs.pop("book_format", "pdf"),
        status=kwargs.pop("status", Book.STATUS_DONE),
        **kwargs,
    )


class ContentResolutionTests(TestCase):
    """Resolution des fichiers de pages sur le disque."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)

    def write(self, book_id, name, payload=JPEG_B64):
        directory = self.root / str(book_id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(payload, encoding="utf-8")

    def test_resolves_zero_padded_page(self):
        book_id = uuid.uuid4()
        self.write(book_id, "content_01.txt")
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.assertIsNotNone(content.resolve_page(book_id, 1))

    def test_resolves_unpadded_and_wide_padding(self):
        book_id = uuid.uuid4()
        self.write(book_id, "content_7.txt")
        self.write(book_id, "content_012.txt")
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.assertIsNotNone(content.resolve_page(book_id, 7))
            self.assertIsNotNone(content.resolve_page(book_id, 12))

    def test_cover_falls_back_to_first_available_page(self):
        """Un livre dont la numerotation ne commence pas a 1 a quand meme une couverture.

        C'est le cas des imports EPUB numerotes a partir de 0.
        """
        book_id = uuid.uuid4()
        self.write(book_id, "content_00.txt")
        self.write(book_id, "content_01.txt")
        directory = self.root / str(book_id)
        (directory / "content_01.txt").unlink()

        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            cover = content.resolve_cover(book_id)
            self.assertIsNotNone(cover)
            self.assertEqual(cover.name, "content_00.txt")

    def test_cover_is_none_without_any_file(self):
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.assertIsNone(content.resolve_cover(uuid.uuid4()))

    def test_cover_page_zero_means_generated(self):
        """0 = aucune page exploitable : le client dessine la couverture."""
        book_id = uuid.uuid4()
        self.write(book_id, "content_01.txt")
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.assertIsNone(content.resolve_cover(book_id, 0))

    def test_cover_page_selects_the_configured_page(self):
        book_id = uuid.uuid4()
        self.write(book_id, "content_01.txt")
        self.write(book_id, "content_03.txt")
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.assertEqual(content.resolve_cover(book_id, 3).name, "content_03.txt")
            self.assertEqual(content.resolve_cover(book_id, 1).name, "content_01.txt")

    def test_cover_page_falls_back_when_the_page_is_missing(self):
        """Un reglage pointant une page absente ne doit pas priver de couverture."""
        book_id = uuid.uuid4()
        self.write(book_id, "content_02.txt")
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.assertEqual(content.resolve_cover(book_id, 7).name, "content_02.txt")

    def test_cover_page_without_any_file(self):
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.assertIsNone(content.resolve_cover(uuid.uuid4(), 1))


class BookAccessControlTests(TestCase):
    """Un eleve ne doit atteindre que les livres autorises pour sa classe."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)

        self.classe_a = Class.objects.create(name="6eme A")
        self.classe_b = Class.objects.create(name="6eme B")

        self.allowed = make_book("Livre autorise", slug="livre-autorise")
        self.allowed.allowed_classes.add(self.classe_a)

        self.forbidden = make_book("Livre interdit", slug="livre-interdit")
        self.forbidden.allowed_classes.add(self.classe_b)

        for book in (self.allowed, self.forbidden):
            directory = self.root / str(book.id)
            directory.mkdir(parents=True)
            (directory / "content_01.txt").write_text(JPEG_B64, encoding="utf-8")

        self.student_user = User.objects.create_user(
            username="eleve", email="eleve@test.cd", password="motdepasse123"
        )
        Student.objects.create(
            user=self.student_user, school_class=self.classe_a, full_name="Eleve Test"
        )

        self.staff_user = User.objects.create_user(
            username="admin", email="admin@test.cd", password="motdepasse123", is_staff=True
        )

        self.client = APIClient()

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def test_list_returns_only_allowed_books(self):
        self.auth(self.student_user)
        response = self.client.get(reverse("book-list"))
        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.json()]
        self.assertEqual(titles, ["Livre autorise"])

    def test_list_does_not_expose_allowed_classes(self):
        self.auth(self.student_user)
        response = self.client.get(reverse("book-list"))
        self.assertNotIn("allowed_classes", response.json()[0])

    def test_staff_sees_everything(self):
        self.auth(self.staff_user)
        response = self.client.get(reverse("book-list"))
        self.assertEqual(len(response.json()), 2)

    def test_user_without_student_profile_sees_nothing(self):
        orphan = User.objects.create_user(
            username="orphelin", email="orphelin@test.cd", password="motdepasse123"
        )
        self.auth(orphan)
        response = self.client.get(reverse("book-list"))
        self.assertEqual(response.json(), [])

    def test_detail_of_forbidden_book_is_404(self):
        self.auth(self.student_user)
        url = reverse("book-detail", kwargs={"id": self.forbidden.id})
        self.assertEqual(self.client.get(url).status_code, 404)

    @override_settings(BOOKS_CONTENT_ROOT=None)
    def test_page_of_forbidden_book_is_404(self):
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.auth(self.student_user)
            url = reverse(
                "book-page-by-book-and-order",
                kwargs={"book_id": self.forbidden.id, "order": 1},
            )
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_page_of_allowed_book_is_served(self):
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.auth(self.student_user)
            url = reverse(
                "book-page-by-book-and-order",
                kwargs={"book_id": self.allowed.id, "order": 1},
            )
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["content"], JPEG_B64)
            self.assertEqual(body["mime"], "image/jpeg")

    def test_page_zero_is_rejected(self):
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.auth(self.student_user)
            url = reverse(
                "book-page-by-book-and-order",
                kwargs={"book_id": self.allowed.id, "order": 0},
            )
            self.assertEqual(self.client.get(url).status_code, 400)

    def test_cover_of_forbidden_book_is_404(self):
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.auth(self.student_user)
            url = reverse("book-cover", kwargs={"book_id": self.forbidden.id})
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_cover_without_content_reports_unavailable(self):
        """Un livre sans fichier renvoie 200/available=false, pas une erreur."""
        empty = make_book("Sans contenu", slug="sans-contenu")
        empty.allowed_classes.add(self.classe_a)

        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.auth(self.student_user)
            url = reverse("book-cover", kwargs={"book_id": empty.id})
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["available"])

    def test_cover_with_width_returns_a_thumbnail(self):
        try:
            import io

            from PIL import Image
        except ImportError:
            self.skipTest("Pillow n'est pas installe")

        directory = self.root / str(self.allowed.id)
        buffer = io.BytesIO()
        Image.new("RGB", (1400, 1900), (200, 120, 60)).save(buffer, format="JPEG", quality=95)
        full = base64.b64encode(buffer.getvalue()).decode()
        (directory / "content_01.txt").write_text(full, encoding="utf-8")

        with override_settings(
            BOOKS_CONTENT_ROOT=self.root, BOOKS_THUMBNAIL_ROOT=self.root / ".thumbnails"
        ):
            self.auth(self.student_user)
            url = reverse("book-cover", kwargs={"book_id": self.allowed.id})
            body = self.client.get(url, {"width": 400}).json()

            self.assertTrue(body["available"])
            self.assertLess(len(body["content"]), len(full))

    def test_cover_with_invalid_width_falls_back_to_full_image(self):
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.auth(self.student_user)
            url = reverse("book-cover", kwargs={"book_id": self.allowed.id})
            body = self.client.get(url, {"width": "abc"}).json()

            self.assertTrue(body["available"])
            self.assertEqual(body["content"], JPEG_B64)

    def test_availability_reports_real_page_count(self):
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.auth(self.student_user)
            url = reverse("book-availability", kwargs={"book_id": self.allowed.id})
            body = self.client.get(url).json()
            self.assertEqual(body["declared_pages"], 3)
            self.assertEqual(body["available_pages"], 1)
            self.assertTrue(body["has_content"])

    def test_anonymous_access_is_denied(self):
        self.assertEqual(self.client.get(reverse("book-list")).status_code, 401)

    def test_download_of_forbidden_book_is_404(self):
        """Le telechargement du fichier obeit au meme controle d'acces que le reste."""
        self.forbidden.book_file = "books/interdit.epub"
        self.forbidden.save()

        self.auth(self.student_user)
        url = reverse("book-download", kwargs={"book_id": self.forbidden.id})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_download_without_file_is_404(self):
        self.auth(self.student_user)
        url = reverse("book-download", kwargs={"book_id": self.allowed.id})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_download_requires_authentication(self):
        url = reverse("book-download", kwargs={"book_id": self.allowed.id})
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_book_file_path_is_null_without_file(self):
        self.auth(self.student_user)
        book = self.client.get(reverse("book-list")).json()[0]
        self.assertIsNone(book["book_file_path"])

    @override_settings(BOOKS_PUBLIC_BASE_URL="https://exemple.cd/")
    def test_book_file_path_uses_public_base_url(self):
        """Le lecteur EPUB charge le fichier via cette URL."""
        epub = make_book("Roman epub", slug="roman-epub", book_format="epub")
        epub.book_file = "books/roman.epub"
        epub.save()
        epub.allowed_classes.add(self.classe_a)

        self.auth(self.student_user)
        detail = self.client.get(reverse("book-detail", kwargs={"id": epub.id})).json()
        self.assertEqual(detail["book_file_path"], "https://exemple.cd/books/roman.epub")
        self.assertEqual(detail["book_format"], "epub")

    @override_settings(BOOKS_PUBLIC_BASE_URL="https://exemple.cd")
    def test_book_file_path_tolerates_base_url_without_slash(self):
        epub = make_book("Autre epub", slug="autre-epub", book_format="epub")
        epub.book_file = "books/autre.epub"
        epub.save()
        epub.allowed_classes.add(self.classe_a)

        self.auth(self.student_user)
        detail = self.client.get(reverse("book-detail", kwargs={"id": epub.id})).json()
        self.assertEqual(detail["book_file_path"], "https://exemple.cd/books/autre.epub")

    def test_epub_defaults_to_a_generated_cover(self):
        """Un EPUB cree recoit cover_page=0 : le client dessine la couverture."""
        epub = make_book("Roman en epub", slug="roman-en-epub", book_format="epub")
        epub.allowed_classes.add(self.classe_a)
        self.assertEqual(epub.cover_page, 0)

        # On depose une page : elle ne doit pas etre servie tant que le
        # reglage vaut 0.
        directory = self.root / str(epub.id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "content_01.txt").write_text(JPEG_B64, encoding="utf-8")

        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.auth(self.student_user)
            body = self.client.get(reverse("book-cover", kwargs={"book_id": epub.id})).json()
            self.assertFalse(body["available"])
            self.assertIsNone(body["content"])

    def test_cover_page_can_be_configured_for_an_epub(self):
        """Le reglage reste modifiable : un EPUB peut pointer une page reelle."""
        epub = make_book("Epub avec couverture", slug="epub-avec-couv", book_format="epub")
        epub.allowed_classes.add(self.classe_a)
        epub.cover_page = 2
        epub.save()

        directory = self.root / str(epub.id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "content_02.txt").write_text(JPEG_B64, encoding="utf-8")

        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.auth(self.student_user)
            body = self.client.get(reverse("book-cover", kwargs={"book_id": epub.id})).json()
            self.assertTrue(body["available"])
            self.assertEqual(body["content"], JPEG_B64)

    def test_pdf_keeps_page_one_by_default(self):
        self.assertEqual(self.allowed.cover_page, 1)
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.auth(self.student_user)
            body = self.client.get(reverse("book-cover", kwargs={"book_id": self.allowed.id})).json()
            self.assertTrue(body["available"])
            self.assertEqual(body["content"], JPEG_B64)

    def test_cover_page_zero_on_a_pdf_also_generates(self):
        """Le reglage n'est pas lie au format : un PDF peut aussi etre genere."""
        self.allowed.cover_page = 0
        self.allowed.save()
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.auth(self.student_user)
            body = self.client.get(reverse("book-cover", kwargs={"book_id": self.allowed.id})).json()
            self.assertFalse(body["available"])

    def test_availability_reports_real_page_count(self):
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.auth(self.student_user)
            url = reverse("book-availability", kwargs={"book_id": self.allowed.id})
            body = self.client.get(url).json()
            self.assertEqual(body["declared_pages"], 3)
            self.assertEqual(body["available_pages"], 1)
            self.assertTrue(body["has_content"])

    def test_anonymous_access_is_denied(self):
        self.assertEqual(self.client.get(reverse("book-list")).status_code, 401)

    def test_book_file_path_is_null_without_file(self):
        self.auth(self.student_user)
        book = self.client.get(reverse("book-list")).json()[0]
        self.assertIsNone(book["book_file_path"])

    @override_settings(BOOKS_PUBLIC_BASE_URL="https://exemple.cd/")
    def test_book_file_path_uses_public_base_url(self):
        """Le lecteur EPUB charge le fichier via cette URL."""
        epub = make_book("Roman epub", slug="roman-epub", book_format="epub")
        epub.book_file = "books/roman.epub"
        epub.save()
        epub.allowed_classes.add(self.classe_a)

        self.auth(self.student_user)
        detail = self.client.get(reverse("book-detail", kwargs={"id": epub.id})).json()
        self.assertEqual(detail["book_file_path"], "https://exemple.cd/books/roman.epub")
        self.assertEqual(detail["book_format"], "epub")

    @override_settings(BOOKS_PUBLIC_BASE_URL="https://exemple.cd")
    def test_book_file_path_tolerates_base_url_without_slash(self):
        epub = make_book("Autre epub", slug="autre-epub", book_format="epub")
        epub.book_file = "books/autre.epub"
        epub.save()
        epub.allowed_classes.add(self.classe_a)

        self.auth(self.student_user)
        detail = self.client.get(reverse("book-detail", kwargs={"id": epub.id})).json()
        self.assertEqual(detail["book_file_path"], "https://exemple.cd/books/autre.epub")

    def test_epub_always_reports_no_cover(self):
        """Un EPUB utilise toujours la couverture generee par le client.

        Meme lorsque des images de pages existent, elles commencent par des
        pages blanches puis une page de titre scannee : le visuel genere est
        plus lisible et homogene.
        """
        epub = make_book("Roman en epub", slug="roman-en-epub", book_format="epub")
        epub.allowed_classes.add(self.classe_a)

        # On depose volontairement des pages : elles ne doivent pas etre servies.
        directory = self.root / str(epub.id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "content_01.txt").write_text(JPEG_B64, encoding="utf-8")

        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.auth(self.student_user)
            body = self.client.get(reverse("book-cover", kwargs={"book_id": epub.id})).json()
            self.assertFalse(body["available"])
            self.assertIsNone(body["content"])

    def test_books_still_processing_are_hidden(self):
        """Un livre non traite n'a pas de pages exploitables : il reste masque."""
        for state in (Book.STATUS_PENDING, Book.STATUS_PROCESSING, Book.STATUS_ERROR):
            with self.subTest(status=state):
                book = make_book(f"En cours {state}", slug=f"en-cours-{state}", status=state)
                book.allowed_classes.add(self.classe_a)

                self.auth(self.student_user)
                titles = [item["title"] for item in self.client.get(reverse("book-list")).json()]
                self.assertNotIn(book.title, titles)

                detail = reverse("book-detail", kwargs={"id": book.id})
                self.assertEqual(self.client.get(detail).status_code, 404)

    def test_staff_also_only_sees_processed_books(self):
        pending = make_book("Non traite", slug="non-traite", status=Book.STATUS_PENDING)
        pending.allowed_classes.add(self.classe_a)

        self.auth(self.staff_user)
        titles = [item["title"] for item in self.client.get(reverse("book-list")).json()]
        self.assertNotIn("Non traite", titles)


class CategoryTests(TestCase):
    """Domaines thematiques : socle, exposition dans l'API, pre-classement."""

    SEEDED_SLUGS = [
        "sciences-et-mathematiques",
        "informatique-technologie-et-robotique",
        "langues-et-litterature",
        "sciences-humaines-et-sociales",
        "economie-gestion-et-entrepreneuriat",
        "arts-et-culture",
        "developpement-personnel-et-orientation",
        "religion-et-spiritualite",
        "encyclopedies-et-ouvrages-de-reference",
    ]

    def setUp(self):
        self.classe = Class.objects.create(name="5eme A")
        self.user = User.objects.create_user(
            username="eleve-cat", email="cat@test.cd", password="motdepasse123"
        )
        Student.objects.create(
            user=self.user, school_class=self.classe, full_name="Eleve Categorie"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_migration_seeds_the_nine_categories(self):
        slugs = list(Category.objects.values_list("slug", flat=True))
        for slug in self.SEEDED_SLUGS:
            self.assertIn(slug, slugs)

    def test_categories_are_ordered_for_display(self):
        """L'ordre est celui du classement retenu, pas l'alphabet."""
        names = list(Category.objects.values_list("slug", flat=True))
        self.assertEqual(names[0], "sciences-et-mathematiques")
        self.assertEqual(names[8], "encyclopedies-et-ouvrages-de-reference")

    def test_slug_is_derived_from_the_name(self):
        category = Category.objects.create(name="Vie pratique")
        self.assertEqual(category.slug, "vie-pratique")

    def test_slug_stays_unique(self):
        Category.objects.create(name="Vie pratique")
        duplicate = Category.objects.create(name="Vie Pratique !")
        self.assertEqual(duplicate.slug, "vie-pratique-1")

    def test_api_exposes_the_categories_of_a_book(self):
        book = make_book("Algebre 4eme", slug="algebre-4eme")
        book.allowed_classes.add(self.classe)
        maths = Category.objects.get(slug="sciences-et-mathematiques")
        book.categories.add(maths)

        payload = self.client.get(reverse("book-list")).json()[0]
        self.assertEqual(
            payload["categories"],
            [
                {
                    "id": maths.id,
                    "name": maths.name,
                    "slug": maths.slug,
                    "order": maths.order,
                }
            ],
        )

    def test_a_book_can_carry_several_categories(self):
        book = make_book("Robotique en classe", slug="robotique-en-classe")
        book.allowed_classes.add(self.classe)
        book.categories.set(
            Category.objects.filter(
                slug__in=[
                    "sciences-et-mathematiques",
                    "informatique-technologie-et-robotique",
                ]
            )
        )

        payload = self.client.get(reverse("book-list")).json()[0]
        self.assertEqual(len(payload["categories"]), 2)

    def test_an_unclassified_book_reports_an_empty_list(self):
        book = make_book("Sans categorie", slug="sans-categorie")
        book.allowed_classes.add(self.classe)

        payload = self.client.get(reverse("book-list")).json()[0]
        self.assertEqual(payload["categories"], [])

    def test_categories_do_not_leak_the_access_rule(self):
        """L'ajout du champ ne doit pas rouvrir la fuite d'`allowed_classes`."""
        book = make_book("Controle", slug="controle-categorie")
        book.allowed_classes.add(self.classe)

        payload = self.client.get(reverse("book-list")).json()[0]
        self.assertNotIn("allowed_classes", payload)


class ClassifyBooksCommandTests(TestCase):
    """Pre-classement automatique : propose, n'ecrit que sur demande."""

    def run_command(self, **options):
        out = StringIO()
        call_command("classify_books", stdout=out, stderr=out, **options)
        return out.getvalue()

    def test_dry_run_writes_nothing(self):
        book = make_book("Cours de mathematiques", slug="cours-de-mathematiques")
        output = self.run_command()

        self.assertEqual(book.categories.count(), 0)
        self.assertIn("Simulation", output)

    def test_apply_assigns_the_matching_category(self):
        book = make_book("Cours de mathematiques", slug="cours-de-mathematiques")
        self.run_command(apply=True)

        self.assertEqual(
            list(book.categories.values_list("slug", flat=True)),
            ["sciences-et-mathematiques"],
        )

    def test_a_title_can_match_several_domains(self):
        book = make_book("Initiation a la robotique et aux sciences", slug="robot-sciences")
        self.run_command(apply=True)

        slugs = set(book.categories.values_list("slug", flat=True))
        self.assertEqual(
            slugs,
            {"sciences-et-mathematiques", "informatique-technologie-et-robotique"},
        )

    def test_an_unrecognised_title_is_left_undecided(self):
        book = make_book("Le grand voyage", slug="le-grand-voyage")
        output = self.run_command(apply=True)

        self.assertEqual(book.categories.count(), 0)
        self.assertIn("indecis", output)

    def test_word_boundaries_avoid_false_positives(self):
        """« partage » ne doit pas declencher la categorie « art »."""
        book = make_book("Le partage des taches", slug="le-partage-des-taches")
        self.run_command(apply=True)

        self.assertEqual(book.categories.count(), 0)

    def test_an_already_classified_book_is_left_alone(self):
        book = make_book("Cours de mathematiques", slug="cours-de-mathematiques")
        arts = Category.objects.get(slug="arts-et-culture")
        book.categories.add(arts)

        self.run_command(apply=True)

        self.assertEqual(list(book.categories.all()), [arts])

    def test_force_reclassifies_an_existing_book(self):
        book = make_book("Cours de mathematiques", slug="cours-de-mathematiques")
        book.categories.add(Category.objects.get(slug="arts-et-culture"))

        self.run_command(apply=True, force=True)

        self.assertEqual(
            list(book.categories.values_list("slug", flat=True)),
            ["sciences-et-mathematiques"],
        )

    def test_a_collection_prefix_is_not_a_subject(self):
        """« STEAM SCIENCE. » ouvre 40 titres du fonds : c'est un editeur.

        Compte comme mot-cle, il rangerait « Learn to Draw » dans les
        sciences. La tete de titre partagee par assez d'ouvrages est donc
        ecartee du score.
        """
        for index in range(5):
            make_book(f"COLLECTION SCIENCES. Cours de dessin {index}", slug=f"coll-{index}")

        self.run_command(apply=True)

        for book in Book.objects.all():
            self.assertEqual(
                list(book.categories.values_list("slug", flat=True)), ["arts-et-culture"]
            )

    def test_an_isolated_prefix_keeps_its_weight(self):
        """Une tete de titre unique reste un signal : rien n'est code en dur."""
        book = make_book("COURS DE SCIENCES. Cours de dessin", slug="cours-sciences")

        self.run_command(apply=True)

        self.assertEqual(
            set(book.categories.values_list("slug", flat=True)),
            {"sciences-et-mathematiques", "arts-et-culture"},
        )

    def test_the_description_alone_needs_several_hits(self):
        """Une seule occurrence dans la description ne suffit pas a classer."""
        weak = make_book("Recueil", slug="recueil", description="Un peu de musique.")
        strong = make_book(
            "Anthologie",
            slug="anthologie",
            description="Musique, danse et peinture : trois formes d'art.",
        )
        self.run_command(apply=True)

        self.assertEqual(weak.categories.count(), 0)
        self.assertEqual(
            list(strong.categories.values_list("slug", flat=True)), ["arts-et-culture"]
        )
