/**
 * HEALTHCARE CRM - MAIN JAVASCRIPT FILE
 * 
 * This file contains core JavaScript functionality for the Healthcare CRM application.
 * It handles DOM interactions, event listeners, and basic application logic.
 * 
 * Modules:
 * 1. DOM Elements Cache
 * 2. Initialization Functions
 * 3. Navbar & User Menu
 * 4. Sidebar Navigation
 * 5. Form Handling
 * 6. Utility Functions
 * 7. Event Listeners
 */

// ============================================
// 1. DOM ELEMENTS CACHE
// ============================================

// Navbar Elements
const userMenuBtn = document.getElementById('user-menu-btn');
const userDropdown = document.getElementById('user-dropdown');

// Sidebar Elements
const sidebar = document.getElementById('sidebar');
const sidebarToggleBtn = document.getElementById('sidebar-toggle-btn');
const menuLinks = document.querySelectorAll('.menu-link');

// Main Content Elements
const mainContent = document.getElementById('main-content');
const pageTitle = document.querySelector('.page-title');
const pageSubtitle = document.querySelector('.page-subtitle');

// Form Elements
const loginForm = document.getElementById('login-form');
const emailInput = document.getElementById('email');
const passwordInput = document.getElementById('password');
const rememberMeCheckbox = document.getElementById('remember-me');
const loginBtn = document.getElementById('login-btn');
const togglePasswordBtn = document.getElementById('toggle-password');
const formErrorAlert = document.getElementById('form-error-alert');
const alertText = document.getElementById('alert-text');
const emailError = document.getElementById('email-error');
const passwordError = document.getElementById('password-error');

// ============================================
// 2. INITIALIZATION FUNCTIONS
// ============================================

/**
 * Initialize the application
 * Called when DOM is fully loaded
 */
function initializeApp() {
    // Check if we're on the login page
    if (loginForm) {
        initializeLoginPage();
    } else {
        // Regular page initialization
        setupEventListeners();
        setActiveMenuItem();
    }
    
    appLog('Application initialized successfully');
}

/**
 * Initialize login page specific features
 */
function initializeLoginPage() {
    appLog('Initializing Login Page');
    
    // Setup login form listeners
    if (loginForm) {
        loginForm.addEventListener('submit', handleLoginSubmit);
    }
    
    // Password visibility toggle
    if (togglePasswordBtn) {
        togglePasswordBtn.addEventListener('click', togglePasswordVisibility);
    }
    
    // Clear error messages when user starts typing
    if (emailInput) {
        emailInput.addEventListener('input', () => clearError('email'));
    }
    
    if (passwordInput) {
        passwordInput.addEventListener('input', () => clearError('password'));
    }
    
    // Check if user was remembered
    checkRememberedUser();
}

/**
 * Setup all event listeners for the application
 */
