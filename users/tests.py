"""Tests d'authentification : login, profil, deconnexion et revocation."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()


class AuthenticationFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "unMotDePasseSolide123"
        self.user = User.objects.create_user(
            username="eleve",
            email="eleve@test.cd",
            password=self.password,
            full_name="Eleve Test",
        )

    def login(self):
        response = self.client.post(
            reverse("token_obtain_pair"),
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_login_with_email_returns_tokens(self):
        tokens = self.login()
        self.assertIn("access", tokens)
        self.assertIn("refresh", tokens)

    def test_login_with_wrong_password_is_rejected(self):
        response = self.client.post(
            reverse("token_obtain_pair"),
            {"email": self.user.email, "password": "mauvais"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_profile_requires_authentication(self):
        self.assertEqual(self.client.get(reverse("user-profile")).status_code, 401)

    def test_profile_returns_current_user(self):
        tokens = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        body = self.client.get(reverse("user-profile")).json()
        self.assertEqual(body["email"], "eleve@test.cd")
        self.assertEqual(body["full_name"], "Eleve Test")

    def test_refresh_returns_new_access_token(self):
        tokens = self.login()
        response = self.client.post(
            reverse("token_refresh"), {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())

    def test_logout_blacklists_refresh_token(self):
        """Apres deconnexion, le refresh token ne doit plus etre utilisable."""
        tokens = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        response = self.client.post(
            reverse("logout"), {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, 205)

        refreshed = self.client.post(
            reverse("token_refresh"), {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(refreshed.status_code, 401)

    def test_logout_without_refresh_is_a_bad_request(self):
        tokens = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.client.post(reverse("logout"), {}, format="json").status_code, 400)

    def test_register_creates_user_with_hashed_password(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "nouveau@test.cd",
                "username": "nouveau",
                "full_name": "Nouvel Eleve",
                "password": "unAutreMotDePasse123",
                "password2": "unAutreMotDePasse123",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        created = User.objects.get(email="nouveau@test.cd")
        self.assertNotEqual(created.password, "unAutreMotDePasse123")
        self.assertTrue(created.check_password("unAutreMotDePasse123"))

    def test_register_rejects_mismatched_passwords(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "autre@test.cd",
                "username": "autre",
                "password": "unMotDePasse123",
                "password2": "different123",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
