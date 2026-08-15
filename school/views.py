import datetime

from django.conf import settings
from django.http import FileResponse
from django.utils import timezone
from itsdangerous import URLSafeSerializer
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import content
from .models import Book, BookPage
from .serializers import BookPageSerializer, BookSerializer


def accessible_books(user):
    """Livres qu'un utilisateur a le droit de consulter.

    - staff / superuser : tout le catalogue ;
    - eleve : uniquement les livres dont `allowed_classes` contient sa classe ;
    - tout autre cas (compte sans profil eleve, eleve sans classe) : rien.

    Dans tous les cas, seuls les livres dont le traitement est termine
    (`status='done'`) sont exposes : un livre en cours de conversion n'a pas
    encore de pages exploitables sur le disque.
    """
    if not user or not user.is_authenticated:
        return Book.objects.none()

    processed = Book.objects.filter(status=Book.STATUS_DONE)

    if user.is_staff or user.is_superuser:
        return processed

    # `student_profile` est l'accesseur inverse du OneToOne Student.user.
    # Django fait heriter RelatedObjectDoesNotExist d'AttributeError, donc
    # getattr avec valeur par defaut couvre le cas "pas de profil eleve".
    student = getattr(user, "student_profile", None)
    if student is None or student.school_class_id is None:
        return Book.objects.none()

    return processed.filter(allowed_classes=student.school_class_id).distinct()


class AccessibleBookMixin:
    """Restreint une vue aux livres accessibles a l'utilisateur courant."""

    permission_classes = [IsAuthenticated]

    def get_accessible_books(self):
        return accessible_books(self.request.user)

    def get_book_or_404(self, book_id):
        book = self.get_accessible_books().filter(id=book_id).first()
        if book is None:
            # Meme reponse qu'un livre inexistant : on n'indique pas a un eleve
            # qu'un livre existe mais ne lui est pas accessible.
            raise NotFound("Livre introuvable.")
        return book


class BookListAPIView(AccessibleBookMixin, generics.ListAPIView):
    """GET /api/apps/books/ — catalogue accessible a l'utilisateur."""

    serializer_class = BookSerializer

    def get_queryset(self):
        user = self.request.user
        books = self.get_accessible_books()
        if user.is_staff or user.is_superuser:
            return books.order_by("-created_at")
        return books.order_by("title")


class BookDetailAPIView(AccessibleBookMixin, generics.RetrieveAPIView):
    """GET /api/apps/books/<uuid:id>/"""

    serializer_class = BookSerializer
    lookup_field = "id"

    def get_queryset(self):
        return self.get_accessible_books()


class BookPagesByBookAPIView(AccessibleBookMixin, generics.ListAPIView):
    """GET /api/apps/books/<uuid:book_id>/pages/ — pages stockees en base."""

    serializer_class = BookPageSerializer

    def get_queryset(self):
        book = self.get_book_or_404(self.kwargs["book_id"])
        return BookPage.objects.filter(book=book).order_by("order")