function setupEventListeners() {
    // Navbar - User Menu
    if (userMenuBtn) {
        userMenuBtn.addEventListener('click', toggleUserDropdown);
    }
    
    // Sidebar - Toggle Button
    if (sidebarToggleBtn) {
        sidebarToggleBtn.addEventListener('click', toggleSidebar);
    }
    
    // Sidebar - Menu Links
    menuLinks.forEach(link => {
        link.addEventListener('click', handleMenuLinkClick);
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', closeDropdownOnOutsideClick);
}

// ============================================
// 3. NAVBAR & USER MENU FUNCTIONS
// ============================================

/**
 * Toggle the visibility of the user dropdown menu
 */
function toggleUserDropdown(event) {
    event.stopPropagation();
    
    if (userDropdown) {
        userDropdown.classList.toggle('hidden');
    }
}

/**
 * Close user dropdown when clicking outside of it
 */
function closeDropdownOnOutsideClick(event) {
    // Close user dropdown
    if (userDropdown && 
        !userDropdown.contains(event.target) && 
        !userMenuBtn.contains(event.target)) {
        userDropdown.classList.add('hidden');
    }
    
    // Close sidebar when clicking outside (on mobile)
    if (window.innerWidth <= 768 && sidebar &&
        !sidebar.contains(event.target) && 
        !sidebarToggleBtn.contains(event.target) &&
        sidebar.classList.contains('active')) {
        closeSidebar();
    }
}

// ============================================
// 4. SIDEBAR NAVIGATION
// ============================================

/**
 * Toggle sidebar visibility on mobile devices
 */
function toggleSidebar() {
    if (sidebar) {
        sidebar.classList.toggle('active');
        appLog('Sidebar toggled');
    }
}

/**
 * Close sidebar
 */
function closeSidebar() {
    if (sidebar) {
        sidebar.classList.remove('active');
    }
}

/**
 * Open sidebar
 */
function openSidebar() {
    if (sidebar) {
        sidebar.classList.add('active');
    }
}

/**
 * Set the active menu item based on current page
 */
function setActiveMenuItem() {
    // Get current page filename
    const currentPage = window.location.pathname.split('/').pop() || 'index.html';
    
    // Remove active class from all menu links
    menuLinks.forEach(link => {
        link.classList.remove('active');
    });
    
    // Add active class to matching menu link
    menuLinks.forEach(link => {
        if (link.getAttribute('href').includes(currentPage)) {
            link.classList.add('active');
        }
    });
}

/**
 * Handle menu link clicks
 */
function handleMenuLinkClick(event) {
    // Remove active class from all links
    menuLinks.forEach(link => {
        link.classList.remove('active');
    });
    
    // Add active class to clicked link
    event.currentTarget.classList.add('active');
    
    // Close sidebar on mobile after navigation
    if (window.innerWidth <= 768) {
        closeSidebar();
    }
    
    appLog('Navigating to:', event.currentTarget.getAttribute('href'));
}

// ============================================
// 5. LOGIN FORM VALIDATION & HANDLING
// ============================================

/**
 * Toggle password visibility
 */
function togglePasswordVisibility() {
    if (!passwordInput) return;
    
    const isPassword = passwordInput.type === 'password';
    passwordInput.type = isPassword ? 'text' : 'password';
    
    // Update button emoji
    togglePasswordBtn.textContent = isPassword ? '🙈' : '👁️';
}

/**
 * Validate email format
 * @param {string} email - Email to validate
 * @returns {boolean} True if valid email format
 */
function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

/**
 * Validate login form
 * @returns {boolean} True if form is valid
 */
function validateLoginForm() {
    let isValid = true;
    
    // Clear previous errors
    clearFormErrors();
    
    // Validate email
    if (!emailInput.value.trim()) {
        showFieldError('email', 'Email address is required');
        isValid = false;
    } else if (!isValidEmail(emailInput.value)) {
        showFieldError('email', 'Please enter a valid email address');
        isValid = false;
    }
    
    // Validate password
    if (!passwordInput.value.trim()) {
        showFieldError('password', 'Password is required');
        isValid = false;
    } else if (passwordInput.value.length < 6) {
        showFieldError('password', 'Password must be at least 6 characters');
        isValid = false;
    }
    
    return isValid;
}

/**
 * Show error message for a specific field
 * @param {string} fieldName - Name of the field ('email' or 'password')
 * @param {string} message - Error message to display
 */
function showFieldError(fieldName, message) {
    const errorElement = document.getElementById(`${fieldName}-error`);
    if (errorElement) {
        errorElement.textContent = message;
        errorElement.classList.add('show');
    }
}

/**
 * Clear error message for a specific field
 * @param {string} fieldName - Name of the field
 */
function clearError(fieldName) {
    const errorElement = document.getElementById(`${fieldName}-error`);
    if (errorElement) {
        errorElement.textContent = '';
        errorElement.classList.remove('show');
    }
}

/**
 * Clear all form errors
 */
function clearFormErrors() {
    if (emailError) {
        emailError.textContent = '';
        emailError.classList.remove('show');
    }
    if (passwordError) {
        passwordError.textContent = '';
        passwordError.classList.remove('show');
    }
    hideFormAlert();
}

/**
 * Show form alert
 * @param {string} message - Alert message
 */
function showFormAlert(message) {
    if (formErrorAlert && alertText) {
        alertText.textContent = message;
        formErrorAlert.classList.add('show');
    }
}

/**
 * Hide form alert
 */
function hideFormAlert() {
    if (formErrorAlert) {
        formErrorAlert.classList.remove('show');
    }
}

// ============================================
// 5. LOGIN FORM VALIDATION & HANDLING
// ============================================

/**
 * Handle login form submission
 * @param {Event} event - Form submit event
 */
function handleLoginSubmit(event) {
    event.preventDefault();
    
    // Validate form
    if (!validateLoginForm()) {
        showFormAlert('Please fix the errors above and try again');
        return;
    }
    
    // Get form data
    const email = emailInput.value.trim();
    const password = passwordInput.value;
    const rememberMe = rememberMeCheckbox.checked;
    
    // Log attempt
    appLog(`Login attempt for: ${email}`, 'info');
    
    // Save remembered email if checkbox is checked
    if (rememberMe) {
        localStorage.setItem('rememberedEmail', email);
    } else {
        localStorage.removeItem('rememberedEmail');
    }
    
    // Show loading state
    showLoadingState(true);
    
    // Simulate API call delay (In real app, this would be an actual API request)
    setTimeout(() => {
        // Simulate successful login
        hideFormAlert();
        
        appLog('Login successful! Redirecting to dashboard...', 'info');
        
        // Reset form
        loginForm.reset();
        passwordInput.type = 'password';
        togglePasswordBtn.textContent = '👁️';
        
        // Hide loading state
        showLoadingState(false);
        
        // Redirect to dashboard
        window.location.href = 'dashboard.html';
    }, 1500);
}

/**
 * Show/hide loading state on login button
 * @param {boolean} isLoading - True to show loading, false to hide
 */
function showLoadingState(isLoading) {
    if (!loginBtn) return;
    
    if (isLoading) {
        loginBtn.disabled = true;
        const btnLoader = document.getElementById('btn-loader');
        if (btnLoader) {
            btnLoader.classList.add('show');
        }
    } else {
        loginBtn.disabled = false;
        const btnLoader = document.getElementById('btn-loader');
        if (btnLoader) {
            btnLoader.classList.remove('show');
        }
    }
}

/**
 * Check if user was previously remembered and pre-fill email
 */
function checkRememberedUser() {
    const rememberedEmail = localStorage.getItem('rememberedEmail');
    if (rememberedEmail && emailInput) {
        emailInput.value = rememberedEmail;
        if (rememberMeCheckbox) {
            rememberMeCheckbox.checked = true;
        }
    }
}

// ============================================
// 6. UTILITY FUNCTIONS
// ============================================

/**
 * Log a message with application context
 * @param {string} message - Message to log
 * @param {string} level - Log level: 'info', 'warn', 'error'
 */
function appLog(message, level = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    const prefix = `[Healthcare CRM - ${timestamp}]`;
    
    switch(level) {
        case 'warn':
            console.warn(prefix, message);
            break;
        case 'error':
            console.error(prefix, message);
            break;
        default:
            console.log(prefix, message);
    }
}

// ============================================
// 7. EVENT LISTENERS & DOM READY
// ============================================

/**
 * Initialize application when DOM is ready
 */
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}

// Log application load status
window.addEventListener('load', () => {
    appLog('All resources loaded successfully');
});

// Log page visibility changes (for debugging)
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        appLog('Application hidden');
    } else {
        appLog('Application visible');
    }
});

