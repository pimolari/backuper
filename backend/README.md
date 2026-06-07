# Backuper API - Backend FastAPI

Este es el backend de la aplicación **Backuper**, desarrollado con **FastAPI**. Ofrece una API para el registro e inicio de sesión de usuarios, creación de buckets en GCS, sincronización de metadatos de archivos mediante Datastore, y subida, descarga y eliminación de archivos y carpetas.

## Características Técnicas

* **Framework**: FastAPI (con Uvicorn como servidor ASGI).
* **Base de Datos**: Google Cloud Datastore (o emulador local basado en JSON).
* **Almacenamiento**: Google Cloud Storage (o almacenamiento simulado localmente).
* **Seguridad**: Autenticación JWT y hashing de contraseñas con bcrypt (aislamiento multi-inquilino estricto).
* **Dockerizado**: Preparado para desplegarse de manera nativa en Google Cloud Run.

---

## Configuración del Entorno Local

El backend puede operar en modo **emulación local** (predeterminado) o utilizando recursos reales de GCP mediante la variable de entorno `USE_REAL_GCP`.

### Variables de Entorno

* `USE_REAL_GCP`: Si es `true`, la API buscará credenciales y servicios reales de GCP en lugar de usar almacenamiento local simulado. Por defecto es `false`.
* `JWT_SECRET`: Llave secreta para firmar los tokens JWT.

### Ejecución Local Directa

1. Asegúrese de tener Python `>= 3.9` instalado.
2. Cree un entorno virtual e instale las dependencias:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Ejecute el servidor:
   ```bash
   python -m uvicorn backend.app:app --port 8000 --reload
   ```

### Ejecución Local con Docker

1. Construir la imagen:
   ```bash
   docker build -t backuper-backend .
   ```
2. Ejecutar el contenedor:
   ```bash
   docker run -p 8000:8080 -e USE_REAL_GCP=false backuper-backend
   ```

---

## Rutas Clave de la API

| Método | Ruta | Descripción | Requiere Auth |
| :--- | :--- | :--- | :---: |
| **POST** | `/api/auth/register` | Registra un usuario y genera su bucket GCS activo inicial. | No |
| **POST** | `/api/auth/login` | Inicia sesión y devuelve un token JWT. | No |
| **GET** | `/api/profile` | Devuelve los detalles del perfil del usuario y sus buckets. | Sí |
| **POST** | `/api/profile/bucket` | Crea y asocia un nuevo bucket de GCS al perfil. | Sí |
| **POST** | `/api/profile/active-bucket` | Cambia el bucket activo del espacio de trabajo. | Sí |
| **GET** | `/api/files/browse` | Lista directorios y archivos dentro de una ruta. | Sí |
| **GET** | `/api/files/tree` | Obtiene la estructura recursiva completa de carpetas del usuario. | Sí |
| **POST** | `/api/files/upload` | Sube un archivo a GCS y lo registra en el caché. | Sí |
| **GET** | `/api/files/download/{id}` | Descarga el archivo seleccionado desde GCS. | Sí |
| **DELETE** | `/api/files/{id}` | Elimina permanentemente el archivo en GCS y Datastore. | Sí |
| **DELETE** | `/api/files/folder/{path}` | Elimina recursivamente una carpeta y todos sus contenidos en GCS y caché. | Sí |
| **POST** | `/api/files/create-folder` | Registra una carpeta vacía en el caché del usuario. | Sí |
| **POST** | `/api/files/sync` | Fuerza la sincronización del caché leyendo los objetos reales de GCS. | Sí |

---

## Pruebas de Integración

Se dispone del script `verify_backuper.py` en la raíz del proyecto para ejecutar pruebas automatizadas completas contra el backend (corriendo un servidor local de FastAPI temporal).

Para ejecutar los tests:
```bash
python3 verify_backuper.py
```

Las pruebas cubren:
1. Registro de usuario.
2. Login y obtención del JWT.
3. Creación de directorios virtuales.
4. Subida de archivos a subdirectorios.
5. Listado de contenidos e integridad de caché.
6. Aislamiento de seguridad multi-inquilino (Bob no puede acceder a los datos de Alice).
7. Eliminación de archivos individuales.
8. Eliminación recursiva de carpetas y limpieza del árbol de directorios.
