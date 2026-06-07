/* backend/static/js/main.js */

// Global State
const state = {
    user: null,
    selectedFile: null
};

// Token Storage Constants
const ACCESS_TOKEN_KEY = 'wastetrack_access';
const REFRESH_TOKEN_KEY = 'wastetrack_refresh';
const USER_INFO_KEY = 'wastetrack_user';

// JWT Token Management
function saveTokens(tokens) {
    if (tokens.access) localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
    if (tokens.refresh) localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
}

function getAccessToken() {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
}

function getRefreshToken() {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
}

function clearTokens() {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_INFO_KEY);
}

// Decode JWT to extract expiration timestamp
function parseJwt(token) {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));
        return JSON.parse(jsonPayload);
    } catch (e) {
        return null;
    }
}

function isTokenExpired(token) {
    if (!token) return true;
    const payload = parseJwt(token);
    if (!payload || !payload.exp) return true;
    
    // Add 10-second buffer to prevent edge cases
    const currentTime = Math.floor(Date.now() / 1000);
    return payload.exp < (currentTime + 10);
}

// Automatically refresh expired token
async function refreshAccessToken() {
    const refresh = getRefreshToken();
    if (!refresh || isTokenExpired(refresh)) {
        clearTokens();
        return null;
    }

    try {
        const response = await fetch('/api/v1/auth/refresh/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh: refresh })
        });

        if (response.ok) {
            const data = await response.json();
            // simplejwt refresh endpoint typically returns { access: "..." }
            saveTokens({ access: data.access });
            console.log("JWT Token refreshed successfully.");
            return data.access;
        } else {
            console.warn("Failed to refresh token. Session expired.");
            clearTokens();
            return null;
        }
    } catch (err) {
        console.error("Token refresh network error:", err);
        return null;
    }
}

// Retrieve a guaranteed valid access token
async function getValidToken() {
    let access = getAccessToken();
    if (!access) return null;

    if (isTokenExpired(access)) {
        access = await refreshAccessToken();
    }
    return access;
}

// Wrapper around native fetch to inject JWT and handle redirects
async function apiFetch(url, options = {}) {
    let token = await getValidToken();
    
    // Configure default headers
    options.headers = options.headers || {};
    if (token) {
        options.headers['Authorization'] = `Bearer ${token}`;
    }

    let response = await fetch(url, options);

    // If 401 Unauthorized, try one more time by forcing a refresh
    if (response.status === 401 && getRefreshToken()) {
        token = await refreshAccessToken();
        if (token) {
            options.headers['Authorization'] = `Bearer ${token}`;
            response = await fetch(url, options);
        } else {
            window.location.href = '/login/?msg=session_expired';
            return null;
        }
    }

    return response;
}

// Compute standard SHA-256 hash of a file client-side
async function calculateSHA256(file) {
    const arrayBuffer = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    return hashHex;
}

// Update authentication links in the navbar
async function updateNavbar() {
    const access = getAccessToken();
    const navAuth = document.getElementById('navbar-auth');
    const navMenu = document.getElementById('navbar-menu');
    if (!navAuth) return;

    if (access) {
        // Logged In navbar state
        let displayName = "Citizen";
        let ecoScore = 0;

        try {
            // Fetch profile data to update cache and get display name / scores
            const profileRes = await apiFetch('/api/v1/auth/profile/');
            if (profileRes && profileRes.ok) {
                const profile = await profileRes.json();
                displayName = profile.display_name || "Citizen";
                ecoScore = profile.eco_score || 0;
                localStorage.setItem(USER_INFO_KEY, JSON.stringify(profile));
            }
        } catch (e) {
            console.error("Failed to load user profile in nav:", e);
        }

        navAuth.innerHTML = `
            <div class="eco-badge">
                <i class="fas fa-leaf"></i>
                <span id="eco-score-val">${ecoScore} Points</span>
            </div>
            <a href="/profile/" class="navbar-link" id="nav-user-name" style="font-weight: 600; color: var(--primary);">${displayName}</a>
            <a href="#" id="nav-logout" class="btn-nav-login" style="margin-left: 8px;">Logout</a>
        `;

        // Bind logout click event
        document.getElementById('nav-logout').addEventListener('click', (e) => {
            e.preventDefault();
            clearTokens();
            window.location.href = '/login/?msg=logged_out';
        });

        // Ensure Profile history page link is accessible
        if (navMenu) {
            // Find or append Results page if not present
            if (!document.getElementById('nav-results')) {
                const resultsLi = document.createElement('li');
                resultsLi.innerHTML = `<a href="/profile/" class="navbar-link" id="nav-results">History</a>`;
                navMenu.appendChild(resultsLi);
            }
        }
    } else {
        // Logged Out navbar state
        navAuth.innerHTML = `
            <a href="/login/" class="btn-nav-login">Login</a>
            <a href="/register/" class="btn-nav-signup">Register</a>
        `;
        // Hide history if logged out
        const resLink = document.getElementById('nav-results');
        if (resLink) resLink.parentElement.remove();
    }
}


