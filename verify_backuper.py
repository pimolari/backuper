import os
import sys
import time
import subprocess
import requests
import json
import shutil

def clean_local_storage():
    """Reset the mock database and local mock GCS storage."""
    print("Resetting local mock storage and database...")
    db_file = "backend/mock_datastore.json"
    gcs_dir = "backend/mock_gcs"
    if os.path.exists(db_file):
        os.remove(db_file)
    if os.path.exists(gcs_dir):
        shutil.rmtree(gcs_dir)
    os.makedirs(gcs_dir, exist_ok=True)

def run_integration_tests():
    # 1. Clear database & storage first
    clean_local_storage()

    # 2. Start Backend FastAPI Server
    print("Launching FastAPI backend server...")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app:app", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for server to boot
    time.sleep(3)
    
    base_url = "http://localhost:8000/api"
    success = True
    
    try:
        # ---- TEST 1: User Registration ----
        print("\n--- Test 1: User Registration ---")
        reg_payload = {
            "name": "Alice Developer",
            "email": "alice@example.com",
            "password": "alicepassword123",
            "default_region": "europe-west1",
            "default_storage_class": "NEARLINE"
        }
        res = requests.post(f"{base_url}/auth/register", json=reg_payload)
        print("Register Status Code:", res.status_code)
        assert res.status_code == 200, "Registration failed"
        reg_data = res.json()
        print("Registration Response:")
        print(json.dumps(reg_data, indent=2))
        assert reg_data["email"] == "alice@example.com"
        assert reg_data["active_bucket"].startswith("backuper-"), "Bucket name invalid"
        assert len(reg_data["buckets"]) == 1
        assert reg_data["buckets"][0]["region"] == "europe-west1"
        assert reg_data["buckets"][0]["storage_class"] == "NEARLINE"
        print("✓ Registration successful!")

        # ---- TEST 2: User Login & Token Retrieval ----
        print("\n--- Test 2: User Login & JWT Retrieval ---")
        login_payload = {
            "email": "alice@example.com",
            "password": "alicepassword123"
        }
        res = requests.post(f"{base_url}/auth/login", json=login_payload)
        print("Login Status Code:", res.status_code)
        assert res.status_code == 200, "Login failed"
        login_data = res.json()
        token = login_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("JWT Access Token generated successfully!")
        print("✓ Login successful!")

        # ---- TEST 3: Folder Creation ----
        print("\n--- Test 3: Create Workspace Folder in Cache ---")
        folder_payload = {
            "path": "",
            "folder_name": "Documents"
        }
        res = requests.post(f"{base_url}/files/create-folder", data=folder_payload, headers=headers)
        print("Create Folder Status:", res.status_code)
        assert res.status_code == 200, "Folder creation failed"
        print("✓ Folder creation successful!")

        # ---- TEST 4: File Upload to Subfolder ----
        print("\n--- Test 4: Upload File to GCS Documents Subfolder ---")
        file_content = b"This is a backup of a critical system report document."
        files = {
            "file": ("system_report.txt", file_content, "text/plain")
        }
        form_data = {
            "path": "Documents"
        }
        res = requests.post(f"{base_url}/files/upload", headers=headers, data=form_data, files=files)
        print("Upload File Status:", res.status_code)
        assert res.status_code == 200, "File upload failed"
        upload_data = res.json()
        print("File Upload Response:")
        print(json.dumps(upload_data, indent=2))
        file_id = upload_data["file"]["id"]
        print("✓ File upload & metadata caching successful!")

        # ---- TEST 5: Browse and Cache Check ----
        print("\n--- Test 5: Browse Folder Contents & Metadata Integrity ---")
        # Browse Documents
        res = requests.get(f"{base_url}/files/browse?path=Documents", headers=headers)
        print("Browse Documents Status:", res.status_code)
        assert res.status_code == 200, "Browse folder failed"
        browse_data = res.json()
        print("Folder Contents:")
        print(json.dumps(browse_data, indent=2))
        assert len(browse_data["files"]) == 1, "Cached file listing not returned"
        cached_file = browse_data["files"][0]
        assert cached_file["name"] == "system_report.txt"
        assert cached_file["path"] == "Documents/system_report.txt"
        assert cached_file["size"] == len(file_content)
        assert cached_file["storage_class"] == "NEARLINE"
        print("✓ Cache browse and metadata integrity verified!")

        # ---- TEST 6: Multi-Tenant Security Access Enforcement ----
        print("\n--- Test 6: Multi-Tenant Data Leakage Isolation Verification ---")
        # Register User Bob
        bob_reg = {
            "name": "Bob Security Auditor",
            "email": "bob@example.com",
            "password": "bobpassword456",
            "default_region": "us-central1",
            "default_storage_class": "STANDARD"
        }
        res = requests.post(f"{base_url}/auth/register", json=bob_reg)
        assert res.status_code == 200, "Bob registration failed"
        
        # Log Bob in to obtain his token
        res = requests.post(f"{base_url}/auth/login", json={"email": "bob@example.com", "password": "bobpassword456"})
        bob_token = res.json()["access_token"]
        bob_headers = {"Authorization": f"Bearer {bob_token}"}
        
        # Bob attempts to download Alice's file using her file ID
        print(f"Bob attempting to access Alice's cached file '{file_id}'...")
        res = requests.get(f"{base_url}/files/download/{file_id}", headers=bob_headers)
        print("Bob Unauthorized Download Access Status:", res.status_code)
        assert res.status_code == 403, "SECURITY BREACH: Bob successfully downloaded Alice's file!"
        
        # Bob attempts to browse Alice's bucket directly
        # Since active buckets are segmented, Bob is assigned his own active bucket. Let's make sure Bob can't view Alice's bucket
        alice_bucket = reg_data["active_bucket"]
        res = requests.get(f"{base_url}/files/browse?path=Documents", headers=bob_headers)
        # Verify Bob sees nothing (empty state) in Documents because he has a different active bucket
        assert len(res.json()["files"]) == 0
        print("✓ Multi-tenant isolation verified! Bob was strictly barred from accessing Alice's files.")

        # ---- TEST 7: File Deletion ----
        print("\n--- Test 7: Delete File and Clean Cache ---")
        res = requests.delete(f"{base_url}/files/{file_id}", headers=headers)
        print("Delete File Status:", res.status_code)
        assert res.status_code == 200, "Delete file failed"
        
        # Verify from browse
        res = requests.get(f"{base_url}/files/browse?path=Documents", headers=headers)
        assert len(res.json()["files"]) == 0, "File was not removed from cache"
        print("✓ File deleted and metadata cache cleaned successfully!")

        # ---- TEST 8: Folder Deletion ----
        print("\n--- Test 8: Folder Deletion and Recursive Cache Cleanup ---")
        # Let's upload a file inside Documents again first to test recursive deletion
        file_content_2 = b"Another test report inside Documents."
        files_2 = {
            "file": ("temp_report.txt", file_content_2, "text/plain")
        }
        form_data_2 = {
            "path": "Documents"
        }
        res = requests.post(f"{base_url}/files/upload", headers=headers, data=form_data_2, files=files_2)
        assert res.status_code == 200, "Failed to upload file to Documents for Test 8"
        
        # Verify it was added
        res = requests.get(f"{base_url}/files/browse?path=Documents", headers=headers)
        assert len(res.json()["files"]) == 1, "Uploaded file not visible inside folder"
        
        # Verify "Documents" is in folders tree
        res = requests.get(f"{base_url}/files/tree", headers=headers)
        assert "Documents" in res.json(), "Documents folder missing from tree"

        # Now, delete the folder
        res = requests.delete(f"{base_url}/files/folder/Documents", headers=headers)
        print("Delete Folder Status:", res.status_code)
        assert res.status_code == 200, "Delete folder failed"
        print("Folder deletion response:", res.json())

        # Verify folder "Documents" is no longer in tree
        res = requests.get(f"{base_url}/files/tree", headers=headers)
        assert "Documents" not in res.json(), "Documents folder should be removed from tree"

        # Verify browse on root has no folders named Documents
        res = requests.get(f"{base_url}/files/browse?path=", headers=headers)
        assert "Documents" not in res.json()["folders"], "Documents folder still exists in root browse list"

        # Verify browse on Documents shows nothing (empty)
        res = requests.get(f"{base_url}/files/browse?path=Documents", headers=headers)
        assert len(res.json()["files"]) == 0, "Nested files under deleted folder still exist in cache"
        assert len(res.json()["folders"]) == 0, "Nested folders under deleted folder still exist in cache"
        print("✓ Folder and all its nested contents recursively deleted and cleaned from cache successfully!")

        # ---- TEST 9: Chunked Upload ----
        print("\n--- Test 9: Chunked File Upload End-to-End ---")
        init_payload = {
            "path": "",
            "filename": "chunked_test.bin",
            "file_size": 12,
            "content_type": "application/octet-stream"
        }
        res = requests.post(f"{base_url}/files/upload/initiate", data=init_payload, headers=headers)
        print("Initiate Chunked Upload Status:", res.status_code)
        assert res.status_code == 200, "Initiation failed"
        upload_id = res.json()["upload_id"]

        # Chunk 1 (6 bytes)
        res = requests.post(
            f"{base_url}/files/upload/chunk",
            data={"upload_id": upload_id, "offset": 0},
            files={"file": ("chunked_test.bin", b"hello ", "application/octet-stream")},
            headers=headers
        )
        print("Upload Chunk 1 Status:", res.status_code)
        assert res.status_code == 200, "Chunk 1 upload failed"

        # Chunk 2 (6 bytes)
        res = requests.post(
            f"{base_url}/files/upload/chunk",
            data={"upload_id": upload_id, "offset": 6},
            files={"file": ("chunked_test.bin", b"world!", "application/octet-stream")},
            headers=headers
        )
        print("Upload Chunk 2 Status:", res.status_code)
        assert res.status_code == 200, "Chunk 2 upload failed"

        # Complete
        res = requests.post(
            f"{base_url}/files/upload/complete",
            data={"upload_id": upload_id},
            headers=headers
        )
        print("Complete Chunked Upload Status:", res.status_code)
        assert res.status_code == 200, "Completion failed"
        complete_data = res.json()
        file_id = complete_data["file"]["id"]
        assert complete_data["file"]["size"] == 12

        # Verify content by downloading
        res = requests.get(f"{base_url}/files/download/{file_id}", headers=headers)
        print("Download Assembled File Status:", res.status_code)
        assert res.status_code == 200, "Download failed"
        assert res.content == b"hello world!", f"Content mismatch: expected 'hello world!', got {res.content}"
        print("✓ Assembled file content matches original input exactly!")

        # Clean up chunked file
        res = requests.delete(f"{base_url}/files/{file_id}", headers=headers)
        assert res.status_code == 200, "Clean up failed"
        print("✓ Chunked upload verification finished successfully!")


        # ---- TEST 10: Folder Deduplication ----
        print("\n--- Test 10: Folder Deduplication ---")
        # Create an explicit folder
        res = requests.post(f"{base_url}/files/create-folder", data={"path": "", "folder_name": "DedupeFolder"}, headers=headers)
        assert res.status_code == 200
        # Upload a file inside it
        res = requests.post(f"{base_url}/files/upload", headers=headers, data={"path": "DedupeFolder"}, files={"file": ("test.txt", b"dedupe", "text/plain")})
        assert res.status_code == 200
        # Browse root and verify "DedupeFolder" appears exactly once
        res = requests.get(f"{base_url}/files/browse?path=", headers=headers)
        folders = res.json()["folders"]
        assert folders.count("DedupeFolder") == 1, "DedupeFolder appeared more than once!"
        print("✓ Folder deduplication verified!")

        # ---- TEST 11: Pagination ----
        print("\n--- Test 11: Pagination Slicing ---")
        # Upload 3 more files to root to have a total of 3 files (assuming we delete others or have them)
        # Root currently has nothing because we deleted Documents and Chunked file. Oh wait, we have DedupeFolder.
        # Let's upload 3 files
        for i in range(3):
            requests.post(f"{base_url}/files/upload", headers=headers, data={"path": ""}, files={"file": (f"pfile_{i}.txt", b"a", "text/plain")})
        
        # Now root has 1 folder (DedupeFolder) and 3 files (pfile_0.txt, pfile_1.txt, pfile_2.txt) -> total 4 items
        # Let's paginate with limit=2
        res1 = requests.get(f"{base_url}/files/browse?path=&limit=2&page=1", headers=headers)
        page1 = res1.json()
        assert page1["total_count"] == 4, f"Expected 4 total items, got {page1['total_count']}"
        assert len(page1["folders"]) + len(page1["files"]) == 2
        # Page 1 should have DedupeFolder and pfile_0.txt (sorted alphabetically)
        # actually pfile_0, pfile_1, pfile_2.
        
        res2 = requests.get(f"{base_url}/files/browse?path=&limit=2&page=2", headers=headers)
        page2 = res2.json()
        assert len(page2["folders"]) + len(page2["files"]) == 2
        print("✓ Pagination verified!")

        # ---- TEST 12: Image Thumbnails ---
        print("\n--- Test 12: Image Thumbnails in Chunked Upload ---")
        init_payload_thumb = {
            "path": "",
            "filename": "image.png",
            "file_size": 69,
            "content_type": "image/png"
        }
        res = requests.post(f"{base_url}/files/upload/initiate", data=init_payload_thumb, headers=headers)
        assert res.status_code == 200
        up_id = res.json()["upload_id"]
        res = requests.post(f"{base_url}/files/upload/chunk", data={"upload_id": up_id, "offset": 0}, files={"file": ("image.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82", "image/png")}, headers=headers)
        assert res.status_code == 200
        res = requests.post(f"{base_url}/files/upload/complete", data={"upload_id": up_id}, headers=headers)
        assert res.status_code == 200
        
        res = requests.get(f"{base_url}/files/browse?path=", headers=headers)
        files = res.json()["files"]
        img_file = next((f for f in files if f["name"] == "image.png"), None)
        assert img_file is not None
        print("Waiting for snapshot worker to process...")
        time.sleep(3)
        res = requests.get(f"{base_url}/files/browse?path=", headers=headers)
        files = res.json()["files"]
        img_file = next((f for f in files if f["name"] == "image.png"), None)
        assert img_file is not None
        assert img_file.get("thumbnail_base64") is not None, "Thumbnail base64 was not generated by worker!"
        assert img_file["thumbnail_base64"].startswith("data:image/jpeg;base64,"), "Thumbnail format invalid"
        print("✓ Image thumbnails cached asynchronously and retrieved successfully!")


        print("\n===============================================")
        print("  ALL INTEGRATION TESTS PASSED TRIUMPHANTLY!   ")
        print("===============================================")

    except AssertionError as e:
        print("\n❌ TEST FAILURE DETECTED:")
        print(str(e))
        success = False
    except Exception as e:
        print("\n❌ AN UNEXPECTED EXCEPTION OCCURRED:")
        print(str(e))
        success = False
    finally:
        print("\nShutting down backend process...")
        backend_proc.terminate()
        backend_proc.wait()
        
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    run_integration_tests()