// Handle window resize for responsive design
window.addEventListener('resize', () => {
    // Close sidebar when resizing to desktop view
    if (window.innerWidth > 768) {
        closeSidebar();
    }
});

// Handle keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Escape key closes sidebar and dropdown
    if (e.key === 'Escape') {
        closeSidebar();
        if (userDropdown) {
            userDropdown.classList.add('hidden');
        }
        appLog('Escape key pressed - closing menus');
    }
});

// ============================================
// 8. DASHBOARD INTERACTIONS
// ============================================

/**
 * Initialize dashboard interactions
 */
function initializeDashboard() {
    // Add click handlers to stat cards
    const statCards = document.querySelectorAll('.stat-card');
    statCards.forEach(card => {
        card.addEventListener('click', handleStatCardClick);
    });
    
    // Add click handlers to alert items
    const alertItems = document.querySelectorAll('.alert-item');
    alertItems.forEach(item => {
        item.addEventListener('click', handleAlertClick);
    });
    
    // Add click handlers to activity items
    const activityItems = document.querySelectorAll('.activity-item');
    activityItems.forEach(item => {
        item.addEventListener('click', handleActivityClick);
    });
    
    // Add hover effects to chart bars
    const bars = document.querySelectorAll('.bar');
    bars.forEach(bar => {
        bar.addEventListener('mouseenter', handleBarHover);
        bar.addEventListener('mouseleave', handleBarLeave);
    });
    
    appLog('Dashboard interactions initialized');
}

