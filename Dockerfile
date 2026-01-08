# Image de base
FROM python:3.13.9-alpine3.22

# Définir le répertoire de travail
WORKDIR /app

# Variables d'environnement pour Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Installer les dépendances système nécessaires
RUN apk add --no-cache gcc musl-dev libffi-dev bash curl make

# Copier requirements et installer les dépendances Python
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copier tout le code source
COPY . .

# Créer le dossier static pour éviter les warnings
RUN mkdir -p /app/static

# Exposer le port Django
EXPOSE 8000

# Lancer migrations et serveur au démarrage du conteneur
CMD ["sh", "-c", "python manage.py migrate && python manage.py runserver 0.0.0.0:8000"]