// Redirect helpers for page authorization protection
function protectPage() {
    const path = window.location.pathname;
    const access = getAccessToken();

    const protectedPaths = ['/', '/result/']; // result/<uuid>/ is covered
    const authPaths = ['/login/', '/register/'];

    const isProtected = protectedPaths.some(p => path === p || path.startsWith('/result/'));
    const isAuthPage = authPaths.some(p => path === p);

    if (isProtected && !access) {
        window.location.href = '/login/?msg=login_required';
    } else if (isAuthPage && access) {
        window.location.href = '/';
    }
}

// UI Alert display helper
function showAlert(containerId, message, type = 'danger') {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = `
        <div class="alert alert-${type}">
            <i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}"></i>
            <div>${message}</div>
        </div>
    `;
    container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Intercept registration form submission
async function setupRegistration() {
    const form = document.getElementById('register-form');
    if (!form) return;

    // Toggle Password Visibility
    const pwToggle = document.getElementById('toggle-register-password');
    const pwInput = document.getElementById('register-password');
    if (pwToggle && pwInput) {
        pwToggle.addEventListener('click', () => {
            const isPw = pwInput.type === 'password';
            pwInput.type = isPw ? 'text' : 'password';
            pwToggle.innerHTML = isPw ? '<i class="far fa-eye-slash"></i>' : '<i class="far fa-eye"></i>';
        });
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const alertContainer = 'register-alert-container';
        document.getElementById(alertContainer).innerHTML = '';

        const password = form.password.value;
        const email = form.email.value;
        const displayName = form.display_name.value;
        const phoneNumber = form.phone_number.value;
        const addressLine = form.address_line.value;
        const consent = form.consent.checked;

        if (password.length < 8) {
            showAlert(alertContainer, "Password must be at least 8 characters long.");
            return;
        }

        if (!consent) {
            showAlert(alertContainer, "You must consent to data processing.");
            return;
        }

        const payload = {
            email: email,
            password: password,
            role: 'citizen',
            profile: {
                display_name: displayName,
                phone_number: phoneNumber || null,
                address_line: addressLine || null,
                latitude: "0.000000",
                longitude: "0.000000",
                business_reg_no: null
            },
            consent: consent
        };

        try {
            const response = await fetch('/api/v1/auth/register/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (response.ok) {
                showAlert(alertContainer, "Registration successful! Redirecting to login...", "success");
                form.reset();
                setTimeout(() => {
                    window.location.href = '/login/?msg=registered';
                }, 2000);
            } else {
                // Parse and show validation errors
                let errorMsg = "Registration failed.";
                if (data.email) errorMsg = `Email: ${data.email.join(' ')}`;
                else if (data.password) errorMsg = `Password: ${data.password.join(' ')}`;
                else if (data.profile) {
                    if (data.profile.display_name) errorMsg = `Name: ${data.profile.display_name.join(' ')}`;
                    else if (data.profile.phone_number) errorMsg = `Phone: ${data.profile.phone_number.join(' ')}`;
                } else if (data.error) {
                    errorMsg = data.error;
                }
                showAlert(alertContainer, errorMsg);
            }
        } catch (err) {
            showAlert(alertContainer, "Server error during registration. Please try again.");
            console.error("Register error:", err);
        }
    });
}