/**
 * Handle stat card click
 */
function handleStatCardClick(e) {
    const card = e.currentTarget;
    const label = card.querySelector('.stat-label').textContent;
    const number = card.querySelector('.stat-number').textContent;
    
    appLog(`Clicked: ${label} - ${number}`);
    
    // Add visual feedback
    card.style.transform = 'scale(1.02)';
    setTimeout(() => {
        card.style.transform = '';
    }, 200);
    
    // In a real app, this would navigate or show detailed view
    // window.location.href = getPageForStat(label);
}

/**
 * Handle alert item click
 */
function handleAlertClick(e) {
    const alertItem = e.currentTarget;
    const alertText = alertItem.querySelector('.alert-text').textContent;
    const badge = alertItem.querySelector('.alert-badge').textContent;
    
    appLog(`Alert clicked: ${alertText} (${badge})`);
    
    // Add visual feedback
    alertItem.style.transform = 'translateX(5px)';
    setTimeout(() => {
        alertItem.style.transform = '';
    }, 200);
    
    // In a real app, this would open a detail view or perform an action
}

/**
 * Handle activity item click
 */
function handleActivityClick(e) {
    const activityItem = e.currentTarget;
    const activityText = activityItem.querySelector('.activity-text').textContent;
    
    appLog(`Activity viewed: ${activityText}`);
    
    // Add visual feedback
    activityItem.style.background = 'rgba(52, 152, 219, 0.05)';
    setTimeout(() => {
        activityItem.style.background = '';
    }, 300);
}

/**
 * Handle bar chart hover
 */
function handleBarHover(e) {
    const bar = e.currentTarget;
    const group = bar.closest('.bar-group');
    const value = group.querySelector('.bar-value');
    
    // Show tooltip or highlight
    if (value) {
        value.style.opacity = '1';
        value.style.fontWeight = '700';
    }
}

/**
 * Handle bar chart leave
 */
function handleBarLeave(e) {
    const bar = e.currentTarget;
    const group = bar.closest('.bar-group');
    const value = group.querySelector('.bar-value');
    
    if (value) {
        value.style.opacity = '0.8';
    }
}

/**
 * Get page/URL for stat navigation
 */
function getPageForStat(statLabel) {
    const statMap = {
        'Total Patients': '#patients',
        'Total Doctors': '#doctors',
        'Today\'s Visits': '#visits',
        'Pending Follow-ups': '#follow-ups'
    };
    return statMap[statLabel] || '#';
}

/**
 * Check if we're on dashboard page
 */
function isDashboardPage() {
    return window.location.pathname.includes('dashboard.html') || 
           window.location.pathname === '/templates/dashboard.html';
}

// Initialize dashboard when on dashboard page
if (isDashboardPage()) {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeDashboard);
    } else {
        initializeDashboard();
    }
}

/* ============================================
   9. MANAGEMENT PAGES - DOCTORS & PATIENTS JS
   UI-only: dummy data + modal, table rendering, search & filters
   ============================================ */

// ============================================
// 9. MANAGEMENT DATA & FUNCTIONS
// ============================================

/**
 * DUMMY DATA ARRAYS - Healthcare Management Records
 * 
 * In a real application, this data would come from a backend API/database.
 * For this CRM, we use frontend arrays with JavaScript filtering/sorting.
 */

// Dummy data for doctors
const doctorsData = [
    { id: 1, name: 'Dr. Alice Smith', specialization: 'General', availability: 'Mon-Fri 9:00-17:00', phone: '555-1234', status: 'active' },
    { id: 2, name: 'Dr. Brian Johnson', specialization: 'Dental', availability: 'Tue-Thu 10:00-16:00', phone: '555-5678', status: 'active' },
    { id: 3, name: 'Dr. Cathy Williams', specialization: 'Eye', availability: 'Mon,Wed,Fri 9:00-14:00', phone: '555-9012', status: 'inactive' }
];

