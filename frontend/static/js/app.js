document.addEventListener("DOMContentLoaded", () => {
    // 1. Auth Guard
    const token = localStorage.getItem("backuper_token");
    if (!token) {
        window.location.href = "/login";
        return;
    }

    // 2. State Management
    let currentPath = "";
    let currentViewMode = "list"; // "list" or "grid"
    let currentPage = 1;
    let pageSize = 200;
    let totalCount = 0;
    let userData = null;
    let foldersList = [];
    let filesList = [];
    let allFolderPaths = []; // for tree generation

    // 3. DOM Elements
    const activeBucketNameEl = document.getElementById("active-bucket-name");
    const userDisplayNameEl = document.getElementById("user-display-name");
    const userAvatarEl = document.getElementById("user-avatar");
    const logoutBtn = document.getElementById("logout-btn");
    const syncCacheBtn = document.getElementById("sync-cache-btn");
    const searchInput = document.getElementById("search-input");
    
    // Breadcrumbs & Folders Tree
    const breadcrumbsContainer = document.getElementById("breadcrumbs");
    const folderTreeContainer = document.getElementById("folder-tree");
    const sidebarNewFolderBtn = document.getElementById("sidebar-new-folder-btn");

    // View Modes
    const viewListBtn = document.getElementById("view-list-btn");
    const viewGridBtn = document.getElementById("view-grid-btn");
    const contentsContainer = document.getElementById("contents-container");
    const appSidebar = document.getElementById("app-sidebar");
    const mobileMenuBtn = document.getElementById("mobile-menu-btn");
    const sidebarBucketSelect = document.getElementById("sidebar-bucket-select");
    const pageSizeSelect = document.getElementById("page-size-select");
    const prevPageBtn = document.getElementById("prev-page-btn");
    const nextPageBtn = document.getElementById("next-page-btn");
    const paginationInfo = document.getElementById("pagination-info");

    // Upload Zone
    const uploadZone = document.getElementById("upload-zone");
    const fileInput = document.getElementById("file-input");

    // Modals
    const profileModal = document.getElementById("profile-modal");
    const openProfileBtn = document.getElementById("open-profile-btn");
    const profileModalClose = document.getElementById("profile-modal-close");
    const profileForm = document.getElementById("profile-form");
    const bucketsTableBody = document.getElementById("buckets-table-body");
    const createBucketForm = document.getElementById("create-bucket-form");

    const folderModal = document.getElementById("folder-modal");
    const folderModalClose = document.getElementById("folder-modal-close");
    const folderForm = document.getElementById("folder-form");

    const alertContainer = document.getElementById("alert-container");

    // 4. Alert Helper
    function showToast(message, type = "success") {
        const toast = document.createElement("div");
        toast.className = `alert-toast ${type}`;
        
        const icon = document.createElement("i");
        icon.className = type === "success" ? "fa-solid fa-circle-check" : "fa-solid fa-circle-exclamation";
        
        const text = document.createElement("span");
        text.innerText = message;
        
        toast.appendChild(icon);
        toast.appendChild(text);
        alertContainer.appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(50px)";
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 4000);
    }

    // 5. API Fetch Wrapper
    async function apiRequest(endpoint, options = {}) {
        options.headers = options.headers || {};
        options.headers["Authorization"] = `Bearer ${token}`;
        
        try {
            const response = await fetch(endpoint, options);
            if (response.status === 401) {
                // Token expired/invalid
                localStorage.removeItem("backuper_token");
                localStorage.removeItem("backuper_user");
                window.location.href = "/login";
                return null;
            }
            
            // For file downloads
            const contentType = response.headers.get("content-type");
            if (contentType && contentType.includes("application/octet-stream")) {
                return response;
            }
            
            return await response.json();
        } catch (error) {
            console.error(`API Request to ${endpoint} failed:`, error);
            showToast("Network connection error.", "error");
            return null;
        }
    }

    // 6. Init Application
    async function init() {
        await loadUserProfile();
        await refreshWorkspace();
    }

    // Load Profile & Buckets info
    async function loadUserProfile() {
        const data = await apiRequest("/api/profile");
        if (data) {
            userData = data;
            
            // Set User Display details
            userDisplayNameEl.innerText = userData.name;
            userAvatarEl.innerText = userData.name.charAt(0).toUpperCase();
            
            // Active Bucket Badge
            activeBucketNameEl.innerText = userData.active_bucket;
            
            // Populate profile modal fields
            document.getElementById("profile-name").value = userData.name;
            document.getElementById("profile-email").value = userData.email;
            
            // Populate Buckets Table in profile modal
            renderBucketsTable();
            
            // Populate Sidebar Bucket Selector
            sidebarBucketSelect.innerHTML = "";
            userData.buckets.forEach(bucket => {
                const opt = document.createElement("option");
                opt.value = bucket.name;
                opt.textContent = bucket.name;
                if (bucket.is_active) opt.selected = true;
                sidebarBucketSelect.appendChild(opt);
            });
        }
    }

    // Populate Buckets Table
    function renderBucketsTable() {
        bucketsTableBody.innerHTML = "";
        
        userData.buckets.forEach(bucket => {
            const tr = document.createElement("tr");
            if (bucket.is_active) {
                tr.className = "active-bucket-row";
            }
            
            tr.innerHTML = `
                <td>
                    <i class="fa-solid fa-bucket" style="margin-right: 8px; color: ${bucket.is_active ? 'var(--secondary)' : 'var(--text-muted)'};"></i>
                    <span>${bucket.name}</span>
                </td>
                <td>${bucket.region}</td>
                <td><span style="font-size: 0.8rem; background: rgba(255,255,255,0.06); padding: 4px 8px; border-radius: 4px;">${bucket.storage_class}</span></td>
                <td style="text-align: right;">
                    ${bucket.is_active 
                        ? '<span style="font-size: 0.8rem; color: var(--success); font-weight:600;"><i class="fa-solid fa-circle-check"></i> Active</span>' 
                        : `<button class="btn-secondary switch-bucket-btn" data-name="${bucket.name}" style="padding: 4px 10px; font-size: 0.8rem;">Switch</button>`}
                </td>
            `;
            
            bucketsTableBody.appendChild(tr);
        });


        // Sidebar Bucket switch
        sidebarBucketSelect.addEventListener("change", async (e) => {
            const name = e.target.value;
            const result = await apiRequest(`/api/profile/active-bucket?bucket_name=${name}`, { method: "POST" });
            if (result) {
                showToast("Switched workspace bucket!", "success");
                currentPath = ""; currentPage = 1;
                await init();
            }
        });

        // Mobile menu toggle
        mobileMenuBtn.addEventListener("click", () => {
            appSidebar.classList.toggle("sidebar-open");
        });

        // Pagination handlers
        pageSizeSelect.addEventListener("change", (e) => {
            pageSize = parseInt(e.target.value, 10);
            currentPage = 1;
            refreshWorkspace();
        });

        prevPageBtn.addEventListener("click", () => {
            if (currentPage > 1) {
                currentPage--;
                refreshWorkspace();
            }
        });

        nextPageBtn.addEventListener("click", () => {
            const maxPage = Math.ceil(totalCount / pageSize);
            if (currentPage < maxPage) {
                currentPage++;
                refreshWorkspace();
            }
        });

        // Setup Switch Bucket action listeners
        document.querySelectorAll(".switch-bucket-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                const name = e.target.dataset.name;
                const result = await apiRequest(`/api/profile/active-bucket?bucket_name=${name}`, {
                    method: "POST"
                });
                if (result) {
                    showToast("Switched workspace bucket!", "success");
                    currentPath = ""; // reset path
                    await init();
                    profileModal.classList.remove("active");
                }
            });
        });
    }

    // 7. Refresh Folder Tree & Active View
    async function refreshWorkspace() {
        // Fetch folders tree structure
        const treeData = await apiRequest("/api/files/tree");
        if (treeData) {
            allFolderPaths = treeData;
            renderFolderTree();
        }

        // Fetch direct folders & files inside currentPath
        const browseData = await apiRequest(`/api/files/browse?path=${encodeURIComponent(currentPath)}&limit=${pageSize}&page=${currentPage}`);
        if (browseData) {
            foldersList = browseData.folders;
            filesList = browseData.files;
            totalCount = browseData.total_count || 0;
            
            // Update pagination UI
            const startIdx = totalCount === 0 ? 0 : ((currentPage - 1) * pageSize) + 1;
            const endIdx = Math.min(currentPage * pageSize, totalCount);
            paginationInfo.innerText = `Showing ${startIdx}-${endIdx} of ${totalCount}`;
            prevPageBtn.disabled = currentPage <= 1;
            nextPageBtn.disabled = endIdx >= totalCount;
            
            renderBreadcrumbs(browseData.breadcrumbs);
            renderContents();
        }
    }

    // Recursive Folder Tree Builder
    function renderFolderTree() {
        folderTreeContainer.innerHTML = "";
        
        // Root Node representation
        const rootNode = document.createElement("div");
        rootNode.className = `tree-node ${currentPath === "" ? "active" : ""}`;
        rootNode.innerHTML = `
            <div class="tree-node-content" data-path="">
                <i class="fa-solid fa-database"></i>
                <span>Root Workspace</span>
            </div>
        `;
        rootNode.addEventListener("click", () => navigatePath(""));
        folderTreeContainer.appendChild(rootNode);

        // We construct a nested structure of our paths
        const treeObj = {};
        allFolderPaths.forEach(path => {
            const parts = path.split("/");
            let currentLevel = treeObj;
            parts.forEach(part => {
                if (!currentLevel[part]) {
                    currentLevel[part] = { _path: "", children: {} };
                }
                currentLevel = currentLevel[part].children;
            });
        });

        // Set absolute paths
        function setPaths(obj, parentPath = "") {
            for (const key in obj) {
                const absolute = parentPath ? `${parentPath}/${key}` : key;
                obj[key]._path = absolute;
                setPaths(obj[key].children, absolute);
            }
        }
        setPaths(treeObj);

        // HTML builder
        function buildTreeHTML(obj, container) {
            const sortedKeys = Object.keys(obj).sort();
            sortedKeys.forEach(key => {
                const node = obj[key];
                const nodeEl = document.createElement("div");
                nodeEl.className = `tree-node ${currentPath === node._path ? "active" : ""}`;
                
                const contentEl = document.createElement("div");
                contentEl.className = "tree-node-content";
                contentEl.style.paddingLeft = "10px";
                contentEl.dataset.path = node._path;
                contentEl.innerHTML = `
                    <i class="fa-solid fa-folder"></i>
                    <span>${key}</span>
                `;
                
                nodeEl.appendChild(contentEl);
                
                contentEl.addEventListener("click", (e) => {
                    e.stopPropagation();
                    navigatePath(node._path);
                });

                if (Object.keys(node.children).length > 0) {
                    const childrenContainer = document.createElement("div");
                    childrenContainer.className = "tree-children";
                    buildTreeHTML(node.children, childrenContainer);
                    nodeEl.appendChild(childrenContainer);
                }

                container.appendChild(nodeEl);
            });
        }

        const subTreeContainer = document.createElement("div");
        subTreeContainer.className = "tree-children";
        buildTreeHTML(treeObj, subTreeContainer);
        folderTreeContainer.appendChild(subTreeContainer);
    }

    // Navigate to a new directory
    function navigatePath(path) {
        currentPath = path;
        refreshWorkspace();
    }

    // Breadcrumbs Builder
    function renderBreadcrumbs(breadcrumbs) {
        breadcrumbsContainer.innerHTML = "";
        
        breadcrumbs.forEach((crumb, index) => {
            const isLast = index === breadcrumbs.length - 1;
            
            const span = document.createElement("span");
            span.className = `breadcrumb-item ${isLast ? 'active' : ''}`;
            span.innerText = crumb.name;
            
            if (!isLast) {
                span.addEventListener("click", () => navigatePath(crumb.path));
                breadcrumbsContainer.appendChild(span);
                
                const separator = document.createElement("span");
                separator.className = "breadcrumb-separator";
                separator.innerHTML = ' <i class="fa-solid fa-chevron-right" style="font-size:0.75rem;"></i> ';
                breadcrumbsContainer.appendChild(separator);
            } else {
                breadcrumbsContainer.appendChild(span);
            }
        });
    }

    // 8. Contents Rendering (List vs Grid)
    function renderContents(filterQuery = "") {
        contentsContainer.innerHTML = "";
        
        const q = filterQuery.toLowerCase().trim();
        const filteredFolders = foldersList.filter(f => f.toLowerCase().includes(q));
        const filteredFiles = filesList.filter(f => f.name.toLowerCase().includes(q));

        if (filteredFolders.length === 0 && filteredFiles.length === 0) {
            contentsContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-folder-open"></i>
                    <h3>Folder is Empty</h3>
                    <p>Drag and drop files to upload to this workspace folder.</p>
                </div>
            `;
            return;
        }

        if (currentViewMode === "list") {
            renderListView(filteredFolders, filteredFiles);
        } else {
            renderGridView(filteredFolders, filteredFiles);
        }
    }

    // Render Table format
    function renderListView(folders, files) {
        const table = document.createElement("table");
        table.className = "list-view-table";
        table.innerHTML = `
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Date Uploaded</th>
                    <th>Size</th>
                    <th>Storage Location</th>
                    <th>Class</th>
                    <th style="text-align: right;">Actions</th>
                </tr>
            </thead>
            <tbody></tbody>
        `;
        const tbody = table.querySelector("tbody");

        // Folders Rows
        folders.forEach(folder => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>
                    <div class="file-name-cell" data-type="folder" data-name="${folder}">
                        <i class="fa-solid fa-folder"></i>
                        <span>${folder}</span>
                    </div>
                </td>
                <td style="color: var(--text-muted);">—</td>
                <td style="color: var(--text-muted);">—</td>
                <td style="color: var(--text-muted);">—</td>
                <td style="color: var(--text-muted);">—</td>
                <td style="text-align: right;">
                    <button class="action-btn delete-folder-btn" data-name="${folder}" title="Delete Folder">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });

        // Files Rows
        files.forEach(file => {
            const tr = document.createElement("tr");
            const iconClass = getFileIcon(file.name);
            const formattedSize = formatBytes(file.size);
            const formattedDate = new Date(file.upload_date).toLocaleDateString() + " " + new Date(file.upload_date).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            
            let fileIconHTML = `<i class="${iconClass}"></i>`;
            if (file.thumbnail_base64) {
                fileIconHTML = `<img src="${file.thumbnail_base64}" class="list-thumbnail" alt="thumbnail">`;
            }
            
            tr.innerHTML = `
                <td>
                    <div class="file-name-cell" data-type="file" data-id="${file.id}">
                        ${fileIconHTML}
                        <span>${file.name}</span>
                    </div>
                </td>
                <td>${formattedDate}</td>
                <td>${formattedSize}</td>
                <td>${file.storage_location}</td>
                <td><span style="font-size: 0.75rem; background: rgba(255,255,255,0.06); padding: 4px 8px; border-radius: 4px;">${file.storage_class}</span></td>
                <td style="text-align: right;" class="action-cell">
                    <button class="action-btn download-btn" data-id="${file.id}" title="Download File">
                        <i class="fa-solid fa-download"></i>
                    </button>
                    <button class="action-btn delete delete-btn" data-id="${file.id}" title="Delete File">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });

        contentsContainer.appendChild(table);
        setupActionListeners();
    }

    // Render Grid format
    function renderGridView(folders, files) {
        const grid = document.createElement("div");
        grid.className = "grid-view-layout";

        // Folder cards
        folders.forEach(folder => {
            const card = document.createElement("div");
            card.className = "file-card glass-panel";
            card.innerHTML = `
                <div class="card-icon"><i class="fa-solid fa-folder"></i></div>
                <div class="card-title">${folder}</div>
                <div class="card-meta">Directory</div>
                <div class="card-actions" style="opacity: 1; position: static; margin-top: 10px;">
                    <button class="action-btn delete-folder-btn" data-name="${folder}" title="Delete Folder">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            `;
            card.addEventListener("click", (e) => {
                if (e.target.closest(".action-btn")) return;
                const path = currentPath ? `${currentPath}/${folder}` : folder;
                navigatePath(path);
            });
            grid.appendChild(card);
        });

        // File cards
        files.forEach(file => {
            const card = document.createElement("div");
            card.className = "file-card glass-panel";
            const iconClass = getFileIcon(file.name);
            const formattedSize = formatBytes(file.size);
            
            let cardIconHTML = `<div class="card-icon"><i class="${iconClass}"></i></div>`;
            if (file.thumbnail_base64) {
                cardIconHTML = `<img src="${file.thumbnail_base64}" class="card-thumbnail" alt="thumbnail">`;
            }
            
            card.innerHTML = `
                ${cardIconHTML}
                <div class="card-title" title="${file.name}">${file.name}</div>
                <div class="card-meta">${formattedSize}</div>
                <div class="card-actions">
                    <button class="action-btn download-btn" data-id="${file.id}" title="Download File">
                        <i class="fa-solid fa-download"></i>
                    </button>
                    <button class="action-btn delete delete-btn" data-id="${file.id}" title="Delete File">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            `;
            grid.appendChild(card);
        });

        contentsContainer.appendChild(grid);
        setupActionListeners();
    }

    // Helper file icon resolver
    function getFileIcon(filename) {
        const ext = filename.split(".").pop().toLowerCase();
        if (["jpg", "jpeg", "png", "gif", "svg", "webp"].includes(ext)) {
            return "fa-solid fa-file-image";
        } else if (["pdf"].includes(ext)) {
            return "fa-solid fa-file-pdf";
        } else if (["doc", "docx", "txt", "rtf", "md"].includes(ext)) {
            return "fa-solid fa-file-lines";
        } else if (["xls", "xlsx", "csv"].includes(ext)) {
            return "fa-solid fa-file-excel";
        } else if (["zip", "tar", "gz", "rar", "7z"].includes(ext)) {
            return "fa-solid fa-file-zipper";
        }
        return "fa-solid fa-file";
    }

    // Bytes Formatter
    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return "0 Bytes";
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
    }

    // Set actions click events
    function setupActionListeners() {
        // Double-click or click navigation on folder names
        document.querySelectorAll(".file-name-cell[data-type='folder']").forEach(cell => {
            cell.addEventListener("click", () => {
                const name = cell.dataset.name;
                const path = currentPath ? `${currentPath}/${name}` : name;
                navigatePath(path);
            });
        });

        // Download Action
        document.querySelectorAll(".download-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                
                showToast("Preparing file download...", "success");
                try {
                    const response = await apiRequest(`/api/files/download/${id}`);
                    if (response) {
                        const blob = await response.blob();
                        const url = window.URL.createObjectURL(blob);
                        
                        // Extract filename from header
                        const disposition = response.headers.get("content-disposition");
                        let filename = "download";
                        if (disposition && disposition.indexOf("attachment") !== -1) {
                            const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
                            const matches = filenameRegex.exec(disposition);
                            if (matches != null && matches[1]) { 
                                filename = matches[1].replace(/['"]/g, '');
                            }
                        }
                        
                        const a = document.createElement("a");
                        a.href = url;
                        a.download = filename;
                        document.body.appendChild(a);
                        a.click();
                        a.remove();
                    }
                } catch (err) {
                    showToast("Download failed.", "error");
                }
            });
        });

        // Delete File Action
        document.querySelectorAll(".delete-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                
                if (confirm("Are you sure you want to permanently delete this file from GCS?")) {
                    const result = await apiRequest(`/api/files/${id}`, {
                        method: "DELETE"
                    });
                    if (result) {
                        showToast("File deleted successfully", "success");
                        refreshWorkspace();
                    }
                }
            });
        });

        // Delete Folder Action (local placeholder folders inside cache)
        document.querySelectorAll(".delete-folder-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const name = btn.dataset.name;
                if (confirm(`Are you sure you want to permanently delete folder '${name}' and all its contents from GCS?`)) {
                    const folderPath = currentPath ? `${currentPath}/${name}` : name;
                    
                    showToast(`Deleting folder '${name}' and its contents...`, "success");
                    const result = await apiRequest(`/api/files/folder/${encodeURIComponent(folderPath)}`, {
                        method: "DELETE"
                    });
                    if (result) {
                        showToast("Folder deleted successfully", "success");
                        refreshWorkspace();
                    }
                }
            });
        });
    }

    // 9. View Toggles & Header controls
    viewListBtn.addEventListener("click", () => {
        viewListBtn.classList.add("active");
        viewGridBtn.classList.remove("active");
        currentViewMode = "list";
        renderContents(searchInput.value);
    });

    viewGridBtn.addEventListener("click", () => {
        viewGridBtn.classList.add("active");
        viewListBtn.classList.remove("active");
        currentViewMode = "grid";
        renderContents(searchInput.value);
    });

    searchInput.addEventListener("input", (e) => {
        renderContents(e.target.value);
    });

    syncCacheBtn.addEventListener("click", async () => {
        showToast("Syncing cache with GCS...", "success");
        const result = await apiRequest("/api/files/sync", {
            method: "POST"
        });
        if (result) {
            showToast(result.message, "success");
            refreshWorkspace();
        }
    });

    // 10. File Upload Handlers (Drag and Drop)
    uploadZone.addEventListener("click", () => {
        fileInput.click();
    });

    fileInput.addEventListener("change", async (e) => {
        const files = e.target.files;
        if (files.length > 0) {
            await uploadFiles(files);
            // Reset so the same file can be selected and re-uploaded
            fileInput.value = "";
        }
    });

    // Drag-over styling shifts
    uploadZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        uploadZone.classList.add("dragover");
    });

    uploadZone.addEventListener("dragleave", () => {
        uploadZone.classList.remove("dragover");
    });

    uploadZone.addEventListener("drop", (e) => {
        e.preventDefault();
        uploadZone.classList.remove("dragover");
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            uploadFiles(files);
        }
    });

    async function uploadFiles(files) {
        const MAX_BYTES = 5 * 1024 * 1024 * 1024; // 5 GB — must match backend limit
        let uploadedCount = 0;
        const total = files.length;

        for (let i = 0; i < total; i++) {
            const file = files[i];

            // Client-side size guard — give immediate feedback before any network I/O
            if (file.size > MAX_BYTES) {
                showToast(`${file.name} exceeds the 5 GB limit and was skipped.`, "error");
                continue;
            }

            const fileLabel = `${file.name} (${formatBytes(file.size)})`;
            showToast(`Uploading ${fileLabel}...`, "success");
            uploadedCount++;

            try {
                await uploadFileWithProgress(file, uploadedCount, total);
                showToast(`Finished uploading ${file.name}!`, "success");
            } catch (err) {
                showToast(`Failed uploading ${file.name}: ${err.message || err}`, "error");
            }
        }

        // Guarantee progress bar is removed regardless of success/failure
        const pc = document.getElementById("upload-progress-container");
        if (pc) {
            pc.style.transition = "opacity 0.4s";
            pc.style.opacity = "0";
            setTimeout(() => pc.remove(), 400);
        }

        refreshWorkspace();
    }

    /**
     * Upload a single file using the two-step direct-to-GCS signed URL flow:
     *
     *  1. POST /api/files/upload-url  → backend issues a signed GCS PUT URL
     *  2. PUT  <signed-url>           → browser uploads directly to GCS
     *                                   (bypasses Cloud Run's 32 MB body limit)
     *  3. POST /api/files/register    → backend caches the file metadata
     *
     * XHR is used for step 2 so progress events work on the actual upload.
     */
    function uploadFileWithProgress(file, index, total) {
        return new Promise(async (resolve, reject) => {

            // --- Create / reuse the progress bar UI ---
            let progressContainer = document.getElementById("upload-progress-container");
            if (!progressContainer) {
                progressContainer = document.createElement("div");
                progressContainer.id = "upload-progress-container";
                progressContainer.style.cssText = `
                    position: fixed; bottom: 24px; right: 24px;
                    width: 360px; z-index: 9999;
                    background: rgba(20, 20, 30, 0.92);
                    backdrop-filter: blur(16px);
                    border: 1px solid rgba(255,255,255,0.1);
                    border-radius: 12px; padding: 16px 20px;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
                    font-family: inherit; color: #e0e0e8;
                `;
                document.body.appendChild(progressContainer);
            }

            const setProgress = (pct, label) => {
                progressContainer.innerHTML = `
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <span style="font-size:0.82rem;font-weight:600;opacity:0.9;">
                            <i class="fa-solid fa-cloud-arrow-up" style="margin-right:6px;color:var(--secondary,#7c5cfc);"></i>
                            ${label} ${index}/${total}
                        </span>
                        <span id="upload-pct" style="font-size:0.82rem;font-weight:700;color:var(--secondary,#7c5cfc);">${pct}%</span>
                    </div>
                    <div style="font-size:0.75rem;margin-bottom:8px;opacity:0.7;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
                         title="${file.name}">
                        ${file.name} — ${formatBytes(file.size)}
                    </div>
                    <div style="width:100%;height:6px;border-radius:3px;background:rgba(255,255,255,0.08);overflow:hidden;">
                        <div id="upload-bar" style="width:${pct}%;height:100%;border-radius:3px;background:linear-gradient(90deg,var(--secondary,#7c5cfc),var(--accent,#00d4ff));transition:width 0.15s ease;"></div>
                    </div>
                `;
            };

            setProgress(0, "Initiating");

            // ── Generate Thumbnail ──────────────────────────────────────
            let thumbnailBase64 = null;
            if (file.type && file.type.startsWith("image/")) {
                try {
                    thumbnailBase64 = await generateThumbnail(file);
                } catch(e) { console.warn("Thumbnail generation failed", e); }
            }

            // ── Step 1: Initiate Upload ─────────────────────────────────
            let uploadId;
            const CHUNK_SIZE = 5 * 1024 * 1024; // 5 MB chunks
            try {
                const fd1 = new FormData();
                fd1.append("path", currentPath);
                fd1.append("filename", file.name);
                fd1.append("file_size", String(file.size));
                fd1.append("content_type", file.type || "application/octet-stream");
                if (thumbnailBase64) {
                    fd1.append("thumbnail_base64", thumbnailBase64);
                }

                const res = await fetch("/api/files/upload/initiate", {
                    method: "POST",
                    headers: { "Authorization": `Bearer ${token}` },
                    body: fd1,
                });

                if (res.status === 401) {
                    localStorage.removeItem("backuper_token");
                    window.location.href = "/login";
                    return reject(new Error("Session expired"));
                }
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    return reject(new Error(err.detail || `Server error ${res.status}`));
                }
                const initData = await res.json();
                uploadId = initData.upload_id;
            } catch (err) {
                return reject(new Error(`Failed to initiate upload: ${err.message}`));
            }

            // Helper to upload a single chunk using XHR
            const uploadChunkWithXHR = (chunk, startOffset, chunkIndex, totalChunks) => {
                return new Promise((resolveChunk, rejectChunk) => {
                    const xhr = new XMLHttpRequest();

                    xhr.upload.addEventListener("progress", (e) => {
                        if (e.lengthComputable) {
                            const chunkProgress = e.loaded;
                            const totalUploadedBytes = startOffset + chunkProgress;
                            const pct = Math.min(Math.round((totalUploadedBytes / file.size) * 100), 99);
                            setProgress(pct, `Uploading chunk ${chunkIndex + 1}/${totalChunks}`);
                        }
                    });

                    xhr.addEventListener("load", () => {
                        if (xhr.status >= 200 && xhr.status < 300) {
                            resolveChunk();
                        } else {
                            rejectChunk(new Error(`Server error ${xhr.status}`));
                        }
                    });

                    xhr.addEventListener("error", () => rejectChunk(new Error("Network error")));
                    xhr.addEventListener("abort", () => rejectChunk(new Error("Aborted")));

                    const fd = new FormData();
                    fd.append("upload_id", uploadId);
                    fd.append("offset", String(startOffset));
                    fd.append("file", chunk, file.name);

                    xhr.open("POST", "/api/files/upload/chunk");
                    xhr.setRequestHeader("Authorization", `Bearer ${token}`);
                    xhr.send(fd);
                });
            };

            // ── Step 2: Upload Chunks Sequentially ──────────────────────
            const totalChunks = Math.ceil(file.size / CHUNK_SIZE) || 1;
            for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
                const start = chunkIndex * CHUNK_SIZE;
                const end = Math.min(start + CHUNK_SIZE, file.size);
                const chunk = file.slice(start, end);

                let success = false;
                let attempts = 3;
                while (attempts > 0 && !success) {
                    try {
                        await uploadChunkWithXHR(chunk, start, chunkIndex, totalChunks);
                        success = true;
                    } catch (err) {
                        attempts--;
                        if (attempts === 0) {
                            return reject(new Error(`Failed to upload chunk ${chunkIndex + 1}: ${err.message}`));
                        }
                        await new Promise(r => setTimeout(r, 1000));
                    }
                }
            }

            setProgress(99, "Completing");

            // ── Step 3: Complete Upload ─────────────────────────────────
            try {
                const fd3 = new FormData();
                fd3.append("upload_id", uploadId);

                const res = await fetch("/api/files/upload/complete", {
                    method: "POST",
                    headers: { "Authorization": `Bearer ${token}` },
                    body: fd3,
                });

                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    return reject(new Error(err.detail || `Server error ${res.status}`));
                }
                const result = await res.json();
                setProgress(100, "Done");
                resolve(result);
            } catch (err) {
                return reject(new Error(`Failed to complete upload: ${err.message}`));
            }
        });
    }



    function generateThumbnail(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => {
                const img = new Image();
                img.onload = () => {
                    const canvas = document.createElement("canvas");
                    const MAX_WIDTH = 120;
                    const MAX_HEIGHT = 120;
                    let width = img.width;
                    let height = img.height;

                    if (width > height) {
                        if (width > MAX_WIDTH) {
                            height *= MAX_WIDTH / width;
                            width = MAX_WIDTH;
                        }
                    } else {
                        if (height > MAX_HEIGHT) {
                            width *= MAX_HEIGHT / height;
                            height = MAX_HEIGHT;
                        }
                    }
                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext("2d");
                    ctx.drawImage(img, 0, 0, width, height);
                    resolve(canvas.toDataURL("image/jpeg", 0.7));
                };
                img.onerror = reject;
                img.src = e.target.result;
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    // 11. Profile Modal Handlers
    openProfileBtn.addEventListener("click", () => {
        profileModal.classList.add("active");
    });

    profileModalClose.addEventListener("click", () => {
        profileModal.classList.remove("active");
    });

    // Handle Profile Details update
    profileForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = document.getElementById("profile-name").value;
        const email = document.getElementById("profile-email").value;

        const result = await apiRequest("/api/profile/update", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ name, email })
        });

        if (result) {
            showToast("Profile updated!", "success");
            await loadUserProfile();
        }
    });

    // Handle New Bucket creation
    createBucketForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const region = document.getElementById("new-bucket-region").value;
        const storage_class = document.getElementById("new-bucket-class").value;

        showToast("Creating GCS bucket. Please wait...", "success");

        const result = await apiRequest("/api/profile/bucket", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ region, storage_class })
        });

        if (result) {
            showToast("Created GCS bucket successfully!", "success");
            await loadUserProfile();
            createBucketForm.reset();
        }
    });

    // 12. Create Folder Modal Handlers
    sidebarNewFolderBtn.addEventListener("click", () => {
        folderModal.classList.add("active");
    });

    folderModalClose.addEventListener("click", () => {
        folderModal.classList.remove("active");
    });

    folderForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = document.getElementById("new-folder-name").value;

        const formData = new FormData();
        formData.append("path", currentPath);
        formData.append("folder_name", name);

        const result = await apiRequest("/api/files/create-folder", {
            method: "POST",
            body: formData
        });

        if (result) {
            showToast("Folder created in workspace", "success");
            folderModal.classList.remove("active");
            folderForm.reset();
            refreshWorkspace();
        }
    });

    // 13. Logout Handler
    logoutBtn.addEventListener("click", () => {
        localStorage.removeItem("backuper_token");
        localStorage.removeItem("backuper_user");
        window.location.href = "/login";
    });

    // Run
    init();
});
