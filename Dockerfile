FROM python:3.12-slim

# Instalar dependencias del sistema incluyendo Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    && curl -fsSL https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    fonts-freefont-ttf \
    fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Instalar dependencias para GDAL y PostgreSQL
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