// Dummy data for patients - UPDATED with problem/issue, assigned doctor, and last visit
const patientsData = [
    { id: 1, name: 'John Doe', problem: 'Skin', assignedDoctor: 'Dr. Alice Smith', lastVisit: 'Jan 28, 2025', status: 'active' },
    { id: 2, name: 'Mary Lane', problem: 'Dental', assignedDoctor: 'Dr. Brian Johnson', lastVisit: 'Jan 25, 2025', status: 'referred' },
    { id: 3, name: 'Paul Adams', problem: 'Eye', assignedDoctor: 'Dr. Cathy Williams', lastVisit: 'Jan 20, 2025', status: 'follow-up' }
];

/**
 * VISIT DATA - Records of patient visits and referral workflow
 * 
 * Visit Status Explanation for College Viva:
 * - "Resolved": Doctor completed treatment, patient discharged
 * - "Follow-up": Patient needs to return for follow-up appointment
 * - "Referred": Patient referred to specialist (e.g., general doctor → dermatologist)
 */
const visitsData = [
    { 
        id: 1, 
        patientName: 'John Doe', 
        doctorName: 'Dr. Alice Smith', 
        visitDate: 'Jan 28, 2025', 
        issue: 'Skin rash', 
        status: 'referred',  // Needs specialist for skin condition
        notes: 'Referred to Dermatology - possible allergic reaction'
    },
    { 
        id: 2, 
        patientName: 'Mary Lane', 
        doctorName: 'Dr. Brian Johnson', 
        visitDate: 'Jan 25, 2025', 
        issue: 'Tooth pain', 
        status: 'resolved',  // Successfully treated
        notes: 'Root canal completed successfully'
    },
    { 
        id: 3, 
        patientName: 'Paul Adams', 
        doctorName: 'Dr. Cathy Williams', 
        visitDate: 'Jan 20, 2025', 
        issue: 'Blurred vision', 
        status: 'follow-up',  // Needs follow-up appointment
        notes: 'New glasses prescribed, follow-up in 1 month'
    }
];

function isDoctorsPage() {
    return window.location.pathname.includes('doctors.html') || window.location.pathname === '/templates/doctors.html';
}

function isPatientsPage() {
    return window.location.pathname.includes('patients.html') || window.location.pathname === '/templates/patients.html';
}

function isVisitsPage() {
    return window.location.pathname.includes('visits.html') || window.location.pathname === '/templates/visits.html';
}

