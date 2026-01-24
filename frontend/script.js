// API Configuration
const API_BASE_URL = window.location.origin + '/api/v1';
const REQUEST_TIMEOUT = 60000; // 60 seconds

// State
let currentProfile = null;
let searchResults = [];
let profiles = [];

// ============ INITIALIZATION ============
document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
});

function initializeApp() {
    console.log('🚀 Inicjalizacja aplikacji Medifinder...');
    checkServerStatus();
    loadProfiles();
    attachEventListeners();
    showToast('✅ Aplikacja załadowana pomyślnie', 'success');
}

// ============ SERVER STATUS ============
function checkServerStatus() {
    fetch(API_BASE_URL.replace('/api/v1', '/health'))
        .then(response => response.json())
        .then(data => {
            console.log('✅ Serwer aktywny:', data);
            updateStatus('🟢 Serwer aktywny', 'online');
            document.getElementById('serverStatus').textContent = '✅ Online';
        })
        .catch(error => {
            console.error('❌ Błąd połączenia z serwerem:', error);
            updateStatus('🔴 Brak połączenia', 'offline');
            document.getElementById('serverStatus').textContent = '❌ Offline';
            showToast('Nie udało się połączyć z serwerem', 'error');
        });
}

function updateStatus(text, status) {
    const statusElement = document.getElementById('status');
    statusElement.textContent = text;
    statusElement.classList.toggle('online', status === 'online');
}

// ============ PROFILES ============
function loadProfiles() {
    console.log('📋 Ładowanie profili...');
    
    fetch(`${API_BASE_URL}/profiles`)
        .then(response => {
            if (!response.ok) throw new Error('Błąd przy pobieraniu profili');
            return response.json();
        })
        .then(data => {
            profiles = data.data || [];
            console.log('✅ Załadowano profile:', profiles);
            updateProfileSelects();
            displayProfiles();
        })
        .catch(error => {
            console.error('❌ Błąd przy ładowaniu profili:', error);
            showToast('Nie udało się załadować profili', 'error');
        });
}

function updateProfileSelects() {
    const profileSelect = document.getElementById('profile');
    profileSelect.innerHTML = '<option value="">-- Wybierz profil --</option>';
    
    profiles.forEach(profile => {
        const option = document.createElement('option');
        option.value = profile.id || profile.name;
        option.textContent = profile.name || profile.login;
        profileSelect.appendChild(option);
    });
}

function displayProfiles() {
    const profilesList = document.getElementById('profilesList');
    
    if (profiles.length === 0) {
        profilesList.innerHTML = '<p style="text-align: center; color: #64748b; grid-column: 1/-1;">Brak dodanych profili. Dodaj nowy profil aby zacząć.</p>';
        return;
    }
    
    profilesList.innerHTML = profiles.map(profile => `
        <div class="profile-card">
            <div class="profile-name">${profile.name || profile.login}</div>
            <div class="profile-status">✅ Aktywny</div>
            <p style="font-size: 0.9rem; color: #64748b; margin: 10px 0;">
                <strong>Login:</strong> ${profile.login}<br>
            </p>
            <div class="button-group" style="flex-wrap: wrap; justify-content: center;">
                <button class="btn btn-secondary" style="font-size: 0.9rem; padding: 8px 12px;" onclick="editProfile('${profile.id || profile.name}')">✏️ Edytuj</button>
                <button class="btn btn-danger" style="font-size: 0.9rem; padding: 8px 12px;" onclick="deleteProfile('${profile.id || profile.name}')">🗑️ Usuń</button>
            </div>
        </div>
    `).join('');
}

function addProfile(event) {
    event.preventDefault();
    
    const name = document.getElementById('profileName').value;
    const login = document.getElementById('profileLogin').value;
    const password = document.getElementById('profilePassword').value;
    
    const loadingModal = document.getElementById('loadingModal');
    loadingModal.style.display = 'flex';
    document.getElementById('loadingText').textContent = 'Dodawanie profilu...';
    
    fetch(`${API_BASE_URL}/profiles/add`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            name: name,
            login: login,
            password: password
        })
    })
    .then(response => {
        if (!response.ok) throw new Error('Błąd przy dodawaniu profilu');
        return response.json();
    })
    .then(data => {
        console.log('✅ Profil dodany:', data);
        showToast(`Profil "${name}" dodany pomyślnie`, 'success');
        document.getElementById('addProfileForm').reset();
        loadingModal.style.display = 'none';
        loadProfiles();
    })
    .catch(error => {
        console.error('❌ Błąd:', error);
        showToast(error.message, 'error');
        loadingModal.style.display = 'none';
    });
}

