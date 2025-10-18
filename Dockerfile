# Dockerfile.python
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# Copiar requirements primero
COPY requirements.txt .

# Instalar sin sentence-transformers primero
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
    Django==5.2.4 \
    psycopg2-binary==2.9.10 \
    djangorestframework==3.15.2 \
    django-cors-headers==4.4.0 \
    djangorestframework-simplejwt==5.3.1 \
    PyJWT==2.9.0 \
    geopandas==0.14.3 \
    shapely==2.0.4 \
    numpy==2.1.2 \
    beautifulsoup4==4.12.3 \
    gunicorn==22.0.0 \
    python-dotenv==1.0.1

# Instalar transformers y torch separadamente (más livianos)
RUN pip install --no-cache-dir transformers==4.37.2 torch==2.2.0 tokenizers==0.15.2

COPY . .

EXPOSE 8000
CMD ["sh", "-c", "sleep 10 && python manage.py runserver 0.0.0.0:8000"]