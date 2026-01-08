from django.shortcuts import render

# Create your views here.
from rest_framework import generics
from .models import *
from .serializers import *
from rest_framework.exceptions import NotFound
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from pathlib import Path
from uuid import UUID
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated



class BookListAPIView(generics.ListAPIView):
    """GET /api/books/"""
    serializer_class = BookSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # Staff ou superuser => tous les livres
        if user.is_staff or user.is_superuser:
            return Book.objects.filter(status='done').order_by('-created_at')
        print('User : ', user)
        students = Student.objects.filter(user__id=user.id)
        print(students)

        # Si utilisateur est étudiant
        if students :
            print('tu n est pas vide')
            student = students[0]
            student_class = student.school_class
            return Book.objects.filter(allowed_classes=user.student_profile.school_class, status='done').order_by('title')

        # Sinon aucun livre
        return Book.objects.none()


class BookDetailAPIView(generics.RetrieveAPIView):
    """GET /api/books/<id>/"""
    queryset = Book.objects.all()
    serializer_class = BookSerializer
    lookup_field = 'id'


class BookPageListAPIView(generics.ListAPIView):
    """GET /api/bookpages/"""
    queryset = BookPage.objects.all().order_by('order')
    serializer_class = BookPageSerializer


class BookPageDetailAPIView(generics.RetrieveAPIView):
    """GET /api/bookpages/<uuid:id>/"""
    queryset = BookPage.objects.all()
    serializer_class = BookPageSerializer
    lookup_field = 'id'


class BookPagesByBookAPIView(generics.ListAPIView):
    """GET /api/books/<uuid:book_id>/pages/"""
    serializer_class = BookPageSerializer

    def get_queryset(self):
        book_id = self.kwargs['book_id']
        return BookPage.objects.filter(book_id=book_id).order_by('order')
BASE_DIR = Path("books_content")  # dossier racine des livres

class BookPageByBookAndOrderAPIView(APIView):

    def get(self, request, book_id, order):
        # Vérifie que book_id est un UUID valide
        try:
            book_uuid = UUID(str(book_id))
        except ValueError:
            return Response({"detail": "Book ID invalide."}, status=status.HTTP_400_BAD_REQUEST)

        book = Book.objects.filter(id=book_id).first()
        # Construire le chemin vers le fichier
        book_dir = BASE_DIR / str(book_uuid)
        file_name = f"content_{order:02}.txt"
        file_path = book_dir / file_name

        if not file_path.exists():
            return Response({"detail": "Page non trouvée.", "file_path": file_path}, status=status.HTTP_404_NOT_FOUND)

        # Lire le contenu du fichier
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return Response({"detail": f"Erreur lecture fichier: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"id": f'${book_id}{order}', "title":book.title, "book": book_id,  "order": order, "content": content})