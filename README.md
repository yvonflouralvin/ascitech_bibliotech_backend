## Les variables d'environnement qu'il faut avoir :

- LANGUAGE_CODE=fr-FR
- TIME_ZONE=UTC

## Base de données : Par default c'est SQLLite
- DB_ENGINE=django.db.backends.postgresql
- DB_NAME=postgres
- DB_USER=postgres
- DB_PASSWORD=postgres
- DB_HOST=postgres
- DB_PORT=5432

## Les cors header et les allowed origin
- ALLOWED_HOSTS=bibliotech.cd,dev.bibliotech.cd
- CSRF_TRUSTED_ORIGINS=bibliotech.cd,dev.bibliotech.cd
- CORS_ALLOWED_ORIGINS=bibliotech.cd,dev.bibliotech.cd