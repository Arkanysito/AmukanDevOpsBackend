# Setup del Proyecto

## Requisitos
- Tener instalado: [Docker Desktop](https://www.docker.com/products/docker-desktop)
- Clonar este repositorio

---

## ¿Qué incluye este entorno?
- Python 3.13
- Django con GDAL
- Base de datos PostgreSQL + PostGIS
- Volumen persistente para guardar datos de la BD

---

## ¿Cómo levantar el entorno?

1. Crea un archivo `.env` en la raíz del proyecto (donde se encuentra este README.md) con las credenciales del proyecto (Si no sabes cuales son, las puedes pedir) esto es para no dejar ninguna clave pública.
2. Levanta la aplicación y reconstruye las imágenes (incluso si ya existen).
```bash
docker-compose up --build
```

### Notas:
- No es necesario utilizar build cada vez que quieras levantar el proyecto, ya que es útil cuando haces cambios en Dockerfile o en las dependencias.
- Para reconstruir puedes utilizar: 
```bash
docker-compose build
```
- Esto solo reconstruye las imágenes de los servicios definidos, sin iniciarlos. Sirve para preparar el entorno antes de levantarlo.

- Para levantar la aplicación con los contenedores ya construidos:
```bash
docker-compose up
```
- Recuerda esperar a que en la terminal te salga 

```
web-1  | Watching for file changes with StatReloader 
```
- Con eso ya puedes ir a [http://localhost:8000](http://localhost:8000)

## ¿Y Django?

- Si vas a /apps/users/migrations/ no te sale un archivo 0001_initial.py o cualquier otro numero al inicio, es porque no se ha hecho ninguna migración, por lo que debes ejecutar:

```bash
docker-compose exec web python manage.py makemigrations
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

- Si encuentras un archivo como 0001_initial.py, solo debes ejecutar:
```bash
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

- Con esto ya puedes entrar a [http://localhost:8000/admin](http://localhost:8000/admin) con tus credenciales

## ¿Cómo probar que todo funciona?

1. Ve a [http://localhost:8000](http://localhost:8000)
2. Inicia sesión con tu superusuario
3. Crea un objeto en el admin para verificar la conexión con la base de datos

## Extra
Usa `docker-compose down -v` si quieres limpiar la base de datos, pero recuerda eliminar los 0001_initial.py


## ⚠️ Licencia y uso

Este repositorio es **privado** y su contenido está protegido por derechos de autor.  
No se autoriza la copia, distribución ni modificación del código fuente ni de los documentos aquí contenidos, salvo consentimiento explícito del equipo.

© 2025 - Todos los derechos reservados.
