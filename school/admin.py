from django.contrib import admin
#from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Class, Student, Book
from django import forms
from django.db.models import Q

User = get_user_model()  # ✅ Récupère ton modèle user personnalisé

# --- Inline pour Student dans User ---
class StudentInline(admin.StackedInline):
    model = Student
    can_delete = False
    verbose_name_plural = 'Student Profile'

# --- Custom User Admin pour gérer l'élève directement ---
class UserAdmin(BaseUserAdmin):
    inlines = (StudentInline,)
    list_display = ('email', 'username', 'is_staff', 'is_active')

# --- Admin pour Class ---
@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

# --- Admin pour Book ---
@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'description')
    search_fields = ('title','description')

# --- Admin pour Student ---
class StudentAdminForm(forms.ModelForm):
    password = forms.CharField(label='Password', widget=forms.PasswordInput, required=True)
    username = forms.CharField(required=True, help_text="Nom d'utilisateur du compte élève")
    email = forms.EmailField(required=False)

    class Meta:
        model = Student
        fields = ['full_name', 'school_class', 'password', 'email']

    def save(self, commit=True):
        
        # ✅ On récupère les données du formulaire
        username = self.cleaned_data.get('username')
        email = self.cleaned_data.get('email')
        password = self.cleaned_data.get('password')
        full_name = self.cleaned_data.get('full_name')
        
        user = User.objects.filter(username=username)
        if len(user) ==  0 :
        # ✅ Crée l'utilisateur automatiquement
            user = User.objects.create(username=username, email=email, password=password, full_name=full_name)
        else:
            user = user[0]

        if self.cleaned_data['password']:
            user.set_password(self.cleaned_data['password'])
            user.save()

        student = super().save(commit=False)
        student.user = user

        if commit:
            student.save()
        return student

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    form = StudentAdminForm
    list_display = ('full_name', 'user', 'school_class')
    list_filter = ('school_class',)
    search_fields = ('full_name', 'user__email', 'user__username')