// Intercept login form submission
async function setupLogin() {
    const form = document.getElementById('login-form');
    if (!form) return;

    // Show URL param messages
    const urlParams = new URLSearchParams(window.location.search);
    const msgType = urlParams.get('msg');
    const alertContainer = 'login-alert-container';
    
    if (msgType === 'login_required') {
        showAlert(alertContainer, "Please login to access this feature.", "warning");
    } else if (msgType === 'session_expired') {
        showAlert(alertContainer, "Your session expired. Please login again.", "warning");
    } else if (msgType === 'logged_out') {
        showAlert(alertContainer, "Logged out successfully.", "success");
    } else if (msgType === 'registered') {
        showAlert(alertContainer, "Account created! Please enter your credentials to login.", "success");
    }

    // Toggle Password Visibility
    const pwToggle = document.getElementById('toggle-login-password');
    const pwInput = document.getElementById('login-password');
    if (pwToggle && pwInput) {
        pwToggle.addEventListener('click', () => {
            const isPw = pwInput.type === 'password';
            pwInput.type = isPw ? 'text' : 'password';
            pwToggle.innerHTML = isPw ? '<i class="far fa-eye-slash"></i>' : '<i class="far fa-eye"></i>';
        });
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        document.getElementById(alertContainer).innerHTML = '';

        const email = form.email.value;
        const password = form.password.value;

        try {
            const response = await fetch('/api/v1/auth/login/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email, password: password })
            });

            const data = await response.json();

            if (response.ok) {
                // save tokens in localStorage
                saveTokens({ access: data.access, refresh: data.refresh });
                
                // Get profile details
                const profileRes = await apiFetch('/api/v1/auth/profile/');
                if (profileRes && profileRes.ok) {
                    const profile = await profileRes.json();
                    localStorage.setItem(USER_INFO_KEY, JSON.stringify(profile));
                }

                window.location.href = '/';
            } else {
                const errorMsg = data.detail || "Invalid email or password.";
                showAlert(alertContainer, errorMsg);
            }
        } catch (err) {
            showAlert(alertContainer, "Connection error. Please check your network.");
            console.error("Login error:", err);
        }
    });
}

