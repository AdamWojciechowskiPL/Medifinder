// Medifinder Web - Complete JavaScript

const API_URL = 'https://medifinder-production.up.railway.app';

// Stan aplikacji
let currentProfile = null;
let profiles = [];
let appointments = [];

// =========================
// INICJALIZACJA
// =========================

function initializeApp() {
    console.log('🚀 Inicjalizacja Medifinder Web');
    attachEventListeners();
    checkAuth();
    loadProfiles();
}

// =========================
// EVENT LISTENERS
// =========================

function attachEventListeners() {
    // Profile management
    document.getElementById('addProfileBtn')?.addEventListener('click', showAddProfileForm);
    document.getElementById('saveProfileBtn')?.addEventListener('click', saveProfile);
    document.getElementById('cancelProfileBtn')?.addEventListener('click', hideAddProfileForm);
    
    // Search
    document.getElementById('searchBtn')?.addEventListener('click', searchAppointments);
    document.getElementById('autoBookBtn')?.addEventListener('click', autoBookAppointment);
    
    // Auth
    document.getElementById('loginBtn')?.addEventListener('click', login);
    document.getElementById('logoutBtn')?.addEventListener('click', logout);
}

// =========================
// TAB SWITCHING
// =========================

function switchTab(tabName) {
    // Ukryj wszystkie taby
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Usuń active z wszystkich przycisków
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Pokaż wybrany tab
    document.getElementById(tabName + 'Tab')?.classList.add('active');
    
    // Zaznacz aktywny przycisk
    event.target.classList.add('active');
    
    console.log(`📦 Przełączono na tab: ${tabName}`);
}

// =========================
// AUTHENTICATION
// =========================

async function checkAuth() {
    try {
        const response = await fetch(`${API_URL}/auth/me`, {
            credentials: 'include'
        });
        const data = await response.json();
        
        if (data.authenticated) {
            showLoggedIn(data.user);
        } else {
            showLoggedOut();
        }
    } catch (error) {
        console.error('❌ Błąd sprawdzania auth:', error);
        showLoggedOut();
    }
}

function login() {
    window.location.href = `${API_URL}/auth/login`;
}

async function logout() {
    try {
        await fetch(`${API_URL}/auth/logout`, {
            method: 'POST',
            credentials: 'include'
        });
        showLoggedOut();
        showNotification('Wylogowano pomyślnie', 'success');
    } catch (error) {
        console.error('❌ Błąd wylogowania:', error);
        showNotification('Błąd wylogowania', 'error');
    }
}

function showLoggedIn(user) {
    document.getElementById('loginSection')?.classList.add('hidden');
    document.getElementById('loggedInSection')?.classList.remove('hidden');
    document.getElementById('userName').textContent = user.name || user.email;
}

function showLoggedOut() {
    document.getElementById('loginSection')?.classList.remove('hidden');
    document.getElementById('loggedInSection')?.classList.add('hidden');
}

// =========================
// PROFILE MANAGEMENT
// =========================

async function loadProfiles() {
    try {
        const response = await fetch(`${API_URL}/api/v1/profiles`, {
            credentials: 'include'
        });
        const data = await response.json();
        
        if (data.success) {
            profiles = data.data;
            renderProfiles();
            populateProfileSelects();
        }
    } catch (error) {
        console.error('❌ Błąd ładowania profili:', error);
    }
}

function renderProfiles() {
    const container = document.getElementById('profilesList');
    if (!container) return;
    
    if (profiles.length === 0) {
        container.innerHTML = '<p class="empty-state">Brak profili. Dodaj pierwszy profil.</p>';
        return;
    }
    
    container.innerHTML = profiles.map(profile => `
        <div class="profile-card">
            <div class="profile-info">
                <h3>${profile}</h3>
            </div>
            <div class="profile-actions">
                <button class="btn btn-secondary" onclick="selectProfile('${profile}')">Wybierz</button>
            </div>
        </div>
    `).join('');
}

function populateProfileSelects() {
    const selects = document.querySelectorAll('.profile-select');
    selects.forEach(select => {
        select.innerHTML = '<option value="">Wybierz profil</option>' + 
            profiles.map(p => `<option value="${p}">${p}</option>`).join('');
    });
}

function selectProfile(profileName) {
    currentProfile = profileName;
    showNotification(`Wybrano profil: ${profileName}`, 'success');
}

