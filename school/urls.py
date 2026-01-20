from django.urls import path
from .views import *

urlpatterns = [
    path('books/', BookListAPIView.as_view(), name='book-list'),
    path('books/<uuid:id>/', BookDetailAPIView.as_view(), name='book-detail'),

    # 📘 Pages d’un livre spécifique
    path('books/<uuid:book_id>/pages/', BookPagesByBookAPIView.as_view(), name='book-pages-by-book'),
    path('books/<uuid:book_id>/page/<int:order>/', BookPageByBookAndOrderAPIView.as_view(), name='book-page-by-book-and-order'),
    path("books/<uuid:book_id>/download/", BookDownloadView.as_view(), name="book-download" ),
]
