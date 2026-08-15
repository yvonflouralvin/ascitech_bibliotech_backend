from rest_framework import serializers

from .models import Book, BookPage


class BookSerializer(serializers.ModelSerializer):
    """Metadonnees d'un livre exposees au client.

    Les champs sont enumeres explicitement : `allowed_classes` porte la regle
    d'acces et n'a pas a etre diffuse aux eleves.
    """

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
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class BookPageSerializer(serializers.ModelSerializer):
    book = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = BookPage
        fields = ['id', 'title', 'content', 'order', 'book', 'created_at', 'updated_at']
        read_only_fields = fields
