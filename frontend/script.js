// Medifinder Web - Complete JavaScript

const API_URL = 'https://medifinder-production.up.railway.app';
const AUTH_URL = `${API_URL}/auth`;

// Stan aplikacji
let currentProfile = null;
let profiles = [];
let appointments = [];
let currentUser = null;

// =========================
// INICJALIZACJA
// =========================

function initializeApp() {
    console.log('🚀 Inicjalizacja Medifinder Web');
    checkAuth();
    attachEventListeners();
}

// =========================
// AUTHENTICATION
// =========================

async function checkAuth() {
    try {
        const response = await fetch(`${AUTH_URL}/me`, {
            credentials: 'include'
        });
        const data = await response.json();
        
        if (data.authenticated) {
            currentUser = data.user;
            showApp(data.user);
            loadProfiles();
        } else {
            showLogin();
        }
    } catch (error) {
        console.error('❌ Błąd sprawdzania auth:', error);
        showLogin();
    }
}

function loginWithGoogle() {
    window.location.href = `${AUTH_URL}/login`;
}

async function logout() {
    try {
        await fetch(`${AUTH_URL}/logout`, {
            method: 'POST',
            credentials: 'include'
        });
        showLogin();
        showNotification('Wylogowano pomyślnie', 'success');
    } catch (error) {
        console.error('❌ Błąd wylogowania:', error);
        showNotification('Błąd wylogowania', 'error');
    }
}

function showApp(user) {
    document.getElementById('loginOverlay').style.display = 'none';
    document.getElementById('appContent').classList.remove('hidden');
    
    // Update header
    document.getElementById('userLabel').textContent = user.name || user.email;
    const authBtn = document.getElementById('authBtn');
    authBtn.textContent = '🚪 Wyloguj';
    authBtn.onclick = logout;
}

function showLogin() {
    document.getElementById('loginOverlay').style.display = 'flex';
    document.getElementById('appContent').classList.add('hidden');
    
    // Update header
    document.getElementById('userLabel').textContent = '';
    const authBtn = document.getElementById('authBtn');
    authBtn.textContent = '🔐 Zaloguj przez Google';
    authBtn.onclick = loginWithGoogle;
}

// =========================
// EVENT LISTENERS
// =========================

function attachEventListeners() {
    // Search form
    document.getElementById('searchBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        searchAppointments();
    });

    // Profile management
    document.getElementById('addProfileBtn')?.addEventListener('click', showAddProfileForm);
    document.getElementById('saveProfileBtn')?.addEventListener('click', saveProfile);
    document.getElementById('cancelProfileBtn')?.addEventListener('click', hideAddProfileForm);
    
    // Auto book checkbox
    document.getElementById('autoBook')?.addEventListener('change', (e) => {
        const btn = document.getElementById('searchBtn');
        if (e.target.checked) {
            btn.textContent = '🤖 Rozpocznij Auto-Rezerwację';
            btn.classList.add('btn-warning');
        } else {
            btn.textContent = '🔍 Rozpocznij Wyszukiwanie';
            btn.classList.remove('btn-warning');
        }
    });
}

// =========================
// TAB SWITCHING
// =========================

function switchTab(tabName, event) {
    // Ukryj wszystkie taby
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Usuń active z wszystkich przycisków
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Pokaż wybrany tab
    document.getElementById(tabName)?.classList.add('active');
    
    // Zaznacz aktywny przycisk
    if (event) {
        event.target.classList.add('active');
    }
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
    const select = document.getElementById('profile');
    if (select) {
        select.innerHTML = '<option value="">-- Wybierz profil --</option>' + 
            profiles.map(p => `<option value="${p}">${p}</option>`).join('');
    }
}

function selectProfile(profileName) {
    const select = document.getElementById('profile');
    if (select) {
        select.value = profileName;
        switchTab('search');
        document.querySelector('.nav-btn.active').classList.remove('active');
        document.querySelector('.nav-btn:first-child').classList.add('active'); // Search tab button
        showNotification(`Wybrano profil: ${profileName}`, 'success');
    }
}

function showAddProfileForm() {
    document.getElementById('addProfileForm')?.classList.remove('hidden');
    document.getElementById('addProfileBtn')?.classList.add('hidden');
}

function hideAddProfileForm() {
    document.getElementById('addProfileForm')?.classList.add('hidden');
    document.getElementById('addProfileBtn')?.classList.remove('hidden');
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
    
    showLoading(true);

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
    } finally {
        showLoading(false);
    }
}

// =========================
// APPOINTMENTS SEARCH
// =========================