// Home page Drag & Drop and submit logic
function setupUploadPage() {
    const zone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');
    const previewContainer = document.getElementById('preview-container');
    const previewImage = document.getElementById('preview-image');
    const clearPreviewBtn = document.getElementById('btn-clear-preview');
    const btnAnalyze = document.getElementById('btn-analyze');
    const overlay = document.getElementById('progress-overlay');

    if (!zone) return;

    // Open file picker on click
    zone.addEventListener('click', (e) => {
        if (e.target.closest('#btn-clear-preview') || e.target.closest('.preview-wrapper')) return;
        fileInput.click();
    });

    // File Input change event
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFileSelect(fileInput.files[0]);
        }
    });

    // Drag-and-drop events
    ['dragenter', 'dragover'].forEach(eventName => {
        zone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        zone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove('dragover');
        }, false);
    });

    zone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleFileSelect(files[0]);
        }
    }, false);

    // Clear file selection
    clearPreviewBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.value = '';
        state.selectedFile = null;
        previewContainer.style.display = 'none';
        previewImage.src = '';
        btnAnalyze.style.display = 'none';
        // Show upload elements
        zone.querySelector('.upload-icon').style.display = 'block';
        zone.querySelector('.upload-text').style.display = 'block';
        zone.querySelector('.upload-subtext').style.display = 'block';
        zone.querySelector('.btn-file-select').style.display = 'inline-block';
        zone.style.padding = '48px 24px';
    });

    function handleFileSelect(file) {
        if (!['image/jpeg', 'image/png'].includes(file.type)) {
            alert("Only JPEG and PNG file uploads are supported.");
            return;
        }

        state.selectedFile = file;

        // Preview File
        const reader = new FileReader();
        reader.onload = (e) => {
            previewImage.src = e.target.result;
            previewContainer.style.display = 'flex';
            btnAnalyze.style.display = 'flex';
            
            // Hide upload icons in box
            zone.querySelector('.upload-icon').style.display = 'none';
            zone.querySelector('.upload-text').style.display = 'none';
            zone.querySelector('.upload-subtext').style.display = 'none';
            zone.querySelector('.btn-file-select').style.display = 'none';
            zone.style.padding = '12px';
        };
        reader.readAsDataURL(file);
    }

    // Process Analysis
    btnAnalyze.addEventListener('click', async () => {
        if (!state.selectedFile) return;
        
        // Show progress overlay
        overlay.style.display = 'flex';
        resetProgressSteps();
        
        try {
            // STEP 1: Uploading - Request Signed Upload URL
            updateProgressStep('step-upload', 'active');
            const file = state.selectedFile;
            const sha256 = await calculateSHA256(file);
            
            const signedRes = await apiFetch('/api/v1/classification/signed-url/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_name: file.name,
                    file_size: file.size,
                    content_type: file.type
                })
            });

            if (!signedRes || !signedRes.ok) {
                const errData = await signedRes.json();
                throw new Error(errData.error || errData.content_type?.[0] || "Failed to retrieve signed URL.");
            }

            const signedData = await signedRes.json();
            const { signed_url, image_url, file_name } = signedData;

            // STEP 1: Perform the Upload (Direct GCS or simulated)
            if (signed_url.includes('storage.gcs.local')) {
                // Local Dev Simulation
                console.log("Simulating local storage upload...");
                await new Promise(resolve => setTimeout(resolve, 1200));
            } else {
                // Real GCS Upload
                const uploadRes = await fetch(signed_url, {
                    method: 'PUT',
                    headers: { 'Content-Type': file.type },
                    body: file
                });

                if (!uploadRes.ok) {
                    throw new Error("GCS Image placement upload failed.");
                }
            }
            updateProgressStep('step-upload', 'completed');

            // STEP 2: Submit Classification
            updateProgressStep('step-analyze', 'active');
            const submitRes = await apiFetch('/api/v1/classification/submit/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    image_url: image_url,
                    image_sha256: sha256
                })
            });

            if (!submitRes || !submitRes.ok) {
                const errData = await submitRes.json();
                throw new Error(errData.error || errData.image_sha256?.[0] || "Pipeline submission failed.");
            }

            const submitData = await submitRes.json();
            const itemId = submitData.id;

            // STEP 3: Poll status of Celery background pipeline (Analyzing + Safety Check)
            let classificationItem = submitData;
            const maxPollAttempts = 40;
            let attempts = 0;

            while (attempts < maxPollAttempts) {
                console.log(`Polling status attempt #${attempts + 1} for item ${itemId}`);
                
                // Fetch current status
                const statusRes = await apiFetch(`/api/v1/classification/status/${itemId}/`);
                if (!statusRes || !statusRes.ok) {
                    throw new Error("Failed to retrieve classification task status.");
                }
                
                classificationItem = await statusRes.json();
                const status = classificationItem.status;

                // Adjust progress indicators based on actual Celery worker status
                if (status === 'ANALYZING') {
                    // Stay on step analyze
                    updateProgressStep('step-analyze', 'active');
                } else if (status === 'PENDING_CONFIRMATION' || status === 'PENDING_CLARIFICATION' || status === 'CLASSIFIED') {
                    // Completed analysis, showing safety check
                    updateProgressStep('step-analyze', 'completed');
                    updateProgressStep('step-safety', 'completed');
                    updateProgressStep('step-results', 'completed');
                    
                    // Delay slightly to show final completion state
                    await new Promise(resolve => setTimeout(resolve, 800));
                    window.location.href = `/result/${itemId}/`;
                    return;
                } else if (status === 'FAILED') {
                    throw new Error(classificationItem.disposal_instructions || "AI processing pipeline failed.");
                }

                // Simulate transitions for safety check step visually as we poll
                if (attempts > 3 && status === 'ANALYZING') {
                    updateProgressStep('step-analyze', 'completed');
                    updateProgressStep('step-safety', 'active');
                }

                await new Promise(resolve => setTimeout(resolve, 1500));
                attempts++;
            }

            throw new Error("Classification task timed out. Please try again.");

        } catch (err) {
            console.error("Classification error:", err);
            // Hide progress modal
            overlay.style.display = 'none';
            // Show alert
            alert(`Analysis Error: ${err.message}`);
        }
    });

    function resetProgressSteps() {
        ['step-upload', 'step-analyze', 'step-safety', 'step-results'].forEach(id => {
            const step = document.getElementById(id);
            if (step) {
                step.className = 'progress-step';
                step.querySelector('.progress-step-icon').innerHTML = getStepNum(id);
            }
        });
    }

    function getStepNum(id) {
        if (id === 'step-upload') return '1';
        if (id === 'step-analyze') return '2';
        if (id === 'step-safety') return '3';
        return '4';
    }

    function updateProgressStep(stepId, stateClass) {
        const step = document.getElementById(stepId);
        if (!step) return;

        step.className = `progress-step ${stateClass}`;
        const icon = step.querySelector('.progress-step-icon');
        if (stateClass === 'completed') {
            icon.innerHTML = '<i class="fas fa-check"></i>';
        } else if (stateClass === 'active') {
            icon.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }
    }
}

