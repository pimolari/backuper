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
    let allFolderPaths = null; 
    let selectedItems = new Set(); // Tracks selected file IDs and folder names
    let lastCheckedIndex = -1; // Track for shift-click selection

    // 3. DOM Elements
    const appContainer = document.getElementById("app-container");  // now refers to .app-body
    const activeBucketNameEl = document.getElementById("active-bucket-name");
    const userAvatarEl = document.getElementById("user-avatar");
    const logoutBtn = document.getElementById("logout-btn");
    const syncCacheBtn = document.getElementById("sync-cache-btn");
    const searchInput = document.getElementById("search-input");
    
    const breadcrumbsContainer = document.getElementById("breadcrumbs");
    const folderTreeContainer = document.getElementById("folder-tree");
    const sidebarNewFolderBtn = document.getElementById("sidebar-new-folder-btn");

    const viewListBtn = document.getElementById("view-list-btn");
    const viewGridBtn = document.getElementById("view-grid-btn");
    const contentsContainer = document.getElementById("contents-container");
    const sidebarToggleBtn = document.getElementById("sidebar-toggle-btn");
    const sidebarToggleIcon = document.getElementById("sidebar-toggle-icon");
    const pageSizeSelect = document.getElementById("page-size-select");
    const prevPageBtn = document.getElementById("prev-page-btn");
    const nextPageBtn = document.getElementById("next-page-btn");
    const paginationInfo = document.getElementById("pagination-info");

    const uploadZone = document.getElementById("upload-zone");
    const fileInput = document.getElementById("file-input");

    // Selection Toolbar
    const selectionToolbar = document.getElementById("selection-toolbar");
    const selectAllCheckbox = document.getElementById("select-all-checkbox");
    const selectionCountEl = document.getElementById("selection-count");
    const bulkDeleteBtn = document.getElementById("bulk-delete-btn");
    const clearSelectionBtn = document.getElementById("clear-selection-btn");

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

    const viewerModal = document.getElementById("viewer-modal");
    const viewerModalClose = document.getElementById("viewer-modal-close");
    const viewerTitle = document.getElementById("viewer-title");
    const viewerDisplay = document.getElementById("viewer-display");
    const viewerPrevBtn = document.getElementById("viewer-prev");
    const viewerNextBtn = document.getElementById("viewer-next");

    const alertContainer = document.getElementById("alert-container");

    const headerBucketBadge = document.getElementById("header-bucket-badge");
    const bucketSelectorModal = document.getElementById("bucket-selector-modal");
    const bucketModalClose = document.getElementById("bucket-modal-close");
    const quickBucketList = document.getElementById("quick-bucket-list");
    const openProfileFromBucket = document.getElementById("open-profile-from-bucket");

    // SSE implementation
    let eventSource = null;

    // File Viewer State
    let viewerFileList = [];
    let viewerCurrentIndex = -1;

    // 4. Alert Helper
    function showToast(message, type = "success") {
        const toast = document.createElement("div");
        toast.className = `alert ${type === "success" ? "alert-success" : type === "error" ? "alert-error" : "alert-info"}`;
        
        const icon = document.createElement("i");
        icon.className = type === "success" ? "fa-solid fa-check-circle" : "fa-solid fa-circle-exclamation";
        
        const text = document.createElement("span");
        text.innerText = message;
        
        toast.appendChild(icon);
        toast.appendChild(text);
        alertContainer.appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(50px)";
            toast.style.transition = "all 0.3s ease";
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    // 5. API Fetch Wrapper
    /**
     * Wrapper for fetch API to handle authorization, JSON parsing, and basic error toast notifications.
     * @param {string} endpoint - The relative or absolute API URL to fetch.
     * @param {Object} [options={}] - Standard fetch options (method, body, headers).
     * @returns {Promise<Object|Response|null>} - Returns the JSON payload, the raw response for octet-streams, or null on error.
     */
    async function apiRequest(endpoint, options = {}) {
        options.headers = options.headers || {};
        options.headers["Authorization"] = `Bearer ${token}`;
        
        try {
            const response = await fetch(endpoint, options);
            if (response.status === 401) {
                localStorage.removeItem("backuper_token");
                window.location.href = "/login";
                return null;
            }
            if (!response.ok) {
                let errDetail = `API Error: ${response.status}`;
                try {
                    const errData = await response.json();
                    if (errData.detail) errDetail = JSON.stringify(errData.detail);
                } catch (e) {}
                console.error("API Error details:", errDetail);
                showToast(errDetail, "error");
                return null;
            }
            
            const contentType = response.headers.get("content-type");
            if (contentType && contentType.includes("application/octet-stream")) {
                return response;
            }
            
            return await response.json();
        } catch (error) {
            console.error(`API Request failed:`, error);
            showToast("Network connection error.", "error");
            return null;
        }
    }

    // 6. Init Application
    async function init() {
        await loadUserProfile();
        await refreshWorkspace();
    }

    let sseTimeout = null;

    function startTemporarySSE() {
        if (eventSource) {
            clearTimeout(sseTimeout);
            sseTimeout = setTimeout(stopSSE, 180000); // 3 minutes
            return;
        }
        
        eventSource = new EventSource('/api/files/events');
        eventSource.onmessage = (event) => {
            try {
                // Ignore keepalive comments, though EventSource native handling ignores comments anyway
                const data = JSON.parse(event.data);
                if (data.type === "bulk_delete_complete") {
                    refreshWorkspace(true);
                    stopSSE(); // We can stop early since the action is done
                }
            } catch (err) {
                console.error("Error parsing SSE data", err);
            }
        };
        
        eventSource.onerror = () => {
            console.error("SSE connection error");
            stopSSE(); // Just close on error, no need to endlessly retry
        };

        // Auto close after 3 minutes to save container cost
        clearTimeout(sseTimeout);
        sseTimeout = setTimeout(stopSSE, 180000);
    }

    function stopSSE() {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        clearTimeout(sseTimeout);
    }

    async function loadUserProfile() {
        const data = await apiRequest("/api/profile");
        if (data) {
            userData = data;
            
            // Set User Display details (Initials only for clean look)
            const initials = userData.name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
            userAvatarEl.innerText = initials;
            
            // Show full name on desktop; show only last segment on mobile for space
            const bucketName = userData.active_bucket;
            const bucketShort = bucketName.includes("-")
                ? bucketName.split("-").pop()
                : bucketName.length > 12 ? bucketName.slice(-10) + "…" : bucketName;
            activeBucketNameEl.innerText = bucketName;
            activeBucketNameEl.dataset.fullName = bucketName;
            activeBucketNameEl.dataset.shortName = bucketShort;
            // Apply appropriate label based on viewport
            function updateBucketLabel() {
                activeBucketNameEl.innerText = window.innerWidth <= 768
                    ? activeBucketNameEl.dataset.shortName
                    : activeBucketNameEl.dataset.fullName;
            }
            updateBucketLabel();
            // Update on resize
            if (!window._bucketResizeListenerAdded) {
                window.addEventListener("resize", updateBucketLabel);
                window._bucketResizeListenerAdded = true;
            }
            
            document.getElementById("profile-name").value = userData.name;
            document.getElementById("profile-email").value = userData.email;
            
            const isAdmin = userData.role === "admin";
            const adminConsoleBtn = document.getElementById("admin-console-btn");
            const tabInvitesBtn = document.getElementById("tab-invites-btn");
            if (isAdmin) {
                if (adminConsoleBtn) adminConsoleBtn.style.display = "flex";
                if (tabInvitesBtn) tabInvitesBtn.style.display = "block";
            } else {
                if (adminConsoleBtn) adminConsoleBtn.style.display = "none";
                if (tabInvitesBtn) tabInvitesBtn.style.display = "none";
            }
            
            renderBucketsTable();
        }
    }

    function renderBucketsTable() {
        bucketsTableBody.innerHTML = "";
        quickBucketList.innerHTML = "";
        
        userData.buckets.forEach(bucket => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td style="padding: 12px 4px;">
                    <i class="fa-solid fa-bucket" style="margin-right: 8px; color: ${bucket.is_active ? 'var(--primary)' : 'var(--text-muted)'};"></i>
                    <span style="font-weight: ${bucket.is_active ? '600' : '400'}">${bucket.name}</span>
                </td>
                <td style="padding: 12px 4px; color: var(--text-muted);">${bucket.region}</td>
                <td style="padding: 12px 4px; text-align: right;">
                    ${bucket.is_active 
                        ? '<span style="color: var(--success); font-weight:600; font-size: 0.85rem;"><i class="fa-solid fa-check"></i> Active</span>' 
                        : `<button class="btn-secondary switch-bucket-btn" data-name="${bucket.name}" style="padding: 4px 10px; font-size: 0.8rem;">Switch</button>`}
                </td>
            `;
            bucketsTableBody.appendChild(tr);

            // Also add to quick bucket list
            const quickItem = document.createElement("div");
            quickItem.className = "quick-bucket-item";
            quickItem.style.cssText = `padding: 12px; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: background 0.2s;`;
            quickItem.onmouseover = () => quickItem.style.background = "#f9fafb";
            quickItem.onmouseout = () => quickItem.style.background = "transparent";
            
            quickItem.innerHTML = `
                <div>
                    <div style="font-weight: ${bucket.is_active ? '600' : '400'}; color: ${bucket.is_active ? 'var(--primary)' : 'var(--text-main)'}">${bucket.name}</div>
                    <div style="font-size: 0.8rem; color: var(--text-muted)">${bucket.region} • ${bucket.storage_class}</div>
                </div>
                ${bucket.is_active ? '<i class="fa-solid fa-check" style="color: var(--success)"></i>' : '<button class="btn-secondary switch-bucket-btn" data-name="' + bucket.name + '" style="padding: 4px 8px; font-size: 0.75rem;">Switch</button>'}
            `;
            quickBucketList.appendChild(quickItem);
        });

        document.querySelectorAll(".switch-bucket-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                const name = e.currentTarget.dataset.name;
                const result = await apiRequest(`/api/profile/active-bucket?bucket_name=${name}`, { method: "POST" });
                if (result) {
                    showToast("Switched to " + name, "success");
                    currentPath = "";
                    selectedItems.clear();
                    updateSelectionUI();
                    // Close both modals immediately
                    profileModal.classList.remove("active");
                    bucketSelectorModal.classList.remove("active");
                    allFolderPaths = null;
                    await init();
                }
            });
        });
    }



    // Bucket Modals setup
    headerBucketBadge.addEventListener("click", () => {
        bucketSelectorModal.classList.add("active");
    });

    bucketModalClose.addEventListener("click", () => {
        bucketSelectorModal.classList.remove("active");
    });
    
    openProfileFromBucket.addEventListener("click", () => {
        bucketSelectorModal.classList.remove("active");
        profileModal.classList.add("active");
    });

    sidebarToggleBtn.addEventListener("click", () => {
        if (window.innerWidth <= 768) {
            appContainer.classList.toggle("sidebar-open");
        } else {
            appContainer.classList.toggle("sidebar-collapsed");
        }
    });

    document.addEventListener("click", (e) => {
        if (window.innerWidth <= 768 && appContainer.classList.contains("sidebar-open")) {
            const sidebarEl = document.querySelector(".sidebar");
            if (sidebarEl && !sidebarEl.contains(e.target) && !sidebarToggleBtn.contains(e.target)) {
                appContainer.classList.remove("sidebar-open");
            }
        }
    });

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

    // 7. Refresh Folder Tree & Active View
    /**
     * Refreshes the folder tree side panel and the main file browser view.
     * Executes API requests in parallel for optimized loading speeds.
     * @param {boolean} [forceTreeRefresh=false] - Whether to re-fetch the entire folder tree from the backend.
     */
    async function refreshWorkspace(forceTreeRefresh = false) {
        const tasks = [];
        const needsTreeFetch = forceTreeRefresh || !allFolderPaths;
        
        if (needsTreeFetch) {
            tasks.push(
                apiRequest("/api/files/tree").then(treeData => {
                    if (treeData) {
                        allFolderPaths = treeData;
                        renderFolderTree();
                    }
                })
            );
        }

        tasks.push(
            apiRequest(`/api/files/browse?path=${encodeURIComponent(currentPath)}&limit=${pageSize}&page=${currentPage}`).then(browseData => {
                return browseData;
            })
        );

        const results = await Promise.all(tasks);
        const browseData = needsTreeFetch ? results[1] : results[0];

        if (browseData) {
            foldersList = browseData.folders;
            filesList = browseData.files;
            totalCount = browseData.total_count || 0;
            
            const startIdx = totalCount === 0 ? 0 : ((currentPage - 1) * pageSize) + 1;
            const endIdx = Math.min(currentPage * pageSize, totalCount);
            paginationInfo.innerText = `Showing ${startIdx}-${endIdx} of ${totalCount}`;
            prevPageBtn.disabled = currentPage <= 1;
            nextPageBtn.disabled = endIdx >= totalCount;
            
            renderBreadcrumbs(browseData.breadcrumbs);
            renderContents(searchInput.value);
            
            // Build the unified list for viewer modal navigation
            viewerFileList = filesList.filter(f => !f.is_dir);
        }
    }

    function renderFolderTree() {
        folderTreeContainer.innerHTML = "";
        
        let bucketNameStr = "Storage";
        if (userData && userData.buckets) {
            const activeBucketObj = userData.buckets.find(b => b.name === userData.active_bucket);
            if (activeBucketObj) {
                bucketNameStr = activeBucketObj.name;
            }
        }

        const rootNode = document.createElement("div");
        rootNode.className = `tree-node ${currentPath === "" ? "active" : ""}`;
        rootNode.innerHTML = `
            <div class="tree-node-content" data-path="" style="align-items: flex-start;">
                <i class="fa-solid fa-server" style="margin-top: 4px;"></i>
                <div style="display:flex; flex-direction:column; line-height:1.2; overflow: hidden;">
                    <span>Root</span>
                    <span style="font-size:0.7rem; color:var(--text-muted); opacity:0.8; font-weight:normal; white-space:nowrap; text-overflow:ellipsis; overflow:hidden;">${bucketNameStr}</span>
                </div>
            </div>
        `;
        rootNode.addEventListener("click", () => navigatePath(""));
        folderTreeContainer.appendChild(rootNode);

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

        function setPaths(obj, parentPath = "") {
            for (const key in obj) {
                const absolute = parentPath ? `${parentPath}/${key}` : key;
                obj[key]._path = absolute;
                setPaths(obj[key].children, absolute);
            }
        }
        setPaths(treeObj);

        function buildTreeHTML(obj, container) {
            const sortedKeys = Object.keys(obj).sort();
            sortedKeys.forEach(key => {
                const node = obj[key];
                const isSelected = currentPath === node._path;
                const isExpanded = currentPath === node._path || currentPath.startsWith(node._path + "/");

                const nodeEl = document.createElement("div");
                nodeEl.className = `tree-node ${isSelected ? "active" : ""}`;
                
                const contentEl = document.createElement("div");
                contentEl.className = "tree-node-content";
                contentEl.dataset.path = node._path;
                contentEl.innerHTML = `
                    <i class="fa-solid ${isExpanded ? 'fa-folder-open' : 'fa-folder'}"></i>
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

    function navigatePath(path) {
        currentPath = path;
        currentPage = 1;
        lastCheckedIndex = -1;
        selectedItems.clear();
        updateSelectionUI();
        // Auto-collapse sidebar on mobile when a folder is selected
        if (window.innerWidth <= 768) {
            appContainer.classList.remove("sidebar-open");
        }
        refreshWorkspace();
    }

    function renderBreadcrumbs(breadcrumbs) {
        breadcrumbsContainer.innerHTML = "";

        // Smart truncation: always show first (Root) and last item.
        // Middle items are collapsed to "..." if there are more than 3 levels.
        const MAX_LABEL = 18; // max chars per crumb before truncating
        const truncate = (s) => s.length > MAX_LABEL ? s.slice(0, MAX_LABEL - 1) + "…" : s;

        let displayCrumbs;
        if (breadcrumbs.length <= 3) {
            displayCrumbs = breadcrumbs.map((c, i) => ({ ...c, label: truncate(c.name), ellipsis: false, index: i }));
        } else {
            // Show first, ellipsis, last
            displayCrumbs = [
                { ...breadcrumbs[0], label: truncate(breadcrumbs[0].name), ellipsis: false },
                { label: "…", ellipsis: true, path: null },
                { ...breadcrumbs[breadcrumbs.length - 1], label: truncate(breadcrumbs[breadcrumbs.length - 1].name), ellipsis: false },
            ];
        }

        displayCrumbs.forEach((crumb, i) => {
            const isLast = i === displayCrumbs.length - 1;

            if (crumb.ellipsis) {
                const el = document.createElement("span");
                el.className = "breadcrumb-ellipsis";
                el.title = breadcrumbs.slice(1, -1).map(c => c.name).join(" / ");
                el.innerText = "…";
                breadcrumbsContainer.appendChild(el);
                const sep = document.createElement("span");
                sep.className = "breadcrumb-separator";
                sep.innerHTML = '<i class="fa-solid fa-chevron-right"></i>';
                breadcrumbsContainer.appendChild(sep);
                return;
            }

            const span = document.createElement("span");
            span.className = `breadcrumb-item ${isLast ? "active" : ""}`;
            span.innerText = crumb.label;
            if (crumb.name !== crumb.label) span.title = crumb.name;

            if (!isLast) {
                span.addEventListener("click", () => navigatePath(crumb.path));
                breadcrumbsContainer.appendChild(span);
                const sep = document.createElement("span");
                sep.className = "breadcrumb-separator";
                sep.innerHTML = '<i class="fa-solid fa-chevron-right"></i>';
                breadcrumbsContainer.appendChild(sep);
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
        
        viewerFileList = filteredFiles; // update viewable list

        if (filteredFolders.length === 0 && filteredFiles.length === 0) {
            contentsContainer.className = "contents-container list-view";
            contentsContainer.innerHTML = `
                <div style="text-align: center; padding: 60px 20px; color: var(--text-muted);">
                    <i class="fa-solid fa-folder-open" style="font-size: 3rem; margin-bottom: 16px; opacity: 0.5;"></i>
                    <h3>Folder is Empty</h3>
                    <p style="font-size: 0.9rem; margin-top: 8px;">Upload files or create subfolders to get started.</p>
                </div>
            `;
            return;
        }

        contentsContainer.className = `contents-container ${currentViewMode}-view`;

        const checkboxIdxBase = 0;

        foldersList.forEach((folder, idx) => {
            const card = document.createElement("div");
            card.className = "item-card folder-card";
            card.innerHTML = `
                <div class="item-select">
                    <label class="custom-checkbox">
                        <input type="checkbox" class="item-checkbox" data-id="folder:${folder}" data-idx="${checkboxIdxBase + idx}">
                        <span class="checkmark"></span>
                    </label>
                </div>
                <div class="item-icon"><i class="fa-solid fa-folder"></i></div>
                <div class="item-info">
                    <div class="item-name" title="${folder}">${folder}</div>
                    <div class="item-meta">Directory</div>
                </div>
                <div class="item-actions">
                    <button class="action-btn delete-folder-btn" data-name="${folder}" title="Delete Folder">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            `;
            
            const checkbox = card.querySelector(".item-checkbox");
            checkbox.addEventListener("change", (e) => toggleSelection(`folder:${folder}`, e.target.checked));
            
            card.addEventListener("click", (e) => {
                if(e.target.closest(".item-checkbox") || e.target.closest(".action-btn")) return;
                const path = currentPath ? `${currentPath}/${folder}` : folder;
                navigatePath(path);
            });
            contentsContainer.appendChild(card);
        });

        // Render Files
        filteredFiles.forEach((file, idx) => {
            const isChecked = selectedItems.has(`file:${file.id}`);
            const card = document.createElement("div");
            card.className = "item-card";
            
            const iconClass = getFileIcon(file.name);
            let iconHTML = `<div class="item-icon"><i class="${iconClass}"></i></div>`;
            if (file.thumbnail_base64) {
                iconHTML = `<div class="item-icon image"><img src="${file.thumbnail_base64}" alt="thumbnail"></div>`;
            }
            
            const formattedSize = formatBytes(file.size);
            
            card.innerHTML = `
                <input type="checkbox" class="item-checkbox" data-id="file:${file.id}" ${isChecked ? "checked" : ""}>
                ${iconHTML}
                <div class="item-info">
                    <div class="item-name" title="${file.name}">${file.name}</div>
                    <div class="item-meta">${formattedSize} &bull; ${file.storage_class}</div>
                </div>
                <div class="item-actions">
                    <button class="action-btn download-btn" data-id="${file.id}" title="Download">
                        <i class="fa-solid fa-download"></i>
                    </button>
                    <button class="action-btn delete-btn" data-id="${file.id}" title="Delete">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            `;
            
            const checkbox = card.querySelector(".item-checkbox");
            if (selectedItems.has(`file:${file.id}`)) checkbox.checked = true;
            
            card.addEventListener("click", (e) => {
                if(e.target.closest(".item-checkbox") || e.target.closest(".action-btn")) return;
                openViewer(idx); // open file viewer
            });
            
            contentsContainer.appendChild(card);
        });

        setupCheckboxes();
        setupActionListeners();
    }

    function setupCheckboxes() {
        const checkboxes = Array.from(document.querySelectorAll(".item-checkbox"));
        checkboxes.forEach(cb => {
            cb.addEventListener("click", (e) => {
                const isChecked = e.target.checked;
                const id = e.target.dataset.id;
                const idx = parseInt(e.target.dataset.idx, 10);
                
                if (e.shiftKey && lastCheckedIndex !== -1) {
                    // Re-query in case DOM changed
                    const freshCheckboxes = Array.from(document.querySelectorAll(".item-checkbox"));
                    const start = Math.min(idx, lastCheckedIndex);
                    const end = Math.max(idx, lastCheckedIndex);
                    for (let i = start; i <= end; i++) {
                        const targetCb = freshCheckboxes[i];
                        if (targetCb) {
                            targetCb.checked = isChecked;
                            toggleSelection(targetCb.dataset.id, isChecked, false);
                        }
                    }
                } else {
                    toggleSelection(id, isChecked, false);
                }
                lastCheckedIndex = idx;
                updateSelectionUI();
            });
        });
        
        selectAllCheckbox.checked = false;
        selectAllCheckbox.onchange = (e) => {
            const isChecked = e.target.checked;
            checkboxes.forEach(cb => {
                cb.checked = isChecked;
                toggleSelection(cb.dataset.id, isChecked, false);
            });
            updateSelectionUI();
        };
    }

    // Toggle Checkbox Selection
    function toggleSelection(id, isSelected, updateUI = true) {
        if (isSelected) {
            selectedItems.add(id);
        } else {
            selectedItems.delete(id);
        }
        if (updateUI) updateSelectionUI();
    }

    function updateSelectionUI() {
        if (selectedItems.size > 0) {
            selectionToolbar.style.display = "flex";
            selectionCountEl.innerText = `${selectedItems.size} selected`;
        } else {
            selectionToolbar.style.display = "none";
        }
    }

    clearSelectionBtn.addEventListener("click", () => {
        selectedItems.clear();
        updateSelectionUI();
        document.querySelectorAll(".item-checkbox").forEach(cb => cb.checked = false);
    });

    bulkDeleteBtn.addEventListener("click", async () => {
        if (!confirm(`Are you sure you want to queue ${selectedItems.size} item(s) for permanent deletion?`)) return;

        showToast("Queueing items for deletion...", "info");
        
        const itemsToQueue = Array.from(selectedItems).map(item => {
            const [type, val] = item.split(":");
            if (type === "folder") {
                return `folder:${currentPath ? `${currentPath}/${val}` : val}`;
            }
            return item;
        });

        const result = await apiRequest(`/api/files/bulk-delete/queue`, { 
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ items: itemsToQueue })
        });
        
        if (result) {
            showToast(`Queued ${selectedItems.size} item(s) across ${result.chunks || '?'} background jobs.`, "success");
            selectedItems.clear();
            updateSelectionUI();
            
            // Open temporary SSE connection to listen for completion
            startTemporarySSE();
            
            // Remove locally instantly for better UX while backend processes
            itemsToQueue.forEach(item => {
                const cb = document.querySelector(`.item-checkbox[data-id="${item}"]`);
                if (cb && cb.closest('.item-card')) {
                    cb.closest('.item-card').remove();
                }
            });
        }
    });

    function getFileIcon(filename) {
        const ext = filename.split(".").pop().toLowerCase();
        if (["jpg", "jpeg", "png", "gif", "svg", "webp"].includes(ext)) return "fa-solid fa-file-image";
        if (["pdf"].includes(ext)) return "fa-solid fa-file-pdf";
        if (["doc", "docx", "txt", "rtf", "md"].includes(ext)) return "fa-solid fa-file-lines";
        if (["xls", "xlsx", "csv"].includes(ext)) return "fa-solid fa-file-excel";
        if (["zip", "tar", "gz", "rar", "7z"].includes(ext)) return "fa-solid fa-file-zipper";
        if (["mp4", "avi", "mov", "webm"].includes(ext)) return "fa-solid fa-file-video";
        if (["mp3", "wav", "ogg"].includes(ext)) return "fa-solid fa-file-audio";
        return "fa-solid fa-file";
    }

    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return "0 Bytes";
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
    }

    function setupActionListeners() {
        document.querySelectorAll(".download-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                showToast("Preparing download...", "info");
                try {
                    const response = await apiRequest(`/api/files/download/${id}`);
                    if (response) {
                        const blob = await response.blob();
                        const url = window.URL.createObjectURL(blob);
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

        document.querySelectorAll(".delete-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                if (confirm("Delete this file permanently?")) {
                    const result = await apiRequest(`/api/files/${id}`, { method: "DELETE" });
                    if (result) {
                        showToast("File deleted", "success");
                        selectedItems.delete(`file:${id}`);
                        updateSelectionUI();
                        refreshWorkspace(true);
                    }
                }
            });
        });

        document.querySelectorAll(".delete-folder-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const name = btn.dataset.name;
                if (confirm(`Delete folder '${name}' and all contents?`)) {
                    const folderPath = currentPath ? `${currentPath}/${name}` : name;
                    showToast("Deleting folder...", "info");
                    const result = await apiRequest(`/api/files/folder/${encodeURIComponent(folderPath)}`, { method: "DELETE" });
                    if (result) {
                        showToast("Folder deleted", "success");
                        selectedItems.delete(`folder:${name}`);
                        updateSelectionUI();
                        refreshWorkspace(true);
                    }
                }
            });
        });
    }

    // 9. File Viewer Modal Logic
    function openViewer(index) {
        if (index < 0 || index >= viewerFileList.length) return;
        viewerCurrentIndex = index;
        const file = viewerFileList[index];
        
        viewerTitle.innerText = file.name;
        viewerDisplay.innerHTML = ""; // clear previous
        
        const ext = file.name.split(".").pop().toLowerCase();
        const isImage = ["jpg", "jpeg", "png", "gif", "svg", "webp"].includes(ext);

        if (isImage) {
            // Priority: Thumbnail if present, then attempt download full? 
            // In a real app we'd fetch a signed url for full preview. For now, use thumbnail or fallback icon if no thumbnail generated yet.
            if (file.thumbnail_base64) {
                viewerDisplay.innerHTML = `<img src="${file.thumbnail_base64}" alt="${file.name}">`;
            } else {
                viewerDisplay.innerHTML = `<i class="fa-solid fa-image generic-icon"></i>`;
            }
        } else {
            const iconClass = getFileIcon(file.name);
            viewerDisplay.innerHTML = `<i class="${iconClass} generic-icon"></i>`;
        }

        viewerPrevBtn.disabled = viewerCurrentIndex === 0;
        viewerNextBtn.disabled = viewerCurrentIndex === viewerFileList.length - 1;

        viewerModal.classList.add("active");
    }

    function closeViewer() {
        viewerModal.classList.remove("active");
        viewerCurrentIndex = -1;
    }

    viewerModalClose.addEventListener("click", closeViewer);

    viewerPrevBtn.addEventListener("click", () => {
        if (viewerCurrentIndex > 0) openViewer(viewerCurrentIndex - 1);
    });

    viewerNextBtn.addEventListener("click", () => {
        if (viewerCurrentIndex < viewerFileList.length - 1) openViewer(viewerCurrentIndex + 1);
    });

    document.addEventListener("keydown", (e) => {
        if (viewerModal.classList.contains("active")) {
            if (e.key === "Escape") closeViewer();
            else if (e.key === "ArrowLeft" && viewerCurrentIndex > 0) openViewer(viewerCurrentIndex - 1);
            else if (e.key === "ArrowRight" && viewerCurrentIndex < viewerFileList.length - 1) openViewer(viewerCurrentIndex + 1);
        }
    });

    // 10. View Toggles & Header controls
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
        showToast("Syncing cache...", "info");
        const result = await apiRequest("/api/files/sync", { method: "POST" });
        if (result) {
            showToast(result.message, "success");
            refreshWorkspace(true);
        }
    });

    // 11. File Upload Handlers
    uploadZone.addEventListener("click", () => fileInput.click());

    fileInput.addEventListener("change", async (e) => {
        const files = e.target.files;
        if (files.length > 0) {
            await uploadFiles(files);
            fileInput.value = "";
        }
    });

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
        if (files.length > 0) uploadFiles(files);
    });

    async function uploadFiles(files) {
        startTemporarySSE();
        const MAX_BYTES = 5 * 1024 * 1024 * 1024;
        let uploadedCount = 0;
        const total = files.length;

        for (let i = 0; i < total; i++) {
            const file = files[i];
            if (file.size > MAX_BYTES) {
                showToast(`${file.name} exceeds 5 GB limit.`, "error");
                continue;
            }

            showToast(`Uploading ${file.name}...`, "info");
            uploadedCount++;

            try {
                await uploadFileWithProgress(file, uploadedCount, total);
                showToast(`${file.name} uploaded!`, "success");
            } catch (err) {
                showToast(`Failed uploading ${file.name}: ${err.message}`, "error");
            }
        }

        const pc = document.getElementById("upload-progress-container");
        if (pc) {
            pc.style.opacity = "0";
            setTimeout(() => pc.remove(), 400);
        }
        refreshWorkspace(true);
    }

    function uploadFileWithProgress(file, index, total) {
        return new Promise(async (resolve, reject) => {
            let progressContainer = document.getElementById("upload-progress-container");
            if (!progressContainer) {
                progressContainer = document.createElement("div");
                progressContainer.id = "upload-progress-container";
                progressContainer.style.cssText = `
                    position: fixed; bottom: 24px; right: 24px;
                    width: 320px; z-index: 9999;
                    background: var(--bg-surface);
                    border: 1px solid var(--border-color);
                    border-radius: 8px; padding: 16px;
                    box-shadow: var(--shadow-lg);
                    color: var(--text-main);
                `;
                document.body.appendChild(progressContainer);
            }

            const setProgress = (pct, label) => {
                progressContainer.innerHTML = `
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <span style="font-size:0.85rem;font-weight:600;">
                            <i class="fa-solid fa-cloud-arrow-up" style="margin-right:6px;color:var(--primary);"></i>
                            ${label}
                        </span>
                        <span style="font-size:0.85rem;font-weight:600;color:var(--primary);">${pct}%</span>
                    </div>
                    <div style="font-size:0.75rem;margin-bottom:8px;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${file.name}">
                        ${file.name}
                    </div>
                    <div style="width:100%;height:6px;border-radius:3px;background:#e2e8f0;overflow:hidden;">
                        <div style="width:${pct}%;height:100%;border-radius:3px;background:var(--primary);transition:width 0.15s ease;"></div>
                    </div>
                `;
            };

            setProgress(0, "Initiating");

            let uploadId;
            const CHUNK_SIZE = 5 * 1024 * 1024;
            try {
                const fd1 = new FormData();
                fd1.append("path", currentPath);
                fd1.append("filename", file.name);
                fd1.append("file_size", String(file.size));
                fd1.append("content_type", file.type || "application/octet-stream");

                const res = await fetch("/api/files/upload/initiate", {
                    method: "POST",
                    headers: { "Authorization": `Bearer ${token}` },
                    body: fd1,
                });

                if (res.status === 401) return reject(new Error("Session expired"));
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    return reject(new Error(err.detail || `Server error ${res.status}`));
                }
                const initData = await res.json();
                uploadId = initData.upload_id;
            } catch (err) {
                return reject(new Error(`Initiate failed: ${err.message}`));
            }

            const uploadChunkWithXHR = (chunk, startOffset, chunkIndex, totalChunks) => {
                return new Promise((resolveChunk, rejectChunk) => {
                    const xhr = new XMLHttpRequest();
                    xhr.upload.addEventListener("progress", (e) => {
                        if (e.lengthComputable) {
                            const chunkProgress = e.loaded;
                            const totalUploadedBytes = startOffset + chunkProgress;
                            const pct = Math.min(Math.round((totalUploadedBytes / file.size) * 100), 99);
                            setProgress(pct, `Uploading ${chunkIndex + 1}/${totalChunks}`);
                        }
                    });
                    xhr.addEventListener("load", () => {
                        if (xhr.status >= 200 && xhr.status < 300) resolveChunk();
                        else rejectChunk(new Error(`Server error ${xhr.status}`));
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
                        if (attempts === 0) return reject(new Error(`Chunk failed: ${err.message}`));
                        await new Promise(r => setTimeout(r, 1000));
                    }
                }
            }

            setProgress(99, "Completing");

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
                return reject(new Error(`Complete failed: ${err.message}`));
            }
        });
    }



    // 12. Profile & Folder Modals
    openProfileBtn.addEventListener("click", () => profileModal.classList.add("active"));
    profileModalClose.addEventListener("click", () => profileModal.classList.remove("active"));
    
    // Profile Tabs
    const profileTabs = document.querySelectorAll('.profile-tab-btn');
    const profileContents = document.querySelectorAll('.profile-tab-content');
    profileTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            profileTabs.forEach(t => {
                t.classList.remove('active');
                t.style.fontWeight = '500';
                t.style.color = 'var(--text-muted)';
            });
            profileContents.forEach(c => c.style.display = 'none');
            
            tab.classList.add('active');
            tab.style.fontWeight = '600';
            tab.style.color = 'var(--primary)';
            document.getElementById(tab.dataset.target).style.display = 'block';
        });
    });

    // Invite Logic
    const inviteForm = document.getElementById('invite-form');
    if (inviteForm) {
        inviteForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('invite-email').value;
            const result = await apiRequest("/api/profile/invites", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ invited_email: email })
            });
            if (result) {
                const link = `${window.location.origin}/login?invite=${result.id}`;
                document.getElementById('invite-link-input').value = link;
                document.getElementById('invite-result').style.display = 'block';
                inviteForm.reset();
            }
        });
    }
    
    const copyInviteBtn = document.getElementById('copy-invite-btn');
    if (copyInviteBtn) {
        copyInviteBtn.addEventListener('click', () => {
            const input = document.getElementById('invite-link-input');
            input.select();
            document.execCommand('copy');
            showToast("Copied to clipboard!", "success");
        });
    }

    // Admin Console Logic
    const adminConsoleBtn = document.getElementById("admin-console-btn");
    const adminCloseBtn = document.getElementById("admin-close-btn");
    const workspaceSection = document.getElementById("workspace-section");
    const adminConsoleSection = document.getElementById("admin-console-section");
    
    if (adminConsoleBtn) {
        adminConsoleBtn.addEventListener('click', async () => {
            if (window.innerWidth <= 768) {
                const appContainer = document.getElementById("app-container");
                if (appContainer) appContainer.classList.remove("sidebar-open");
            }
            workspaceSection.style.display = "none";
            adminConsoleSection.style.display = "flex";
            await loadAdminUsers();
        });
    }
    
    if (adminCloseBtn) {
        adminCloseBtn.addEventListener('click', () => {
            adminConsoleSection.style.display = "none";
            workspaceSection.style.display = "flex";
        });
    }

    const adminTabs = document.querySelectorAll('.admin-tab-btn');
    const adminViews = document.querySelectorAll('.admin-view');
    adminTabs.forEach(tab => {
        tab.addEventListener('click', async () => {
            adminTabs.forEach(t => {
                t.classList.remove('active');
                t.style.background = 'transparent';
                t.style.fontWeight = '500';
                t.style.color = 'var(--text-muted)';
                t.style.boxShadow = 'none';
            });
            adminViews.forEach(v => v.style.display = 'none');
            
            tab.classList.add('active');
            tab.style.background = 'var(--bg-surface)';
            tab.style.fontWeight = '600';
            tab.style.color = 'var(--text-main)';
            tab.style.boxShadow = 'var(--shadow-sm)';
            const targetId = tab.dataset.target;
            document.getElementById(targetId).style.display = 'block';
            
            if (targetId === "admin-users-view") await loadAdminUsers();
            else await loadAdminInvites();
        });
    });

    async function loadAdminUsers() {
        const users = await apiRequest("/api/profile/users");
        if (!users) return;
        const tbody = document.getElementById("admin-users-tbody");
        tbody.innerHTML = "";
        users.forEach(u => {
            const tr = document.createElement("tr");
            const bucketsStr = u.buckets.map(b => b.name).join(", ");
            tr.innerHTML = `
                <td style="padding: 12px 16px; border-bottom: 1px solid var(--border-color);">${u.email}</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid var(--border-color);">${new Date(u.enrolment_date).toLocaleDateString()}</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid var(--border-color);">${u.last_login_date ? new Date(u.last_login_date).toLocaleDateString() : 'Never'}</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid var(--border-color);"><span title="${bucketsStr}">${u.buckets.length}</span></td>
                <td style="padding: 12px 16px; border-bottom: 1px solid var(--border-color); text-align: right; white-space: nowrap;">
                    <button class="btn-secondary deactivate-btn" data-id="${u.id}" ${!u.is_active ? 'disabled' : ''} style="font-size: 0.8rem; padding: 4px 8px; margin-right: 4px;">${u.is_active ? 'Deactivate' : 'Inactive'}</button>
                    <button class="btn-secondary delete-user-btn" data-id="${u.id}" style="font-size: 0.8rem; padding: 4px 8px; color: var(--error);">Delete</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
        
        document.querySelectorAll('.deactivate-btn').forEach(b => b.addEventListener('click', async (e) => {
            const id = e.target.dataset.id;
            if (confirm("Deactivate this user?")) {
                const res = await apiRequest(`/api/profile/users/${id}/deactivate`, { method: "POST" });
                if (res) {
                    showToast("User deactivated.", "success");
                    loadAdminUsers();
                }
            }
        }));
        
        document.querySelectorAll('.delete-user-btn').forEach(b => b.addEventListener('click', async (e) => {
            const id = e.target.dataset.id;
            if (confirm("Permanently delete this user and ALL their data? This cannot be undone.")) {
                const res = await apiRequest(`/api/profile/users/${id}`, { method: "DELETE" });
                if (res) {
                    showToast("User queued for permanent deletion.", "info");
                    loadAdminUsers();
                }
            }
        }));
    }

    async function loadAdminInvites() {
        const invites = await apiRequest("/api/profile/invites");
        if (!invites) return;
        const tbody = document.getElementById("admin-invites-tbody");
        tbody.innerHTML = "";
        invites.forEach(inv => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td style="padding: 12px 16px; border-bottom: 1px solid var(--border-color);">${inv.invited_email}</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid var(--border-color);">${inv.inviter_email}</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid var(--border-color);">${new Date(inv.created_at).toLocaleDateString()}</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid var(--border-color); font-weight: 500;">${inv.status}</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid var(--border-color); text-align: right; white-space: nowrap;">
                    ${inv.status === 'pending' ? `<button class="btn-secondary cancel-invite-btn" data-id="${inv.id}" style="font-size: 0.8rem; padding: 4px 8px; color: var(--error);">Cancel</button>` : ''}
                </td>
            `;
            tbody.appendChild(tr);
        });
        
        document.querySelectorAll('.cancel-invite-btn').forEach(b => b.addEventListener('click', async (e) => {
            const id = e.target.dataset.id;
            if (confirm("Cancel this invitation?")) {
                const res = await apiRequest(`/api/profile/invites/${id}/cancel`, { method: "POST" });
                if (res) {
                    showToast("Invite cancelled.", "info");
                    loadAdminInvites();
                }
            }
        }));
    }

    profileForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = document.getElementById("profile-name").value;
        const email = document.getElementById("profile-email").value;

        const result = await apiRequest("/api/profile/update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, email })
        });
        if (result) {
            showToast("Profile updated!", "success");
            await loadUserProfile();
        }
    });

    createBucketForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const region = document.getElementById("new-bucket-region").value;
        const storage_class = document.getElementById("new-bucket-class").value;
        showToast("Creating GCS bucket...", "info");
        const result = await apiRequest("/api/profile/bucket", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ region, storage_class })
        });
        if (result) {
            showToast("Created bucket successfully!", "success");
            await loadUserProfile();
            createBucketForm.reset();
        }
    });

    sidebarNewFolderBtn.addEventListener("click", () => folderModal.classList.add("active"));
    folderModalClose.addEventListener("click", () => folderModal.classList.remove("active"));

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
            showToast("Folder created", "success");
            folderModal.classList.remove("active");
            folderForm.reset();
            refreshWorkspace(true);
        }
    });

    logoutBtn.addEventListener("click", () => {
        localStorage.removeItem("backuper_token");
        window.location.href = "/login";
    });

    // Run
    init();
});