async function searchAppointments() {
    const profile = document.getElementById('profile')?.value;
    const specialty = document.getElementById('specialty')?.value;
    
    if (!profile) {
        showNotification('Wybierz profil', 'error');
        return;
    }
    
    // Collect form data
    const doctors = document.getElementById('doctors').value.split(',').map(s => s.trim()).filter(Boolean);
    const clinics = document.getElementById('clinics').value.split(',').map(s => s.trim()).filter(Boolean);
    const timeFrom = document.getElementById('timeFrom').value;
    const timeTo = document.getElementById('timeTo').value;
    const excludedDates = document.getElementById('excludedDates').value.split(',').map(s => s.trim()).filter(Boolean);
    const autoBook = document.getElementById('autoBook').checked;

    // Day ranges
    const dayTimeRanges = {};
    document.querySelectorAll('.day-row').forEach(row => {
        if (row.querySelector('.day-enabled').checked) {
            const day = row.dataset.day;
            dayTimeRanges[day] = {
                start: row.querySelector('.day-from').value,
                end: row.querySelector('.day-to').value
            };
        }
    });

    const payload = {
        profile,
        specialty,
        doctors,
        clinics,
        time_range: { start: timeFrom, end: timeTo },
        day_time_ranges: dayTimeRanges,
        excluded_dates: excludedDates,
        auto_book: autoBook
    };

    showLoading(true);
    
    const endpoint = autoBook ? `${API_URL}/api/v1/appointments/auto-book` : `${API_URL}/api/v1/appointments/search`;

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (autoBook) {
                showNotification(data.message, 'success');
            } else {
                appointments = data.data;
                renderAppointments();
                switchTab('results');
                // Update active button manually as we switched programmatically
                document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
                document.querySelectorAll('.nav-btn')[2].classList.add('active'); // Results tab
                showNotification(`Znaleziono ${data.count} wizyt`, 'success');
            }
        } else {
            showNotification('Błąd: ' + (data.error || data.message), 'error');
        }
    } catch (error) {
        console.error('❌ Błąd requestu:', error);
        showNotification('Błąd połączenia z serwerem', 'error');
    } finally {
        showLoading(false);
    }
}

function renderAppointments() {
    const container = document.getElementById('appointmentsList');
    if (!container) return;
    
    if (appointments.length === 0) {
        container.innerHTML = '<p class="empty-state">Nie znaleziono wizyt pasujących do kryteriów.</p>';
        return;
    }
    
    container.innerHTML = appointments.map(apt => `
        <div class="appointment-card">
            <div class="appointment-info">
                <h3>${apt.specialty_name || apt.specialty?.name || 'Wizyta'}</h3>
                <p><strong>👨‍⚕️ Lekarz:</strong> ${apt.doctor_name || apt.doctor?.name || 'Brak danych'}</p>
                <p><strong>🏥 Placówka:</strong> ${apt.clinic_name || apt.clinic?.name || 'Brak danych'}</p>
                <p><strong>📅 Data:</strong> ${apt.date ? new Date(apt.date).toLocaleDateString() : 'Brak daty'} ${apt.time || ''}</p>
            </div>
            <div class="appointment-actions">
                <button class="btn btn-primary" onclick="bookAppointment('${apt.id}')">Zarezerwuj</button>
            </div>
        </div>
    `).join('');
}

async function bookAppointment(appointmentId) {
    const profile = document.getElementById('profile')?.value;
    
    if (!profile) {
        showNotification('Wybierz profil', 'error');
        return;
    }
    
    showLoading(true);

    try {
        const response = await fetch(`${API_URL}/api/v1/appointments/book`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ profile, appointment_id: appointmentId })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('✅ Wizyta zarezerwowana pomyślnie!', 'success');
            // Remove booked appointment from list
            appointments = appointments.filter(a => a.id !== appointmentId);
            renderAppointments();
        } else {
            showNotification('Błąd rezerwacji: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('❌ Błąd rezerwacji:', error);
        showNotification('Błąd połączenia z serwerem', 'error');
    } finally {
        showLoading(false);
    }
}

// =========================
// UI HELPERS
// =========================

function showLoading(show) {
    const loader = document.getElementById('loadingModal');
    if (loader) {
        loader.style.display = show ? 'flex' : 'none';
    }
}

function showNotification(message, type = 'info') {
    const toast = document.getElementById('toast');
    if (!toast) return;

    toast.textContent = message;
    toast.className = `toast toast-${type} show`;
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

function openGitHub() {
    window.open('https://github.com/AdamWojciechowskiPL/Medifinder', '_blank');
}

// =========================
// INIT ON LOAD
// =========================

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}
