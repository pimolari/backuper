# Backuper API - Backend FastAPI

Este es el backend de la aplicación **Backuper**, desarrollado con **FastAPI**. Ofrece una API para el registro e inicio de sesión de usuarios, creación de buckets en GCS, sincronización de metadatos de archivos mediante Datastore, y subida, descarga y eliminación de archivos y carpetas.

## Características Técnicas

* **Framework**: FastAPI (con Uvicorn como servidor ASGI).
* **Base de Datos**: Google Cloud Datastore (o emulador local basado en JSON).
* **Almacenamiento**: Google Cloud Storage (o almacenamiento simulado localmente).
* **Seguridad**: Autenticación JWT y hashing de contraseñas con bcrypt (aislamiento multi-inquilino estricto).
* **Dockerizado**: Preparado para desplegarse de manera nativa en Google Cloud Run.

---

## System Flows (Flujos del Sistema)

### 1. Authentication Flow (Flujo de Autenticación)
- **Registro (`/api/auth/register`)**: El sistema recibe el correo y contraseña. Primero valida los datos, y luego invoca al cliente GCS para crear un nuevo bucket nativo para el usuario. Tras crearse el bucket con éxito, persiste la entidad del usuario en Datastore con la contraseña cifrada y le asigna este bucket como su "bucket activo" inicial.
- **Login (`/api/auth/login`)**: El cliente envía sus credenciales, que se validan contra Datastore. Si coinciden, el backend firma y emite un token de acceso JWT con el correo del usuario como sujeto (`sub`), que se utilizará en los encabezados `Authorization: Bearer <token>` de futuras solicitudes.

### 2. Standard and Chunked File Upload Flow (Flujos de Subida de Archivos)
- **Subida Estándar (`/api/files/upload`)**: Recibe un archivo monolítico en un payload de formulario `multipart/form-data`, y lo transmite directamente a Google Cloud Storage de forma sincrónica. Finalmente, registra los metadatos en la entidad `FileCache` de Datastore.
- **Subida en Bloques (Chunked Upload)**: Diseñado para archivos grandes que superan los límites de tamaño del cuerpo de solicitud de Cloud Run (32MB).
  - **Fase 1 (`/api/files/upload/initiate`)**: Registra la intención de subir un archivo. El servidor GCS inicia una sesión resumible y el backend crea una entidad `UploadSession` en Datastore para mapearla. Si es una imagen, se procesa un thumbnail Base64.
  - **Fase 2 (`/api/files/upload/chunk`)**: El frontend envía bloques secuenciales del archivo usando la ID de sesión. El backend retransmite estos bloques (vía requests) al endpoint resumible de GCS.
  - **Fase 3 (`/api/files/upload/complete`)**: Se invoca cuando todos los bloques han sido transmitidos. El backend purga la sesión y asienta la entidad definitiva en `FileCache`.

### 3. Listing and Hierarchy Flow (Flujo de Listado y Caché Virtual)
- GCS es inherentemente un almacenamiento de objetos planos, sin carpetas reales. Para proveer una experiencia rápida y no bloquearnos listando repetitivamente objetos GCS remotos, el backend mantiene un caché de Datastore (`FileCache`) de todos los archivos y "directorios virtuales".
- **`browse_files`**: Al listar archivos en una ruta específica (e.g. `Documents/`), el backend consulta en Datastore todos los archivos bajo ese bucket. Mediante la comparación y el recorte de cadenas, infiere instantáneamente y sin costo remoto qué objetos existen directamente en esa subcarpeta y si hay carpetas lógicas implícitas dentro. Este método soporta además paginación (`limit`, `page`).

### 4. Deletion Flow (Flujo de Eliminación)
- **Archivos (`/api/files/{id}`)**: El backend primero constata que el usuario en sesión coincida con el dueño anotado en Datastore. Luego, elimina físicamente el blob de GCS e invalida el registro cacheado en Datastore.
- **Carpetas (`/api/files/folder/{path}`)**: GCS permite usar el cliente para buscar y eliminar recursivamente todos los objetos que tengan la ruta como prefijo. A su vez, el backend busca en Datastore toda entidad que comience con la misma ruta y destruye los registros en ráfaga, limpiando por completo el árbol asociado.

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
9. Subidas en bloques completas (Chunked Uploads).
10. Verificación de paginación y deduplicación.
