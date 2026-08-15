from django.urls import path

from .views import (
    BookAvailabilityAPIView,
    BookCoverAPIView,
    BookDetailAPIView,
    BookDownloadView,
    BookListAPIView,
    BookPageByBookAndOrderAPIView,
    BookPagesByBookAPIView,
)

urlpatterns = [
    path('books/', BookListAPIView.as_view(), name='book-list'),
    path('books/<uuid:id>/', BookDetailAPIView.as_view(), name='book-detail'),

    # Couverture et disponibilite du contenu
    path('books/<uuid:book_id>/cover/', BookCoverAPIView.as_view(), name='book-cover'),
    path(
        'books/<uuid:book_id>/availability/',
        BookAvailabilityAPIView.as_view(),
        name='book-availability',
    ),

    # Pages d'un livre
    path('books/<uuid:book_id>/pages/', BookPagesByBookAPIView.as_view(), name='book-pages-by-book'),
    path(
        'books/<uuid:book_id>/page/<int:order>/',
        BookPageByBookAndOrderAPIView.as_view(),
        name='book-page-by-book-and-order',
    ),

    # Fichier source du livre (EPUB)
    path('books/<uuid:book_id>/download/', BookDownloadView.as_view(), name='book-download'),
]
