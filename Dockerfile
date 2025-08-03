# Imagen oficial de Python 3.13
FROM python:3.13-slim

# Instala GDAL y dependencias del sistema
RUN apt-get update && \
    apt-get install -y gdal-bin libgdal-dev binutils && \
    apt-get clean

# Variables necesarias para compilar los bindings
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# Crea directorio del proyecto
WORKDIR /app

# Copia e instala dependencias Python
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia el resto del código fuente
COPY . /app

# Exponer el puerto para Django
EXPOSE 8000

# Comando por defecto
CMD ["sh", "-c", "sleep 10 && python manage.py runserver 0.0.0.0:8000"]