function showAddProfileForm() {
    document.getElementById('addProfileForm')?.classList.remove('hidden');
}

function hideAddProfileForm() {
    document.getElementById('addProfileForm')?.classList.add('hidden');
    document.getElementById('profileForm')?.reset();
}

async function saveProfile() {
    const name = document.getElementById('profileName')?.value;
    const login = document.getElementById('profileLogin')?.value;
    const password = document.getElementById('profilePassword')?.value;
    
    if (!name || !login || !password) {
        showNotification('Wypełnij wszystkie pola', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/api/v1/profiles/add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ name, login, password })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('Profil dodany pomyślnie', 'success');
            hideAddProfileForm();
            loadProfiles();
        } else {
            showNotification('Błąd dodawania profilu: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('❌ Błąd zapisywania profilu:', error);
        showNotification('Błąd połączenia z serwerem', 'error');
    }
}

// =========================
// APPOINTMENTS SEARCH
// =========================

async function searchAppointments() {
    const profile = document.getElementById('searchProfile')?.value;
    const specialty = document.getElementById('searchSpecialty')?.value;
    
    if (!profile) {
        showNotification('Wybierz profil', 'error');
        return;
    }
    
    showLoading(true);
    
    try {
        const response = await fetch(`${API_URL}/api/v1/appointments/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ profile, specialty })
        });
        
        const data = await response.json();
        
        if (data.success) {
            appointments = data.data;
            renderAppointments();
            showNotification(`Znaleziono ${data.count} wizyt`, 'success');
        } else {
            showNotification('Błąd wyszukiwania: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('❌ Błąd wyszukiwania:', error);
        showNotification('Błąd połączenia z serwerem', 'error');
    } finally {
        showLoading(false);
    }
}

function renderAppointments() {
    const container = document.getElementById('appointmentsList');
    if (!container) return;
    
    if (appointments.length === 0) {
        container.innerHTML = '<p class="empty-state">Nie znaleziono wizyt.</p>';
        return;
    }
    
    container.innerHTML = appointments.map(apt => `
        <div class="appointment-card">
            <div class="appointment-info">
                <h3>${apt.specialty?.name || 'Specjalizacja'}</h3>
                <p><strong>Lekarz:</strong> ${apt.doctor?.name || 'Brak danych'}</p>
                <p><strong>Placówka:</strong> ${apt.clinic?.name || 'Brak danych'}</p>
                <p><strong>Data:</strong> ${apt.visitDate || 'Brak daty'} ${apt.visitTime || ''}</p>
            </div>
            <div class="appointment-actions">
                <button class="btn btn-primary" onclick="bookAppointment('${apt.id}')">Zarezerwuj</button>
            </div>
        </div>
    `).join('');
}

async function bookAppointment(appointmentId) {
    const profile = document.getElementById('searchProfile')?.value;
    
    if (!profile) {
        showNotification('Wybierz profil', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/api/v1/appointments/book`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ profile, appointment_id: appointmentId })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('Wizyta zarezerwowana!', 'success');
        } else {
            showNotification('Błąd rezerwacji: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('❌ Błąd rezerwacji:', error);
        showNotification('Błąd połączenia z serwerem', 'error');
    }
}

async function autoBookAppointment() {
    const profile = document.getElementById('autoBookProfile')?.value;
    const specialty = document.getElementById('autoBookSpecialty')?.value;
    
    if (!profile || !specialty) {
        showNotification('Wybierz profil i specjalizację', 'error');
        return;
    }
    
    showLoading(true);
    
    try {
        const response = await fetch(`${API_URL}/api/v1/appointments/auto-book`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ profile, specialty, auto_book: true })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('✅ Wizyta automatycznie zarezerwowana!', 'success');
        } else {
            showNotification('Błąd auto-rezerwacji: ' + data.message, 'error');
        }
    } catch (error) {
        console.error('❌ Błąd auto-rezerwacji:', error);
        showNotification('Błąd połączenia z serwerem', 'error');
    } finally {
        showLoading(false);
    }
}

// =========================
// UI HELPERS
// =========================

function showLoading(show) {
    const loader = document.getElementById('loader');
    if (loader) {
        loader.style.display = show ? 'flex' : 'none';
    }
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.classList.add('show');
    }, 10);
    
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// =========================
// INIT ON LOAD
// =========================

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}
