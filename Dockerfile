# --- Base image ---
FROM python:3.13.9-alpine3.22

# --- Variables d'environnement ---
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# --- Dépendances système ---
RUN apk update && apk add --no-cache gcc musl-dev libffi-dev make curl bash

# --- Working directory ---
WORKDIR /app

# --- Copier requirements ---
#COPY requirements.txt /app/

# --- Installer python packages ---
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install whitenoise

# --- Copier le code Django ---
#COPY . /app/

# --- Collect statics ---
RUN python manage.py collectstatic --noinput

# --- Exposer le port Django ---
EXPOSE 8000

# --- Commande par défaut ---
CMD ["gunicorn", "backend.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
