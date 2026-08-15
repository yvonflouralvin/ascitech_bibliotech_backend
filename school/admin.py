from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils.html import format_html

from .models import Book, BookPage, Class, Student

User = get_user_model()


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'student_count')
    search_fields = ('name',)

    @admin.display(description="Eleves")
    def student_count(self, obj):
        return obj.students.count()


@admin.register(BookPage)
class BookPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'book', 'order')
    list_filter = ('book',)
    search_fields = ('title',)


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
     # ✅ Colonnes affichées dans la liste
    list_display = ('title', 'status_colored', 'cover_source', 'display_allowed_classes')
    list_filter = ('book_format', 'status')
    search_fields = ('title', 'description')

    readonly_fields = (
        'slug',
        'page',
        'status',
        'processing_error',
        'created_at',
        'updated_at',
    )

     # allowed_classes reste modifiable
    filter_horizontal = ('allowed_classes',)  # pratique pour ManyToManyField

    fieldsets = (
        ('Informations générales', {
            'fields': ('title', 'author', 'description', 'book_format', 'book_file')
        }),
        ('Publication', {
            'fields': ('publish_state', 'publication_date')
        }),
        ('Statut de traitement', {
            'fields': ('status', 'processing_error')
        }),
        ('Classes autorisées', {
            'fields': ('allowed_classes',)  # ✅ Ici l'admin peut ajouter ou retirer des classes
        }),
        ('Couverture', {
            'fields': ('cover_page',),
            'description': (
                "Numéro de la page utilisée comme couverture dans le catalogue. "
                "Mettre <strong>0</strong> pour afficher une couverture générée "
                "automatiquement (dégradé, titre et auteur) — c’est la valeur "
                "par défaut des livres au format EPUB, dont les premières pages "
                "converties sont blanches."
            ),
        }),
        ('Métadonnées (auto)', {
            'fields': ('slug', 'page', 'created_at', 'updated_at')
        }),
    )

    @admin.display(description="Couverture")
    def cover_source(self, obj):
        if obj.cover_page == 0:
            return "générée"
        return f"page {obj.cover_page}"

    # ✅ Affichage coloré et lisible du status
    def status_colored(self, obj):
        color_map = {
            'pending': 'gray',
            'processing': 'blue',
            'done': 'green',
            'error': 'red',
        }
        return format_html(
            '<span style="color:{}; font-weight:bold;">{}</span>',
            color_map.get(obj.status, 'black'),
            obj.get_status_display()
        )

    status_colored.short_description = "Statut"

    # ✅ Afficher les classes associées dans la liste
    def display_allowed_classes(self, obj):
        return ", ".join([c.name for c in obj.allowed_classes.all()])

    display_allowed_classes.short_description = "Classes autorisées"


class StudentAdminForm(forms.ModelForm):
    """Creation d'un eleve et de son compte utilisateur en un seul formulaire.

    A la creation, le mot de passe est obligatoire. En modification il reste
    facultatif : le laisser vide conserve le mot de passe existant.
    """

    username = forms.CharField(
        required=True,
        help_text="Nom d'utilisateur du compte eleve.",
    )
    email = forms.EmailField(
        required=True,
        help_text="Sert d'identifiant de connexion.",
    )
    password = forms.CharField(
        label='Mot de passe',
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Laisser vide pour conserver le mot de passe actuel.",
    )

    class Meta:
        model = Student
        fields = ['full_name', 'school_class']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = getattr(self.instance, 'user', None)
        if user is not None and user.pk:
            self.fields['username'].initial = user.username
            self.fields['email'].initial = user.email
        else:
            # Creation : le mot de passe devient obligatoire.
            self.fields['password'].required = True
            self.fields['password'].help_text = "Mot de passe initial du compte eleve."

    def _existing_user(self):
        user = getattr(self.instance, 'user', None)
        return user if user is not None and user.pk else None

    def clean_email(self):
        email = self.cleaned_data['email']
        taken = User.objects.filter(email__iexact=email)
        current = self._existing_user()
        if current is not None:
            taken = taken.exclude(pk=current.pk)
        if taken.exists():
            raise forms.ValidationError("Cet email est deja utilise par un autre compte.")
        return email

    def clean_username(self):
        username = self.cleaned_data['username']
        taken = User.objects.filter(username__iexact=username)
        current = self._existing_user()
        if current is not None:
            taken = taken.exclude(pk=current.pk)
        if taken.exists():
            raise forms.ValidationError("Ce nom d'utilisateur est deja pris.")
        return username

    def save(self, commit=True):
        username = self.cleaned_data['username']
        email = self.cleaned_data['email']
        password = self.cleaned_data.get('password')
        full_name = self.cleaned_data.get('full_name')

        user = self._existing_user()
        if user is None:
            # create_user hache le mot de passe ; ne jamais passer par
            # User.objects.create() qui l'enregistrerait en clair.
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                full_name=full_name,
            )
        else:
            user.username = username
            user.email = email
            user.full_name = full_name
            if password:
                user.set_password(password)
            user.save()

        student = super().save(commit=False)
        student.user = user
        if commit:
            student.save()
            self.save_m2m()
        return student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    form = StudentAdminForm
    list_display = ('full_name', 'user', 'school_class')
    list_filter = ('school_class',)
    search_fields = ('full_name', 'user__email', 'user__username')
