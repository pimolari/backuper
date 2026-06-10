# Backuper Project

Backuper is a comprehensive, multi-tenant file backup and management system designed to run on Google Cloud Platform (GCP). It leverages FastAPI for the backend, Flask for the frontend, and is deployed entirely on Google Cloud Run utilizing Cloud Datastore for fast file metadata indexing and Cloud Storage for file persistence.

## Project Structure

The repository is divided into three core modules:

1. **`backend/`**: A high-performance REST API built with FastAPI. It handles user authentication, Google Cloud Storage operations (including resumable chunked uploads), Datastore caching, and virtual folder hierarchy generation.
2. **`frontend/`**: A lightweight web interface built with Flask and Vanilla JS. It serves the UI, manages client-side routing, processes image thumbnails locally using HTML5 `<canvas>`, and communicates securely with the backend API.
3. **`infra/`**: Infrastructure as Code (IaC) using Terraform and Bash automation scripts. It provisions GCP projects, Artifact Registries, Service Accounts, Datastore, and manages the deployment lifecycle of both applications to Cloud Run.

---

## 1. Local Development Execution

You can run the entire application locally using local mock emulators (so you don't need real GCP credentials).

### Backend Execution
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the backend server (runs on port `8000` by default):
   ```bash
   USE_REAL_GCP=false JWT_SECRET="your_local_secret" uvicorn backend.app:app --port 8000 --reload
   ```

### Frontend Execution
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the frontend server (runs on port `8080` by default). By default, it proxies API calls to `http://localhost:8000`.
   ```bash
   BACKEND_URL="http://localhost:8000" python -m flask run --port 8080 --reload
   ```

You can now visit `http://localhost:8080` in your browser.

---

## 2. Infrastructure Provisioning

Before deploying the application to Google Cloud, you must provision the underlying infrastructure (Projects, Datastore, IAM permissions, Artifact Registry).

1. Edit the parameters in `infra/variables.tfvars.json` to match your GCP organization and preferred region.
2. Navigate to the `infra` directory:
   ```bash
   cd infra
   ```
3. Make the script executable and run the infrastructure deployment:
   ```bash
   chmod +x deploy_infra.sh
   ./deploy_infra.sh
   ```
   *Note: This utilizes Terraform across two parts to bootstrap the state bucket and provision Datastore and IAM safely.*

---

## 3. Application Deployment

We provide Bash scripts to deploy the frontend and backend using **Google Cloud Build** and **Google Cloud Run**. These scripts ensure zero-downtime rollouts and assign the proper Service Accounts to the containers.

Navigate to the `infra/` directory before running any deployment scripts:
```bash
cd infra/
```

### Option A: Deploy the Entire Application
To compile and deploy both the Backend and Frontend sequentially, use the combined script. It automatically wires the Backend URL dynamically into the Frontend deployment:
```bash
chmod +x deploy_app.sh
./deploy_app.sh
```

### Option B: Deploy Modules Separately
If you only made changes to a specific module, you can deploy them individually to save time.

**Deploy the Backend:**
```bash
chmod +x deploy_backend.sh
./deploy_backend.sh
```

**Deploy the Frontend:**
*When deploying the frontend alone, make sure you know the Backend's Cloud Run URL so it can be passed as an environment variable to the frontend.*
```bash
chmod +x deploy_frontend.sh
./deploy_frontend.sh
```

---

## Testing

A comprehensive integration test suite is located at the root of the project. This suite spins up the backend locally and verifies the entire lifecycle of user registration, folder deduplication, multi-tenant security, chunked uploads, and pagination.

To run the integration tests:
```bash
python3 verify_backuper.py
```