class BookPageByBookAndOrderAPIView(AccessibleBookMixin, APIView):
    """GET /api/apps/books/<uuid:book_id>/page/<int:order>/

    Renvoie l'image de la page encodee en base64, lue sur le disque.
    """

    def get(self, request, book_id, order):
        book = self.get_book_or_404(book_id)

        if order < 1:
            return Response(
                {"detail": "Le numero de page commence a 1."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        path = content.resolve_page(book_id, order)
        if path is None:
            return Response(
                {"detail": "Page non trouvee."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            payload = content.read_page_payload(path)
        except OSError as exc:
            return Response(
                {"detail": f"Erreur de lecture du fichier: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "id": f"{book_id}:{order}",
                "title": book.title,
                "book": str(book_id),
                "order": order,
                "mime": content.guess_mime(payload),
                "content": payload,
            }
        )


class BookCoverAPIView(AccessibleBookMixin, APIView):
    """GET /api/apps/books/<uuid:book_id>/cover/

    Couverture du livre. Contrairement a `page/1/`, cette vue retombe sur la
    premiere page disponible quelle que soit la numerotation, ce qui couvre les
    livres (EPUB notamment) dont les pages ne commencent pas a `content_01.txt`.

    Un livre sans aucun fichier de page renvoie 200 avec `available: false` :
    le client affiche alors une couverture generee, sans requete en erreur ni
    nouvelle tentative a chaque affichage.
    """

    def get(self, request, book_id):
        book = self.get_book_or_404(book_id)

        # `cover_page` est reglable dans l'administration : 0 signifie qu'aucune
        # page ne convient et que le client doit dessiner sa couverture generee.
        path = content.resolve_cover(book_id, book.cover_page)

        if path is None:
            return Response(
                {
                    "id": f"{book_id}:cover",
                    "book": str(book_id),
                    "title": book.title,
                    "available": False,
                    "content": None,
                    "mime": None,
                }
            )

        # `?width=` demande une vignette : une page pleine resolution pese
        # environ 1 Mo, ce qui est disproportionne pour une grille de vignettes.
        width = request.query_params.get("width")
        if width:
            try:
                thumbnail = content.build_thumbnail(path, int(width))
            except (TypeError, ValueError):
                thumbnail = None

            if thumbnail is not None:
                payload, mime = thumbnail
                return Response(
                    {
                        "id": f"{book_id}:cover",
                        "book": str(book_id),
                        "title": book.title,
                        "available": True,
                        "mime": mime,
                        "content": payload,
                    }
                )

        try:
            payload = content.read_page_payload(path)
        except OSError as exc:
            return Response(
                {"detail": f"Erreur de lecture du fichier: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "id": f"{book_id}:cover",
                "book": str(book_id),
                "title": book.title,
                "available": True,
                "mime": content.guess_mime(payload),
                "content": payload,
            }
        )


class BookAvailabilityAPIView(AccessibleBookMixin, APIView):
    """GET /api/apps/books/<uuid:book_id>/availability/

    Nombre de pages reellement presentes sur le disque. Le champ `page` du
    modele provient de l'import et peut differer du contenu disponible ; le
    client s'appuie sur cette valeur pour le telechargement hors-ligne.
    """

    def get(self, request, book_id):
        book = self.get_book_or_404(book_id)
        available = content.count_pages(book_id)
        return Response(
            {
                "book": str(book_id),
                "declared_pages": book.page,
                "available_pages": available,
                "has_content": available > 0,
            }
        )


# Signature des liens de telechargement temporaires.
download_link_serializer = URLSafeSerializer(settings.SECRET_KEY, salt="book-download")

#: Duree de validite d'un lien de telechargement, et marge en dessous de
#: laquelle on en regenere un plutot que de servir un jeton presque expire.
DOWNLOAD_TOKEN_LIFETIME = datetime.timedelta(minutes=5)
DOWNLOAD_TOKEN_MIN_VALIDITY = datetime.timedelta(minutes=3)


class BookDownloadView(AccessibleBookMixin, APIView):
    """GET /api/apps/books/<uuid:book_id>/download/

    Sert le fichier source du livre (EPUB). Le controle d'acces par classe
    s'applique ici aussi : un eleve ne peut pas telecharger le fichier d'un
    livre qui ne lui est pas destine.
    """

    def get(self, request, book_id):
        book = self.get_book_or_404(book_id)

        now = timezone.now()
        needs_new_token = (
            not book.download_token
            or not book.download_token_expires_at
            or book.download_token_expires_at - now < DOWNLOAD_TOKEN_MIN_VALIDITY
        )

        if needs_new_token:
            expires_at = now + DOWNLOAD_TOKEN_LIFETIME
            book.download_token = download_link_serializer.dumps(
                {"book": str(book.id), "exp": int(expires_at.timestamp())}
            )
            book.download_token_expires_at = expires_at
            book.save(update_fields=["download_token", "download_token_expires_at"])

        if not book.book_file:
            return Response(
                {"detail": "Fichier indisponible."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            handle = book.book_file.open("rb")
        except (OSError, ValueError):
            return Response(
                {"detail": "Fichier indisponible."}, status=status.HTTP_404_NOT_FOUND
            )

        return FileResponse(
            handle,
            content_type="application/epub+zip",
            as_attachment=False,
        )
