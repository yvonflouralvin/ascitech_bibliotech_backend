FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System deps
RUN apt-get update && apt-get install -y gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# App code
COPY . .

# Création dossier staticfiles
RUN mkdir -p /app/staticfiles

EXPOSE 8000

# Start
CMD ["sh", "-c", "python manage.py collectstatic --noinput && gunicorn backend.wsgi:application --bind 0.0.0.0:8000 --workers 3"]