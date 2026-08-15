"""Tests du controle d'acces au catalogue et de la resolution du contenu."""

import base64
import shutil
import tempfile
import uuid
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from . import content
from .models import Book, Class, Student

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

    def test_binary_page_is_base64_encoded(self):
        book_id = uuid.uuid4()
        directory = self.root / str(book_id)
        directory.mkdir(parents=True)
        (directory / "content_01.jpg").write_bytes(bytes.fromhex("ffd8ffe000104a464946"))

        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            path = content.resolve_page(book_id, 1)
            self.assertIsNotNone(path)
            payload = content.read_page_payload(path)
            self.assertEqual(base64.b64decode(payload)[:2], b"\xff\xd8")

    def test_invalid_book_id_cannot_escape_content_root(self):
        with override_settings(BOOKS_CONTENT_ROOT=self.root):
            self.assertIsNone(content.book_directory("../../etc"))
            self.assertIsNone(content.resolve_page("../../etc", 1))

    def test_guess_mime(self):
        self.assertEqual(content.guess_mime(JPEG_B64), "image/jpeg")
        self.assertEqual(content.guess_mime(PNG_B64), "image/png")

    def test_thumbnail_is_smaller_than_source(self):
        """La vignette doit reellement alleger la couverture, sinon elle n'a pas d'interet."""
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow n'est pas installe")

        import io

        book_id = uuid.uuid4()
        directory = self.root / str(book_id)
        directory.mkdir(parents=True)

        buffer = io.BytesIO()
        Image.new("RGB", (1600, 2200), (40, 90, 140)).save(buffer, format="JPEG", quality=95)
        source_b64 = base64.b64encode(buffer.getvalue()).decode()
        (directory / "content_01.txt").write_text(source_b64, encoding="utf-8")

        with override_settings(
            BOOKS_CONTENT_ROOT=self.root, BOOKS_THUMBNAIL_ROOT=self.root / ".thumbnails"
        ):
            path = content.resolve_cover(book_id)
            result = content.build_thumbnail(path, 400)

            self.assertIsNotNone(result)
            payload, mime = result
            self.assertEqual(mime, "image/jpeg")
            self.assertLess(len(payload), len(source_b64))

            with Image.open(io.BytesIO(base64.b64decode(payload))) as thumb:
                self.assertLessEqual(thumb.width, 400)

            # Deuxieme appel : sert le fichier mis en cache.
            self.assertEqual(content.build_thumbnail(path, 400)[0], payload)

    def test_thumbnail_returns_none_for_unreadable_image(self):
        """Un fichier illisible ne doit pas faire echouer la couverture."""
        book_id = uuid.uuid4()
        self.write(book_id, "content_01.txt", "pas du tout une image")

        with override_settings(
            BOOKS_CONTENT_ROOT=self.root, BOOKS_THUMBNAIL_ROOT=self.root / ".thumbnails"
        ):
            path = content.resolve_cover(book_id)
            self.assertIsNone(content.build_thumbnail(path, 400))


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
