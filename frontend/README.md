# Backuper Web App - Frontend Flask

Este es el frontend de **Backuper**, una aplicación web interactiva que ofrece una interfaz gráfica moderna, fluida y con diseño de alta calidad (*glassmorphism*, animaciones sutiles y combinaciones de colores premium) para interactuar con los servicios de almacenamiento en la nube de Google Cloud Storage (GCS).

## Características Técnicas

* **Servidor**: Flask (utilizado principalmente para servir plantillas HTML y actuar como proxy inverso API).
* **Diseño y Estilos**: CSS Vanilla altamente personalizado, optimizado para ser responsivo y ofrecer una excelente experiencia visual.
* **Interactividad**: Vanilla JavaScript con controladores de estado dinámicos, carga mediante arrastrar y soltar (Drag and Drop), vistas conmutables en formato de lista y cuadrícula, y árbol jerárquico de carpetas en tiempo real.
* **Seguridad**: Autenticación persistente localmente mediante JWT almacenados en `localStorage`.

---

## Configuración y Proxy Inverso

El frontend opera como un **proxy inverso**. Todas las solicitudes dirigidas a `/api/*` se reenvían al Backend FastAPI configurado en la dirección de la variable de entorno `BACKEND_URL`. 

Esto elimina la necesidad de configurar políticas complejas de CORS (Cross-Origin Resource Sharing) en producción y unifica el origen de cara al cliente web.

---

## Configuración y Ejecución Local

### Ejecución Directa

1. Asegúrese de tener Python instalado.
2. Cree su entorno virtual e instale dependencias:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Defina la dirección del backend (si es diferente de `http://localhost:8000`) y ejecute:
   ```bash
   export BACKEND_URL="http://localhost:8000"
   python app.py
   ```
4. Abra su navegador en [http://localhost:5000](http://localhost:5000).

### Ejecución con Docker

1. Construir la imagen de contenedor:
   ```bash
   docker build -t backuper-frontend .
   ```
2. Iniciar el contenedor (enlazándolo con el backend que corre en su host):
   ```bash
   docker run -p 5000:8080 -e BACKEND_URL="http://host.docker.internal:8000" backuper-frontend
   ```

---

## Estructura del Código Frontend

* **`app.py`**: Servidor Flask que define las rutas para servir el HTML e implementa el reenvío dinámico de cabeceras, parámetros y streaming de descargas/subidas hacia el backend FastAPI.
* **`templates/`**:
  * `index.html`: Panel principal del espacio de trabajo del usuario (gestor de archivos, subidas, árbol de navegación y modal de perfil/buckets).
  * `login.html`: Pantalla de bienvenida, inicio de sesión y formulario de registro interactivo con selección de región de GCS y clases de almacenamiento.
* **`static/css/style.css`**: Hoja de estilos que implementa el diseño estético de la aplicación (desenfocado de fondo, gradientes responsivos de color, contenedores flotantes, y tarjetas estilizadas).
* **`static/js/`**:
  * `auth.js`: Lógica de autenticación, manejo de cookies JWT, redirecciones y alertas flotantes para formularios de login/registro.
  * `app.js`: Script principal del espacio de trabajo que gestiona la carga y visualización de contenidos en lista/grid, navegación por rutas, descargas mediante blobs, creación y eliminación recursiva de carpetas y llamadas de sincronización.
