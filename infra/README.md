# Infraestructura y Despliegue de GCP

Este directorio contiene los scripts de Terraform y Bash necesarios para aprovisionar la infraestructura del proyecto en Google Cloud Platform (GCP) y desplegar los servicios **Backend** y **Frontend** en **Google Cloud Run**.

La infraestructura está estructurada de forma modular en dos fases o partes para permitir ejecuciones independientes y seguras.

## Estructura del Directorio

```text
infra/
├── variables.tfvars.json  # Archivo de variables JSON del entorno
├── common.sh              # (NEW) Script compartido que carga las configuraciones para evitar duplicados
├── deploy_infra.sh        # Automatiza la ejecución de Terraform (Partes 1 y 2)
├── deploy_app.sh          # Automatiza la compilación con Cloud Build y despliegue a Cloud Run (Frontend y Backend)
├── deploy_backend.sh      # Despliega únicamente el Backend
├── deploy_frontend.sh     # Despliega únicamente el Frontend
├── part1/                 # Creación del Proyecto y Bucket de Estado
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
└── part2/                 # Base de Datos Datastore, Permisos IAM y Service Account
    ├── backend.tf         # Configuración del Backend Remoto GCS
    ├── main.tf
    ├── variables.tf
    └── outputs.tf
```

---

## Requisitos Previos

Antes de ejecutar los scripts, asegúrese de contar con las siguientes herramientas en su entorno:

1. **Google Cloud SDK (gcloud)**: Instalado y autenticado con su cuenta.
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```
2. **Terraform** (versión `>= 1.0`): Instalado localmente para el aprovisionamiento.
3. **Python 3**: Utilizado para analizar los valores del archivo JSON de variables de forma nativa.

---

## Configuración de Parámetros

Edite el archivo [variables.tfvars.json](variables.tfvars.json) en la raíz de esta carpeta para definir los parámetros específicos de su organización y proyecto de GCP:

```json
{
  "project_name": "Nombre visible del proyecto",
  "project_id": "id-unico-del-proyecto-gcp",
  "org_id": "Id numérico de la organización (dejar en blanco "" si no tiene organización)",
  "billing_account": "XXXXXX-XXXXXX-XXXXXX (Cuenta de facturación de GCP)",
  "region": "europe-west1 (Región por defecto)",
  "admin_group_email": "grupo-administradores@dominio.com",
  "state_bucket_name": "nombre-unico-para-el-bucket-de-estado-tf"
}
```

---

## Despliegue en 2 Pasos

El despliegue está automatizado para ejecutarse en dos secuencias: aprovisionamiento de infraestructura y despliegue de las aplicaciones.

### Paso 1: Crear la Infraestructura GCP

Ejecute el script `deploy_infra.sh`. Este script realizará lo siguiente de forma automática:
1. Leer los parámetros de `variables.tfvars.json`.
2. Inicializar y aplicar localmente el módulo `part1/` para crear el proyecto GCP, habilitar los servicios/APIs requeridos y crear el bucket de almacenamiento de estado GCS.
3. Inicializar el módulo `part2/` enlazando dinámicamente su backend remoto de Terraform al bucket GCS de estado creado en el paso anterior.
4. Aplicar el módulo `part2/` para generar las políticas IAM de administración para el grupo Google, activar la base de datos Datastore y crear la Cuenta de Servicio de Cloud Run con permisos de escritura de caché y almacenamiento de buckets.

```bash
chmod +x deploy_infra.sh
./deploy_infra.sh
```

### Paso 2: Desplegar los Servicios en Cloud Run

Una vez que la infraestructura esté aprovisionada, ejecute `deploy_app.sh`. Este script automatiza el ciclo de vida del despliegue continuo:
1. Enlazar `gcloud` al nuevo proyecto creado.
2. Crear un repositorio Docker en **Google Artifact Registry** para almacenar las imágenes de contenedor de manera privada y segura.
3. Enviar el código de `backend/` y `frontend/` a **Google Cloud Build** para compilar las imágenes Docker sin necesidad de tener un daemon Docker local (ideal para compilaciones ligeras).
4. Desplegar el **Backend FastAPI** en Cloud Run asignándole la Cuenta de Servicio del proyecto y activando la variable `USE_REAL_GCP=true`.
5. Obtener dinámicamente el endpoint seguro `HTTPS` asignado al backend.
6. Desplegar el **Frontend Flask** asociándole el endpoint del backend para proxying de llamadas.

```bash
chmod +x deploy_app.sh
./deploy_app.sh
```

---

## Detalle de Recursos Creados

* **Proyecto GCP**: Aislado y etiquetado con la cuenta de facturación suministrada.
* **APIs Habilitadas**: Cloud Run, Cloud Storage, Cloud Datastore (Firestore en modo Datastore), Resource Manager, Identity & Access Management (IAM), Service Usage, Artifact Registry y Cloud Build.
* **Estado de Terraform Remoto**: Bucket GCS seguro con control de versiones activo para mitigar riesgos en actualizaciones de Terraform.
* **Rol IAM Administrador**: Enlace de permisos de propietario `roles/owner` directo al grupo de Google administradores.
* **Base de Datos Datastore**: Base de datos `(default)` en la misma región elegida.
* **Cuenta de Servicio Dedicada**: `backuper-cloud-run-sa` con el rol de `roles/datastore.owner` (para almacenar caché de archivos de usuarios) y `roles/storage.admin` (para crear buckets de GCS según las peticiones de los usuarios registrados).
