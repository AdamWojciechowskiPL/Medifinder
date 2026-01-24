// API Configuration
const API_BASE_URL = window.location.origin + '/api/v1';
const AUTH_BASE_URL = window.location.origin + '/auth';
const REQUEST_TIMEOUT = 60000; // 60 seconds

let currentProfile = null;
let searchResults = [];
let profiles = [];
let currentUser = null;

// ============ INITIALIZATION ============
document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
});

async function initializeApp() {
    console.log('🚀 Inicjalizacja Medifinder Web');
    attachEventListeners();
    await checkAuth();
    checkServerStatus();
    if (currentUser) {
        loadProfiles();
    }
    showToast('✅ Aplikacja załadowana', 'success');
}

// ============ AUTH ============
async function checkAuth() {
    try {
        const res = await fetch(`${AUTH_BASE_URL}/me`, {
            credentials: 'include'
        });
        const data = await res.json();
        if (data.authenticated) {
            currentUser = data.user;
            updateAuthUI(true, data.user);
        } else {
            currentUser = null;
            updateAuthUI(false, null);
        }
    } catch (e) {
        console.error('Auth check error', e);
        updateAuthUI(false, null);
    }
}

function updateAuthUI(isAuthenticated, user) {
    const status = document.getElementById('status');
    const authBtn = document.getElementById('authBtn');
    const userLabel = document.getElementById('userLabel');

    if (isAuthenticated) {
        status.textContent = `🟢 Zalogowany: ${user.email}`;
        authBtn.textContent = '🚪 Wyloguj';
        authBtn.onclick = logout;
        userLabel.textContent = user.name || user.email;
    } else {
        status.textContent = '🟡 Niezalogowany';
        authBtn.textContent = '🔐 Zaloguj przez Google';
        authBtn.onclick = loginWithGoogle;
        userLabel.textContent = '';
    }
}

function loginWithGoogle() {
    window.location.href = `${AUTH_BASE_URL}/login`;
}

async function logout() {
    try {
        await fetch(`${AUTH_BASE_URL}/logout`, {
            method: 'POST',
            credentials: 'include'
        });
        currentUser = null;
        updateAuthUI(false, null);
        showToast('Wylogowano', 'info');
    } catch (e) {
        console.error(e);
        showToast('Błąd wylogowania', 'error');
    }
}

// ============ SERVER STATUS ============
function checkServerStatus() {
    fetch(window.location.origin + '/health')
        .then(response => response.json())
        .then(data => {
            document.getElementById('serverStatus').textContent = '✅ Online';
        })
        .catch(() => {
            document.getElementById('serverStatus').textContent = '❌ Offline';
        });
}

// ============ PROFILES ============
function loadProfiles() {
    fetch(`${API_BASE_URL}/profiles`, { credentials: 'include' })
        .then(r => r.json())
        .then(data => {
            profiles = data.data || [];
            updateProfileSelects();
            displayProfiles();
        })
        .catch(() => showToast('Nie udało się załadować profili', 'error'));
}

// ... reszta funkcji z poprzedniej wersji script.js, ale:
// - wszystkie fetch() do API muszą mieć { credentials: 'include' }
// - searchAppointments musi wysyłać day_time_ranges i excluded_dates

function searchAppointments(event) {
    event.preventDefault();
    if (!currentUser) {
        showToast('Najpierw zaloguj się przez Google', 'warning');
        return;
    }

    const profile = document.getElementById('profile').value;
    const specialty = document.getElementById('specialty').value;
    const doctors = document.getElementById('doctors').value.split(',').map(d => d.trim()).filter(Boolean);
    const clinics = document.getElementById('clinics').value.split(',').map(c => c.trim()).filter(Boolean);

    const timeFrom = document.getElementById('timeFrom').value;
    const timeTo = document.getElementById('timeTo').value;
    const autoBook = document.getElementById('autoBook').checked;

    const dayTimeRanges = {};
    document.querySelectorAll('.day-row').forEach(row => {
        const day = row.dataset.day;
        const enabled = row.querySelector('.day-enabled').checked;
        const from = row.querySelector('.day-from').value;
        const to = row.querySelector('.day-to').value;
        if (enabled) {
            dayTimeRanges[day] = { start: from, end: to };
        }
    });

    const excludedDates = document.getElementById('excludedDates').value
        .split(',')
        .map(d => d.trim())
        .filter(Boolean);

    const payload = {
        profile,
        specialty,
        doctors,
        clinics,
        preferred_days: Object.keys(dayTimeRanges).map(d => parseInt(d)),
        time_range: { start: timeFrom, end: timeTo },
        day_time_ranges: dayTimeRanges,
        excluded_dates: excludedDates,
        auto_book: autoBook
    };

    const endpoint = autoBook ? `${API_BASE_URL}/appointments/auto-book` : `${API_BASE_URL}/appointments/search`;

    const loadingModal = document.getElementById('loadingModal');
    loadingModal.style.display = 'flex';
    document.getElementById('loadingText').textContent = '🔍 Wyszukiwanie wizyt...';

    fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload)
    })
        .then(r => r.json())
        .then(data => {
            loadingModal.style.display = 'none';
            if (!data.success) throw new Error(data.error || 'Błąd');
            searchResults = data.data || [];
            displayResults();
            switchTab('results');
        })
        .catch(e => {
            loadingModal.style.display = 'none';
            showToast(e.message, 'error');
        });
}

// reszta poprzedniego kodu (displayResults, addProfile, itp.)