/* DOCTORS: Render table rows */
function renderDoctorsTable() {
    const tbody = document.querySelector('#doctors-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    doctorsData.forEach(doc => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${doc.name}</td>
            <td>${doc.specialization}</td>
            <td>${doc.availability}</td>
            <td><span class="status-badge ${doc.status === 'active' ? 'status-active' : 'status-inactive'}">${doc.status}</span></td>
            <td class="action-links">
                <button class="btn-link" data-action="view" data-id="${doc.id}">View</button>
                <button class="btn-link" data-action="edit" data-id="${doc.id}">Edit</button>
                <button class="btn-link" data-action="delete" data-id="${doc.id}">Delete</button>
            </td>
        `;
        // Row hover visible via CSS
        tbody.appendChild(tr);
    });

    // Attach action handlers
    tbody.querySelectorAll('.btn-link').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const action = btn.getAttribute('data-action');
            const id = Number(btn.getAttribute('data-id'));
            handleDoctorAction(action, id);
        });
    });
}

function handleDoctorAction(action, id) {
    const doctor = doctorsData.find(d => d.id === id);
    if (!doctor) return;
    appLog(`Doctor action: ${action} -> ${doctor.name}`);
    if (action === 'edit') {
        openDoctorModal('edit', doctor);
    } else if (action === 'view') {
        // UI-only: show simple alert
        alert(`${doctor.name}\nSpecialization: ${doctor.specialization}\nAvailability: ${doctor.availability}`);
    } else if (action === 'delete') {
        // UI-only: confirm then remove from array and re-render
        if (confirm(`Delete ${doctor.name}? This is a UI-only action.`)) {
            const idx = doctorsData.findIndex(d => d.id === id);
            if (idx >= 0) doctorsData.splice(idx, 1);
            renderDoctorsTable();
        }
    }
}

/* DOCTORS: Modal behavior */
function openDoctorModal(mode = 'add', doctor = null) {
    const overlay = document.getElementById('doctor-modal');
    if (!overlay) return;
    overlay.classList.add('active');
    document.getElementById('doctor-modal-title').textContent = mode === 'edit' ? 'Edit Doctor' : 'Add Doctor';

    // Populate fields for edit
    if (doctor) {
        document.getElementById('doc-name').value = doctor.name || '';
        document.getElementById('doc-specialization').value = doctor.specialization || 'General';
        document.getElementById('doc-phone').value = doctor.phone || '';
        document.getElementById('doc-availability').value = doctor.availability || '';
        document.getElementById('doc-status').value = doctor.status || 'active';
        overlay.setAttribute('data-edit-id', doctor.id);
    } else {
        document.getElementById('doctor-form').reset();
        overlay.removeAttribute('data-edit-id');
    }
}

function closeDoctorModal() {
    const overlay = document.getElementById('doctor-modal');
    if (!overlay) return;
    overlay.classList.remove('active');
}

function saveDoctorFromModal(event) {
    event.preventDefault();
    const overlay = document.getElementById('doctor-modal');
    const editId = overlay.getAttribute('data-edit-id');
    const name = document.getElementById('doc-name').value.trim();
    const specialization = document.getElementById('doc-specialization').value;
    const phone = document.getElementById('doc-phone').value.trim();
    const availability = document.getElementById('doc-availability').value.trim();
    const status = document.getElementById('doc-status').value;

    if (!name) {
        alert('Please enter a doctor name');
        return;
    }

    if (editId) {
        // Update existing
        const d = doctorsData.find(x => x.id === Number(editId));
        if (d) {
            d.name = name;
            d.specialization = specialization;
            d.phone = phone;
            d.availability = availability;
            d.status = status;
        }
    } else {
        // Add new (UI-only)
        const newId = doctorsData.length ? Math.max(...doctorsData.map(x => x.id)) + 1 : 1;
        doctorsData.push({ id: newId, name, specialization, phone, availability, status });
    }

    closeDoctorModal();
    renderDoctorsTable();
}

/* PATIENTS: Render table rows */
function renderPatientsTable(filter = 'all', search = '') {
    const tbody = document.querySelector('#patients-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    const normalizedSearch = search.trim().toLowerCase();
    patientsData
        .filter(p => filter === 'all' ? true : p.category === filter)
        .filter(p => {
            if (!normalizedSearch) return true;
            return p.name.toLowerCase().includes(normalizedSearch) || (p.phone && p.phone.includes(normalizedSearch));
        })
        .forEach(p => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${p.name}</td>
                <td>${p.phone || ''}</td>
                <td><span class="status-badge">${p.category}</span></td>
                <td><span class="status-badge ${p.status === 'active' ? 'status-active' : 'status-inactive'}">${p.status}</span></td>
                <td class="action-links">
                    <button class="btn-link" data-action="view" data-id="${p.id}">View Profile</button>
                    <button class="btn-link" data-action="edit" data-id="${p.id}">Edit</button>
                    <button class="btn-link" data-action="delete" data-id="${p.id}">Delete</button>
                </td>
            `;
            tbody.appendChild(tr);
        });

    // Attach action handlers
    tbody.querySelectorAll('.btn-link').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const action = btn.getAttribute('data-action');
            const id = Number(btn.getAttribute('data-id'));
            handlePatientAction(action, id);
        });
    });
}

function handlePatientAction(action, id) {
    const pat = patientsData.find(p => p.id === id);
    if (!pat) return;
    appLog(`Patient action: ${action} -> ${pat.name}`);
    if (action === 'edit') {
        openPatientModal('edit', pat);
    } else if (action === 'view') {
        alert(`${pat.name}\nPhone: ${pat.phone || 'N/A'}\nCategory: ${pat.category}`);
    } else if (action === 'delete') {
        if (confirm(`Delete ${pat.name}? This is a UI-only action.`)) {
            const idx = patientsData.findIndex(x => x.id === id);
            if (idx >= 0) patientsData.splice(idx, 1);
            renderPatientsTable();
        }
    }
}

