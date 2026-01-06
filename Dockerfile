FROM python:3.13.9-alpine3.22

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apk add --no-cache gcc musl-dev libffi-dev bash curl make

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Ne pas copier le code pour garder le volume Dokploy
# COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]