FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

COPY requirements.txt .

# Instalar pip y numpy PRIMERO para evitar conflictos
RUN pip install --upgrade pip
RUN pip install numpy==1.26.4

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["sh", "-c", "sleep 10 && python manage.py runserver 0.0.0.0:8000"]