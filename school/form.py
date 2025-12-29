from django import forms
from .models import Student

class StudentForm(forms.ModelForm):
    # Champ pour saisir le mot de passe du futur compte
    password = forms.CharField(widget=forms.PasswordInput, required=True)
    username = forms.CharField(required=True, help_text="Nom d'utilisateur du compte élève")
    email = forms.EmailField(required=False)

    class Meta:
        model = Student
        fields = ['username', 'email', 'password', 'school_class']

    def save(self, commit=True):
        username = self.cleaned_data['username']
        email = self.cleaned_data['email']
        password = self.cleaned_data['password']

        # ✅ Crée l'utilisateur automatiquement
        user = User.objects.create_user(username=username, email=email, password=password)

        student = super().save(commit=False)
        student.user = user

        if commit:
            student.save()
        return student