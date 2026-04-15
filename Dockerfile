FROM python:3.11-slim

# System libs needed by Pillow (JPEG, PNG, FreeType fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev libpng-dev libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