// Results page data binding and action handlers
async function setupResultsPage() {
    const resultsContainer = document.getElementById('results-container');
    if (!resultsContainer) return;

    const itemId = resultsContainer.dataset.itemId;
    const alertContainer = 'result-alert-container';

    try {
        const response = await apiFetch(`/api/v1/classification/status/${itemId}/`);
        if (!response || !response.ok) {
            showAlert(alertContainer, "Could not fetch classification results. It may have been deleted.");
            return;
        }

        const data = await response.json();
        
        // Populate results elements
        document.getElementById('results-image').src = data.image_url;
        
        // Set category text and badge class
        const catText = data.predicted_category || "Unknown";
        const catBadge = document.getElementById('results-cat-badge');
        catBadge.innerText = catText;
        // Clean previous classes
        catBadge.className = 'badge';
        catBadge.classList.add(`badge-${catText.toLowerCase().replace(' ', '-')}`);
        
        // Confidence gauge
        const scoreVal = parseFloat(data.confidence_score || 0);
        const percent = Math.round(scoreVal * 100);
        const gauge = document.getElementById('results-gauge');
        gauge.style.setProperty('--percent', percent);
        gauge.innerText = `${percent}%`;

        // Disposal Instructions
        document.getElementById('results-disposal').innerText = data.disposal_instructions || "No custom instructions available.";

        // Upcycling Guides
        const upcyclingList = document.getElementById('results-upcycling');
        upcyclingList.innerHTML = '';
        const guides = data.upcycling_guides || [];
        if (guides.length === 0) {
            upcyclingList.innerHTML = `<li class="idea-item"><i class="fas fa-info-circle"></i> No custom reuse ideas generated.</li>`;
        } else {
            guides.forEach(guide => {
                const li = document.createElement('li');
                li.className = 'idea-item';
                li.innerHTML = `
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>
                    <span>${guide}</span>
                `;
                upcyclingList.appendChild(li);
            });
        }

        // Safety Assessment details
        const safetyBox = document.getElementById('safety-alert-box');
        const flagsContainer = document.getElementById('safety-flags');
        const safetyAssessment = data.safety_assessment;

        if (safetyAssessment) {
            const riskLvl = safetyAssessment.risk_level || 'SAFE';
            const riskScore = parseFloat(safetyAssessment.risk_score || 0);
            
            // Clean previous classes
            safetyBox.className = 'safety-alert-box';
            safetyBox.classList.add(`safety-${riskLvl.toLowerCase()}`);
            
            let iconHtml = '<i class="fas fa-check-circle"></i>';
            let titleText = 'Approved Safe';
            let descText = 'This waste item is certified clean and secure for reuse processing.';

            if (riskLvl === 'HIGH' || riskLvl === 'CRITICAL') {
                iconHtml = '<i class="fas fa-exclamation-triangle"></i>';
                titleText = `${riskLvl} Risk Alert`;
                descText = safetyAssessment.review_reason || 'Hazardous contaminants or toxic chemical elements detected. Refrain from direct upcycling.';
            } else if (riskLvl === 'MEDIUM' || riskLvl === 'LOW') {
                iconHtml = '<i class="fas fa-exclamation-circle"></i>';
                titleText = 'Caution Recommended';
                descText = safetyAssessment.review_reason || 'Low-level chemical components or manual checking required before reuse handling.';
            }

            document.getElementById('safety-alert-icon').innerHTML = iconHtml;
            document.getElementById('safety-alert-title').innerText = titleText;
            document.getElementById('safety-alert-text').innerText = descText;

            // Flags
            flagsContainer.innerHTML = '';
            const flags = safetyAssessment.safety_flags || [];
            if (flags.length === 0) {
                flagsContainer.innerHTML = `<span class="safety-flag-badge"><i class="fas fa-shield-alt"></i> No Flags</span>`;
            } else {
                flags.forEach(flag => {
                    const badge = document.createElement('span');
                    badge.className = 'safety-flag-badge';
                    badge.innerHTML = `<i class="fas fa-flag" style="color: var(--danger);"></i> ${flag}`;
                    flagsContainer.appendChild(badge);
                });
            }
        } else {
            // Safety assessment not available
            safetyBox.className = 'safety-alert-box safety-low';
            document.getElementById('safety-alert-icon').innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            document.getElementById('safety-alert-title').innerText = 'Evaluating Safety...';
            document.getElementById('safety-alert-text').innerText = 'The safety engine is analyzing regulatory criteria for this waste type.';
        }

        // Set default confirmed select value to the predicted category
        const confirmSelect = document.getElementById('confirmed-category-select');
        if (confirmSelect && data.predicted_category) {
            confirmSelect.value = data.predicted_category;
        }

        // Setup Category Confirmation Form submit
        const confirmForm = document.getElementById('confirm-category-form');
        if (confirmForm) {
            confirmForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const selectedCat = confirmSelect.value;
                
                try {
                    const confirmRes = await apiFetch('/api/v1/classification/confirm/', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            waste_item_id: itemId,
                            confirmed_category: selectedCat
                        })
                    });

                    if (confirmRes && confirmRes.ok) {
                        showAlert('confirm-alert-container', "Classification category confirmed successfully!", "success");
                        // Refresh details
                        setTimeout(() => {
                            window.location.reload();
                        }, 1200);
                    } else {
                        const err = await confirmRes.json();
                        showAlert('confirm-alert-container', err.error || "Failed to confirm classification.");
                    }
                } catch (err) {
                    showAlert('confirm-alert-container', "Connection error. Please try again.");
                }
            });
        }

    } catch (err) {
        showAlert(alertContainer, "Error loading classification result.");
        console.error("Results load error:", err);
    }
}