/* PATIENTS: Modal behavior */
function openPatientModal(mode = 'add', patient = null) {
    const overlay = document.getElementById('patient-modal');
    if (!overlay) return;
    overlay.classList.add('active');
    document.getElementById('patient-modal-title').textContent = mode === 'edit' ? 'Edit Patient' : 'Add Patient';

    if (patient) {
        document.getElementById('pat-name').value = patient.name || '';
        document.getElementById('pat-age').value = patient.age || '';
        document.getElementById('pat-gender').value = patient.gender || 'Female';
        document.getElementById('pat-phone').value = patient.phone || '';
        document.getElementById('pat-email').value = patient.email || '';
        document.getElementById('pat-category').value = patient.category || 'new';
        document.getElementById('pat-status').value = patient.status || 'active';
        overlay.setAttribute('data-edit-id', patient.id);
    } else {
        document.getElementById('patient-form').reset();
        overlay.removeAttribute('data-edit-id');
    }
}

function closePatientModal() {
    const overlay = document.getElementById('patient-modal');
    if (!overlay) return;
    overlay.classList.remove('active');
}

function savePatientFromModal(event) {
    event.preventDefault();
    const overlay = document.getElementById('patient-modal');
    const editId = overlay.getAttribute('data-edit-id');
    const name = document.getElementById('pat-name').value.trim();
    const age = Number(document.getElementById('pat-age').value) || null;
    const gender = document.getElementById('pat-gender').value;
    const phone = document.getElementById('pat-phone').value.trim();
    const email = document.getElementById('pat-email').value.trim();
    const category = document.getElementById('pat-category').value;
    const status = document.getElementById('pat-status').value;

    if (!name) { alert('Please enter patient name'); return; }

    if (editId) {
        const p = patientsData.find(x => x.id === Number(editId));
        if (p) {
            p.name = name; p.age = age; p.gender = gender; p.phone = phone; p.email = email; p.category = category; p.status = status;
        }
    } else {
        const newId = patientsData.length ? Math.max(...patientsData.map(x => x.id)) + 1 : 1;
        patientsData.push({ id: newId, name, age, gender, phone, email, category, status });
    }

    closePatientModal();
    renderPatientsTable();
}

/**
 * VISITS: Render visit history table from visitsData array
 * Shows patient visit records with status (Resolved / Follow-up / Referred)
 * Populates the visits page with formatted data
 */
function renderVisitsTable() {
    const tbody = document.querySelector('#visits-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    visitsData.forEach(visit => {
        const tr = document.createElement('tr');
        
        // Determine status badge color
        let statusClass = 'status-active';
        if (visit.status === 'follow-up') statusClass = 'status-warning';
        else if (visit.status === 'referred') statusClass = 'status-danger';
        
        tr.innerHTML = `
            <td>${visit.patientName}</td>
            <td>${visit.doctorName}</td>
            <td>${visit.visitDate}</td>
            <td>${visit.issue}</td>
            <td><span class="status-badge ${statusClass}">${visit.status}</span></td>
            <td>${visit.notes || '-'}</td>
        `;
        tbody.appendChild(tr);
    });
    
    appLog('Visits table rendered successfully');
}

/**
 * DOCTOR SEARCH: Filter doctors table by name or specialization
 * Called when user types in doctor search input on doctors.html
 */
