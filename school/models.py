from django.db import models
from django.contrib.auth import get_user_model
import uuid
import os
from django.utils.text import slugify

User = get_user_model()

def book_file_upload_path(instance, filename):
    """
    Renomme le fichier avec l'ID du livre (UUID)
    ex: books/<uuid>.pdf
    """
    ext = os.path.splitext(filename)[1]  # .pdf, .epub, etc.
    return f'books/{instance.id}{ext}'

class Class(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    school_class = models.ForeignKey(Class, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    full_name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.full_name} ({self.user.email})"


class Book(models.Model):
    PUBLISH_STATE_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]

    BOOK_FORMAT_CHOICES = [
        ('pdf', 'PDF'),
        ('epub', 'EPUB'),
        ('audiobook', 'Audiobook'),
        ('paper', 'Paper'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('error', 'Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=500, null=False, blank=False)
    author = models.CharField(max_length=500, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    slug = models.SlugField(max_length=500, unique=True)
    publish_state = models.CharField(max_length=10, choices=PUBLISH_STATE_CHOICES, null=False, blank=False)
    publication_date = models.DateField(blank=True, null=True)
    
    # ✅ Valeur par défaut si non fourni
    page = models.PositiveIntegerField(default=0)

    book_format = models.CharField(max_length=10, choices=BOOK_FORMAT_CHOICES, null=False, blank=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ✅ Nouveau champ fichier
    book_file = models.FileField(
        upload_to=book_file_upload_path,
        blank=True,
        null=True
    )

    # ✅ Nouveau champ pour stocker les erreurs de traitement (Markdown)
    processing_error = models.TextField(
        blank=True,
        null=True,
        help_text="Erreur de traitement (format Markdown)"
    )

    # Nouvelle relation Many-to-Many pour les classes
    allowed_classes = models.ManyToManyField('Class', blank=True, related_name='accessible_books')

    # ✅ Nouveau champ status
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )


    class Meta:
        verbose_name = 'Book'
        verbose_name_plural = 'Books'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # ✅ Générer le slug automatiquement si absent
        if not self.slug and self.title:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Book.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        if self.pk:
            try:
                old = Book.objects.get(pk=self.pk)
                if old.book_file and old.book_file != self.book_file:
                    if os.path.isfile(old.book_file.path):
                        os.remove(old.book_file.path)
            except Book.DoesNotExist:
                pass

        super().save(*args, **kwargs)

class BookPage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.TextField(null=False, blank=False)
    content = models.TextField(null=False, blank=False)
    order = models.PositiveIntegerField(null=False, blank=False)
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name='pages',
        db_column='book_id'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta: 
        verbose_name = 'Book Page'
        verbose_name_plural = 'Book Pages'
        ordering = ['order']

    def __str__(self):
        return f"{self.title} (Page {self.order})"