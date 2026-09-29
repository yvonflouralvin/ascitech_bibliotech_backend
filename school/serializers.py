from django.conf import settings
from rest_framework import serializers

from .models import Book, BookPage, Category


class CategorySerializer(serializers.ModelSerializer):
    """Domaine thematique, imbrique dans la fiche d'un livre.

    Le client filtre le catalogue sur le `slug` : il reste stable meme si le
    libelle est retouche dans l'administration.
    """

    class Meta:
        model = Category
        # `order` est expose pour que le client puisse presenter les filtres
        # dans l'ordre voulu par l'administration, et non par ordre
        # alphabetique : les categories arrivent eclatees livre par livre.
        fields = ['id', 'name', 'slug', 'order']
        read_only_fields = fields


class BookSerializer(serializers.ModelSerializer):
    """Metadonnees d'un livre exposees au client.

    Les champs sont enumeres explicitement : `allowed_classes` porte la regle
    d'acces et n'a pas a etre diffuse aux eleves.
    """

    book_file_path = serializers.SerializerMethodField()

    # Imbriquees plutot que referencees par identifiant : le catalogue est mis
    # en cache hors ligne cote client, qui doit pouvoir afficher et filtrer les
    # categories sans second appel reseau.
    categories = CategorySerializer(many=True, read_only=True)

    class Meta:
        model = Book
        fields = [
            'id',
            'title',
            'author',
            'description',
            'slug',
            'publish_state',
            'publication_date',
            'page',
            'book_format',
            'book_file_path',
            'categories',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_book_file_path(self, obj):
        """URL publique du fichier source du livre, ou None s'il n'y en a pas.

        Utilisee par le lecteur EPUB, qui charge le fichier directement au lieu
        de parcourir des images de pages. Les fichiers sont servis par le
        frontend depuis `public/books/`, d'ou une base configurable
        (`BOOKS_PUBLIC_BASE_URL`) plutot qu'un domaine code en dur.
        """
        if not obj.book_file:
            return None

        base_url = settings.BOOKS_PUBLIC_BASE_URL
        if not base_url.endswith("/"):
            base_url = f"{base_url}/"
        return f"{base_url}{obj.book_file.name.lstrip('/')}"


class BookPageSerializer(serializers.ModelSerializer):
    book = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = BookPage
        fields = ['id', 'title', 'content', 'order', 'book', 'created_at', 'updated_at']
        read_only_fields = fields