function filterDoctorsTable(searchTerm) {
    const tbody = document.querySelector('#doctors-table tbody');
    if (!tbody) return;
    
    const normalizedSearch = searchTerm.trim().toLowerCase();
    tbody.innerHTML = '';
    
    const filtered = doctorsData.filter(doc => {
        const matchName = doc.name.toLowerCase().includes(normalizedSearch);
        const matchSpec = doc.specialization.toLowerCase().includes(normalizedSearch);
        return matchName || matchSpec;
    });
    
    filtered.forEach(doc => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${doc.name}</td>
            <td>${doc.specialization}</td>
            <td>${doc.availability}</td>
            <td><span class="status-badge ${doc.status === 'active' ? 'status-active' : 'status-inactive'}">${doc.status}</span></td>
            <td class="action-links">
                <button class="btn-link" data-action="view" data-id="${doc.id}">View</button>
                <button class="btn-link" data-action="edit" data-id="${doc.id}">Edit</button>
                <button class="btn-link" data-action="delete" data-id="${doc.id}">Delete</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
    
    // Re-attach action handlers to new buttons
    tbody.querySelectorAll('.btn-link').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const action = btn.getAttribute('data-action');
            const id = Number(btn.getAttribute('data-id'));
            handleDoctorAction(action, id);
        });
    });
    
    appLog(`Doctors filtered by: "${searchTerm}" (${filtered.length} results)`);
}

/**
 * PATIENT SEARCH: Filter patients table by name or problem
 * Called when user types in patient search input on patients.html
 */
function filterPatientsTable(searchTerm) {
    const tbody = document.querySelector('#patients-table tbody');
    if (!tbody) return;
    
    const normalizedSearch = searchTerm.trim().toLowerCase();
    tbody.innerHTML = '';
    
    const filtered = patientsData.filter(patient => {
        const matchName = patient.name.toLowerCase().includes(normalizedSearch);
        const matchProblem = patient.problem.toLowerCase().includes(normalizedSearch);
        return matchName || matchProblem;
    });
    
    filtered.forEach(p => {
        const tr = document.createElement('tr');
        
        // Status badge color based on referral status
        let statusClass = 'status-active';
        if (p.status === 'follow-up') statusClass = 'status-warning';
        else if (p.status === 'referred') statusClass = 'status-danger';
        
        tr.innerHTML = `
            <td>${p.name}</td>
            <td>${p.problem}</td>
            <td>${p.assignedDoctor}</td>
            <td>${p.lastVisit}</td>
            <td><span class="status-badge ${statusClass}">${p.status}</span></td>
            <td class="action-links">
                <button class="btn-link" data-action="view" data-id="${p.id}">View</button>
                <button class="btn-link" data-action="edit" data-id="${p.id}">Edit</button>
                <button class="btn-link" data-action="delete" data-id="${p.id}">Delete</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
    
    // Re-attach action handlers
    tbody.querySelectorAll('.btn-link').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const action = btn.getAttribute('data-action');
            const id = Number(btn.getAttribute('data-id'));
            handlePatientAction(action, id);
        });
    });
    
    appLog(`Patients filtered by: "${searchTerm}" (${filtered.length} results)`);
}

/* Setup management page event listeners */
function initializeManagementPages() {
    // Doctors page
    if (isDoctorsPage()) {
        renderDoctorsTable();
        
        // Doctor search filter
        const doctorSearch = document.getElementById('doctor-search');
        if (doctorSearch) {
            doctorSearch.addEventListener('input', (e) => {
                filterDoctorsTable(e.target.value);
            });
        }
        
        const addBtn = document.getElementById('add-doctor-btn');
        if (addBtn) addBtn.addEventListener('click', () => openDoctorModal('add'));
        const modal = document.getElementById('doctor-modal');
        if (modal) {
            document.getElementById('doc-cancel').addEventListener('click', closeDoctorModal);
            document.getElementById('doctor-form').addEventListener('submit', saveDoctorFromModal);
            modal.addEventListener('click', (e) => { if (e.target === modal) closeDoctorModal(); });
        }
    }

    // Patients page - UPDATED with new search by name/problem
    if (isPatientsPage()) {
        renderPatientsTable();
        
        // Patient search filter (searches by name or problem)
        const patientSearch = document.getElementById('patient-search');
        if (patientSearch) {
            patientSearch.addEventListener('input', (e) => {
                filterPatientsTable(e.target.value);
            });
        }
        
        appLog('Patients page initialized with search functionality');
    }
    
    // Visits page - NEW
    if (isVisitsPage()) {
        renderVisitsTable();
        appLog('Visits page initialized with visit history table');
    }
}

// Initialize management pages when DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeManagementPages);
} else {
    initializeManagementPages();
}


