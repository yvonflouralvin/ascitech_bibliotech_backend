from rest_framework import serializers
from .models import Book, BookPage


from rest_framework import serializers
from .models import Book


class BookSerializer(serializers.ModelSerializer):
    # 🔹 Retourne le chemin ou l'URL du fichier s'il existe
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
        Retourne le chemin du fichier source si présent,
        sinon None
        """
        if obj.book_file:
            # 👉 chemin relatif sur le serveur
            #return obj.book_file.name

            # 👉 OU URL complète (décommente si tu préfères)
            request = self.context.get('request')
            return request.build_absolute_uri(obj.book_file.url) if request else obj.book_file.url

        return None


class BookPageSerializer(serializers.ModelSerializer):
    book = BookSerializer(read_only=True)

    class Meta:
        model = BookPage
        fields = '__all__'