const BACKEND_URL = document.querySelector('meta[name="backend-url"]')?.content || '';
window.BACKEND_URL = BACKEND_URL;

document.addEventListener("DOMContentLoaded", () => {
    const loginCard = document.getElementById("login-card");
    const signupCard = document.getElementById("signup-card");
    const showSignup = document.getElementById("show-signup");
    const showLogin = document.getElementById("show-login");

    const loginForm = document.getElementById("login-form");
    const signupForm = document.getElementById("signup-form");
    const alertContainer = document.getElementById("alert-container");

    let currentInviteToken = null;

    // Check URL for invite token
    const urlParams = new URLSearchParams(window.location.search);
    const inviteToken = urlParams.get('invite');
    if (inviteToken) {
        // Validate token
        fetch(`${window.BACKEND_URL || ''}/api/auth/validate-invite?token=${inviteToken}`)
            .then(res => res.json())
            .then(data => {
                if (data.valid) {
                    currentInviteToken = inviteToken;
                    document.getElementById("signup-email").value = data.email;
                    document.getElementById("signup-email").readOnly = true;
                    
                    loginCard.style.display = "none";
                    signupCard.style.display = "block";
                    showToast("Invitation valid. Please complete your registration.", "success");
                } else {
                    showToast("Invalid or expired invitation link.", "error");
                    loginCard.style.display = "block";
                    signupCard.style.display = "none";
                }
            })
            .catch(err => {
                console.error(err);
                showToast("Failed to validate invitation.", "error");
            });
    }

    // Helper to display toast notifications
    window.showToast = function(message, type = "success") {
        const toast = document.createElement("div");
        toast.className = `alert ${type === "success" ? "alert-success" : type === "error" ? "alert-error" : "alert-info"}`;
        
        const icon = document.createElement("i");
        if (type === "success") {
            icon.className = "fa-solid fa-check-circle";
        } else {
            icon.className = "fa-solid fa-circle-exclamation";
        }
        
        const text = document.createElement("span");
        text.innerText = message;
        
        toast.appendChild(icon);
        toast.appendChild(text);
        alertContainer.appendChild(toast);
        
        // Auto-remove after 4 seconds
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(50px)";
            toast.style.transition = "all 0.3s ease";
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 4000);
    };

    // Form Submission: Login
    if (loginForm) {
        loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            
            const email = document.getElementById("login-email").value;
            const password = document.getElementById("login-password").value;

            try {
                const response = await fetch(`${window.BACKEND_URL || ''}/api/auth/login`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    credentials: "include",
                    body: JSON.stringify({ email, password })
                });

                const data = await response.json();

                if (response.ok) {
                    showToast("Login successful! Redirecting...", "success");
                    localStorage.setItem("backuper_token", data.access_token);
                    localStorage.setItem("backuper_user", JSON.stringify(data.user));
                    
                    setTimeout(() => {
                        window.location.href = "/";
                    }, 1000);
                } else {
                    showToast(data.detail || "Incorrect email or password.", "error");
                }
            } catch (error) {
                console.error("Login error:", error);
                showToast("Network error. Please try again later.", "error");
            }
        });
    }

    // Form Submission: Registration
    if (signupForm) {
        signupForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            
            const name = document.getElementById("signup-name").value;
            const email = document.getElementById("signup-email").value;
            const password = document.getElementById("signup-password").value;
            const default_region = document.getElementById("signup-region").value;
            const default_storage_class = document.getElementById("signup-class").value;

            try {
                // Register user
                const response = await fetch(`${window.BACKEND_URL || ''}/api/auth/register`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        name,
                        email,
                        password,
                        default_region,
                        default_storage_class,
                        invite_token: currentInviteToken
                    })
                });

                const data = await response.json();

                if (response.ok) {
                    showToast("Account created successfully! Logging in...", "success");
                    
                    // Automatically log in the user after successful registration
                    const loginResponse = await fetch(`${window.BACKEND_URL || ''}/api/auth/login`, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify({ email, password })
                    });
                    
                    const loginData = await loginResponse.json();
                    
                    if (loginResponse.ok) {
                        localStorage.setItem("backuper_token", loginData.access_token);
                        localStorage.setItem("backuper_user", JSON.stringify(loginData.user));
                        setTimeout(() => {
                            window.location.href = "/";
                        }, 1200);
                    } else {
                        window.location.href = "/login";
                    }
                } else {
                    showToast(data.detail || "Registration failed. Please try again.", "error");
                }
            } catch (error) {
                console.error("Signup error:", error);
                showToast("Network error. Please try again later.", "error");
            }
        });
    }
});
