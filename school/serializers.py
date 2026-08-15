from django.conf import settings
from rest_framework import serializers

from .models import Book, BookPage


class BookSerializer(serializers.ModelSerializer):
    """Metadonnees d'un livre exposees au client.

    Les champs sont enumeres explicitement : `allowed_classes` porte la regle
    d'acces et n'a pas a etre diffuse aux eleves.
    """

    book_file_path = serializers.SerializerMethodField()

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
