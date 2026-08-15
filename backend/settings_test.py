"""Settings utilises pour la suite de tests.

Reprend la configuration reelle mais bascule sur SQLite en memoire, afin que
`manage.py test` tourne sans instance PostgreSQL disponible.

    python manage.py test --settings=backend.settings_test
"""

import os

os.environ.setdefault("DEBUG", "True")

from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Hachage rapide : les tests creent beaucoup d'utilisateurs.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Pas de redirection HTTPS ni de cookies secure pendant les tests.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
