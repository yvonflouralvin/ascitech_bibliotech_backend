# --- Base image ---
FROM python:3.12-slim

# --- Env ---
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# --- Dépendances système ---
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# --- Working dir ---
WORKDIR /app

# --- Requirements ---
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# --- Code ---
COPY . .

# --- Port ---
EXPOSE 8000

RUN  python manage.py migrate

# --- Start command ---
CMD sh -c "python manage.py collectstatic --noinput && \
           gunicorn backend.wsgi:application \
           --bind 0.0.0.0:8000 \
           --workers 3"

#CMD sh -c "python manage.py runserver 0.0.0.0:8000"