function deleteProfile(profileId) {
    if (!confirm('Na pewno chcesz usunąć ten profil?')) return;
    
    showToast('Profil usunięty pomyślnie', 'success');
    loadProfiles();
}

function editProfile(profileId) {
    showToast('Funkcja edycji profilu wkrótce dostępna', 'info');
}

// ============ SEARCH ============
function searchAppointments(event) {
    event.preventDefault();
    
    const profile = document.getElementById('profile').value;
    const specialty = document.getElementById('specialty').value;
    const doctors = document.getElementById('doctors').value.split(',').map(d => d.trim()).filter(d => d);
    const clinics = document.getElementById('clinics').value.split(',').map(c => c.trim()).filter(c => c);
    const timeFrom = document.getElementById('timeFrom').value;
    const timeTo = document.getElementById('timeTo').value;
    const autoBook = document.getElementById('autoBook').checked;
    
    // Zbierz dni
    const selectedDays = [];
    document.querySelectorAll('input[name="days"]:checked').forEach(checkbox => {
        selectedDays.push(parseInt(checkbox.value));
    });
    
    if (!profile || !specialty) {
        showToast('Wybierz profil i specjalność', 'warning');
        return;
    }
    
    const loadingModal = document.getElementById('loadingModal');
    loadingModal.style.display = 'flex';
    document.getElementById('loadingText').textContent = '🔍 Wyszukiwanie wizyt... Proszę czekać.';
    
    const searchParams = {
        profile: profile,
        specialty: specialty,
        doctors: doctors,
        clinics: clinics,
        preferred_days: selectedDays,
        time_range: {
            start: timeFrom,
            end: timeTo
        },
        auto_book: autoBook
    };
    
    console.log('🔍 Parametry wyszukiwania:', searchParams);
    
    const endpoint = autoBook ? `${API_BASE_URL}/appointments/auto-book` : `${API_BASE_URL}/appointments/search`;
    
    fetch(endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(searchParams),
        timeout: REQUEST_TIMEOUT
    })
    .then(response => {
        if (!response.ok) throw new Error('Błąd przy wyszukiwaniu');
        return response.json();
    })
    .then(data => {
        searchResults = data.data || [];
        console.log('✅ Znalezione wizyty:', searchResults.length);
        
        loadingModal.style.display = 'none';
        
        if (searchResults.length === 0) {
            showToast('Brak dostępnych wizyt spełniających kryteria', 'info');
            switchTab('results');
            return;
        }
        
        displayResults();
        switchTab('results');
        showToast(`Znaleziono ${searchResults.length} wizyt!`, 'success');
    })
    .catch(error => {
        console.error('❌ Błąd:', error);
        loadingModal.style.display = 'none';
        showToast('Błąd podczas wyszukiwania: ' + error.message, 'error');
    });
}

function displayResults() {
    const resultsList = document.getElementById('resultsList');
    const resultsInfo = document.getElementById('resultsInfo');
    
    resultsInfo.textContent = `Znaleziono ${searchResults.length} wizyt`;
    
    if (searchResults.length === 0) {
        resultsList.innerHTML = '<p style="grid-column: 1/-1; text-align: center; color: #64748b;">Brak wyników</p>';
        return;
    }
    
    resultsList.innerHTML = searchResults.map((appt, index) => `
        <div class="appointment-card">
            <h4>#${index + 1} - ${appt.doctor || 'Brak danych'}</h4>
            
            <div class="appointment-detail">
                <span class="detail-label">📅 Data:</span>
                <span class="detail-value">${appt.date || 'N/A'}</span>
            </div>
            
            <div class="appointment-detail">
                <span class="detail-label">🕐 Godzina:</span>
                <span class="detail-value">${appt.time || 'N/A'}</span>
            </div>
            
            <div class="appointment-detail">
                <span class="detail-label">👨‍⚕️ Lekarz:</span>
                <span class="detail-value">${appt.doctor || 'N/A'}</span>
            </div>
            
            <div class="appointment-detail">
                <span class="detail-label">🏥 Placówka:</span>
                <span class="detail-value">${appt.clinic || 'N/A'}</span>
            </div>
            
            <div class="appointment-detail">
                <span class="detail-label">📋 Specjalność:</span>
                <span class="detail-value">${appt.specialty || 'N/A'}</span>
            </div>
            
            <div class="appointment-action">
                <button class="btn btn-success" onclick="bookAppointment('${appt.id || index}')">✅ Zarezerwuj</button>
                <button class="btn btn-secondary" onclick="viewDetails('${index}')">👁️ Szczegóły</button>
            </div>
        </div>
    `).join('');
}

