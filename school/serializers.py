from rest_framework import serializers
from .models import Book, BookPage


from rest_framework import serializers
from .models import Book

class BookSerializer(serializers.ModelSerializer):
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
            'created_at',
            'updated_at',
            'book_file',
            'book_file_path',
            'processing_error',
            'allowed_classes',
            'status',
        ]

        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'processing_error',
            'status',
        ]

    def get_book_file_path(self, obj):
        """
        Retourne une URL publique normalisée :
        https://bibliotech.cd/public/books/nom_du_fichier
        """
        if not obj.book_file:
            return None

        base_url = "https://bibliotech.cd/public/"
        return f"{base_url}{obj.book_file.name}"


class BookPageSerializer(serializers.ModelSerializer):
    book = BookSerializer(read_only=True)

    class Meta:
        model = BookPage
        fields = '__all__'