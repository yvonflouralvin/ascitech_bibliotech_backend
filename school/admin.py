from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model

from .models import Book, BookPage, Class, Student

User = get_user_model()


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'student_count')
    search_fields = ('name',)

    @admin.display(description="Eleves")
    def student_count(self, obj):
        return obj.students.count()


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'book_format', 'page', 'publish_state', 'created_at')
    list_filter = ('publish_state', 'book_format', 'allowed_classes')
    search_fields = ('title', 'author', 'description')
    filter_horizontal = ('allowed_classes',)
    readonly_fields = ('created_at', 'updated_at')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(BookPage)
class BookPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'book', 'order')
    list_filter = ('book',)
    search_fields = ('title',)


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