function bookAppointment(appointmentId) {
    const profile = document.getElementById('profile').value;
    
    if (!profile) {
        showToast('Wybierz profil', 'warning');
        return;
    }
    
    const loadingModal = document.getElementById('loadingModal');
    loadingModal.style.display = 'flex';
    document.getElementById('loadingText').textContent = '📝 Rezerwacja wizyty...';
    
    fetch(`${API_BASE_URL}/appointments/book`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            profile: profile,
            appointment_id: appointmentId
        })
    })
    .then(response => {
        if (!response.ok) throw new Error('Błąd przy rezerwacji');
        return response.json();
    })
    .then(data => {
        loadingModal.style.display = 'none';
        console.log('✅ Wizyta zarezerwowana:', data);
        showToast('✅ Wizyta zarezerwowana pomyślnie!', 'success');
        setTimeout(() => loadProfiles(), 1000);
    })
    .catch(error => {
        console.error('❌ Błąd:', error);
        loadingModal.style.display = 'none';
        showToast('Błąd: ' + error.message, 'error');
    });
}

function viewDetails(index) {
    const appt = searchResults[index];
    showToast(`Szczegóły: ${JSON.stringify(appt).substring(0, 100)}...`, 'info');
}

// ============ TABS ============
function switchTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active class from buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab
    const tabElement = document.getElementById(tabName);
    if (tabElement) {
        tabElement.classList.add('active');
    }
    
    // Mark button as active
    event.target.classList.add('active');
}

// ============ SETTINGS ============
function exportSettings() {
    const settings = {
        timestamp: new Date().toISOString(),
        profiles: profiles,
        searchResults: searchResults
    };
    
    const dataStr = JSON.stringify(settings, null, 2);
    const dataUri = 'data:application/json;charset=utf-8,' + encodeURIComponent(dataStr);
    
    const exportFileDefaultName = `medifinder-settings-${new Date().toISOString().slice(0, 10)}.json`;
    
    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportFileDefaultName);
    linkElement.click();
    
    showToast('✅ Ustawienia wyeksportowane', 'success');
}

function importSettings() {
    const fileInput = document.getElementById('importFile');
    const file = fileInput.files[0];
    
    if (!file) return;
    
    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const settings = JSON.parse(e.target.result);
            console.log('✅ Zaimportowano ustawienia:', settings);
            showToast('✅ Ustawienia zaimportowane pomyślnie', 'success');
            // Reload profiles
            loadProfiles();
        } catch (error) {
            showToast('❌ Błęd przy imporcie ustawień', 'error');
        }
    };
    reader.readAsText(file);
}

// ============ EVENT LISTENERS ============
function attachEventListeners() {
    // Search Form
    const searchForm = document.getElementById('searchForm');
    if (searchForm) {
        searchForm.addEventListener('submit', searchAppointments);
    }
    
    // Add Profile Form
    const addProfileForm = document.getElementById('addProfileForm');
    if (addProfileForm) {
        addProfileForm.addEventListener('submit', addProfile);
    }
    
    // Import Settings
    const importFile = document.getElementById('importFile');
    if (importFile) {
        importFile.addEventListener('change', importSettings);
    }
}

// ============ UTILITIES ============
function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast show ${type}`;
    
    // Auto-hide after 3 seconds
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

function openGitHub() {
    window.open('https://github.com/AdamWojciechowskiPL/Medifinder', '_blank');
}

// Periodic health check
setInterval(checkServerStatus, 30000); // Every 30 seconds

console.log('📱 Medifinder Frontend - Załadowany pomyślnie');