// Page initialization on DOM Load
document.addEventListener('DOMContentLoaded', () => {
    protectPage();
    updateNavbar();
    
    // Bind features based on active templates
    setupLogin();
    setupRegistration();
    setupUploadPage();
    setupResultsPage();
    setupProfilePage();
});

// Profile page data binding
async function setupProfilePage() {
    const profileContainer = document.getElementById('profile-page-container');
    if (!profileContainer) return;

    const alertContainer = 'profile-alert-container';
    const historyBody = document.getElementById('history-list-body');

    try {
        // 1. Fetch Profile info from API
        const profileRes = await apiFetch('/api/v1/auth/profile/');
        if (!profileRes || !profileRes.ok) {
            showAlert(alertContainer, "Could not fetch user profile details.");
            return;
        }

        const profile = await profileRes.json();

        // 2. Populate Profile View elements
        document.getElementById('profile-display-name').innerText = profile.display_name || "Citizen";
        document.getElementById('profile-email').innerText = profile.email || "...";
        document.getElementById('profile-phone').innerText = profile.phone_number || "Not Provided";
        document.getElementById('profile-address').innerText = profile.address_line || "Not Provided";
        document.getElementById('profile-eco-score').innerText = `${profile.eco_score || 0} Points`;
        document.getElementById('profile-reputation-score').innerText = `${parseFloat(profile.reputation_score || 5).toFixed(2)} / 5.00`;

        const roleBadge = document.getElementById('profile-user-role');
        if (profile.role) {
            roleBadge.innerText = profile.role;
            roleBadge.className = 'badge badge-organic';
        }

        const verificationBadge = document.getElementById('profile-verification');
        if (profile.is_verified) {
            verificationBadge.innerText = "Verified";
            verificationBadge.className = "badge badge-glass";
            verificationBadge.style.backgroundColor = "var(--success-light)";
            verificationBadge.style.color = "var(--success)";
        } else {
            verificationBadge.innerText = "Not Verified";
            verificationBadge.className = "badge badge-mixed-waste";
        }

        // 3. Fetch Paginated History list
        const historyRes = await apiFetch('/api/v1/classification/');
        if (!historyRes || !historyRes.ok) {
            historyBody.innerHTML = `
                <tr>
                    <td colspan="6" style="padding: 32px; text-align: center; color: var(--danger);">
                        <i class="fas fa-exclamation-triangle"></i> Failed to retrieve history data.
                    </td>
                </tr>
            `;
            return;
        }

        const historyData = await historyRes.json();
        const items = historyData.results || [];

        if (items.length === 0) {
            historyBody.innerHTML = `
                <tr>
                    <td colspan="6" style="padding: 48px; text-align: center; color: var(--text-muted);">
                        <div style="font-size: 2.5rem; margin-bottom: 12px; opacity: 0.5;"><i class="fas fa-trash-restore-alt"></i></div>
                        <p style="font-weight: 500; margin-bottom: 8px;">No waste items classified yet</p>
                        <a href="/#upload-card-section" class="btn-view-details" style="font-size: 0.85rem; padding: 6px 16px;">Classify Your First Item</a>
                    </td>
                </tr>
            `;
            return;
        }

        historyBody.innerHTML = '';
        items.forEach(item => {
            const tr = document.createElement('tr');
            
            // Image thumbnail
            const thumbUrl = item.image_url || '';
            const thumbTd = `
                <td style="padding: 12px 8px;">
                    <img class="history-thumb" src="${thumbUrl}" alt="Thumbnail" onerror="this.src='https://placehold.co/60x45?text=No+Img'">
                </td>
            `;

            // Category badge
            const cat = item.predicted_category || "Mixed Waste";
            const catBadgeClass = `badge-${cat.toLowerCase().replace(' ', '-')}`;
            const categoryTd = `
                <td style="padding: 12px 8px;">
                    <span class="badge ${catBadgeClass}">${cat}</span>
                </td>
            `;

            // Confidence score percentage
            let confPercent = "N/A";
            if (item.confidence_score) {
                confPercent = `${Math.round(parseFloat(item.confidence_score) * 100)}%`;
            }
            const confTd = `<td style="padding: 12px 8px; font-weight: 600;">${confPercent}</td>`;

            // Safety status
            let safetyText = "Pending";
            let safetyBadgeClass = "badge-mixed-waste";
            
            if (item.safety_assessment) {
                const risk = item.safety_assessment.risk_level || 'SAFE';
                if (risk === 'SAFE') {
                    safetyText = "Approved";
                    safetyBadgeClass = "badge-organic";
                } else if (risk === 'HIGH' || risk === 'CRITICAL') {
                    safetyText = "Blocked";
                    safetyBadgeClass = "badge-hazardous";
                } else {
                    safetyText = "Caution";
                    safetyBadgeClass = "badge-paper";
                }
            } else if (item.status === 'FAILED') {
                safetyText = "Failed";
                safetyBadgeClass = "badge-hazardous";
            }
            const safetyTd = `
                <td style="padding: 12px 8px;">
                    <span class="badge ${safetyBadgeClass}">${safetyText}</span>
                </td>
            `;

            // Formatted creation date
            const dateObj = new Date(item.created_at);
            const dateStr = dateObj.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) + 
                            ' ' + dateObj.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
            const dateTd = `<td style="padding: 12px 8px; font-size: 0.85rem; color: var(--text-secondary);">${dateStr}</td>`;

            // Action details link
            const actionTd = `
                <td style="padding: 12px 8px; text-align: right;">
                    <a href="/result/${item.id}/" class="btn-view-details">Details</a>
                </td>
            `;

            tr.innerHTML = thumbTd + categoryTd + confTd + safetyTd + dateTd + actionTd;
            historyBody.appendChild(tr);
        });

    } catch (err) {
        showAlert(alertContainer, "Failed to load profile parameters.");
        console.error("Profile page load error:", err);
    }
}

