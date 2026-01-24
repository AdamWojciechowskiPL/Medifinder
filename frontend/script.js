// Medifinder Web - Desktop Logic Replica
// Ustawienie na pusty ciąg znaków, ponieważ teraz frontend jest serwowany z tej samej domeny co backend
const API_URL = '';
const AUTH_URL = '/auth';

let currentProfile = null;
let profiles = [];
let allSpecialties = [];
let allDoctors = [];
let allClinics = [];
let selectedDoctors = new Set();
let selectedClinics = new Set();
let selectedAppointment = null;
let searchResults = [];

// =========================
// INIT & AUTH
// =========================
document.addEventListener('DOMContentLoaded', () => {
    initWeekdays();
    setDefaultDates();
    checkAuth();

    // Event Listeners for UI
    document.getElementById('specialtySelect').addEventListener('change', handleSpecialtyChange);
    document.getElementById('searchBtn').addEventListener('click', searchAppointments);
    document.getElementById('resetBtn').addEventListener('click', resetFilters);
    document.getElementById('bookSelectedBtn').addEventListener('click', bookSelected);
    document.getElementById('exportBtn').addEventListener('click', exportResults);
});

async function checkAuth() {
    try {
        const resp = await fetch(`${AUTH_URL}/me`, { credentials: 'include' });
        const data = await resp.json();
        
        console.log('Auth check response:', data);

        if (data.authenticated) {
            console.log('User is authenticated, updating UI...');
            document.getElementById('loginOverlay').style.display = 'none';
            document.getElementById('appContent').classList.remove('hidden');
            document.getElementById('userLabel').textContent = data.user.name || data.user.email;
            
            const authBtn = document.getElementById('authBtn');
            authBtn.textContent = 'Wyloguj';
            authBtn.onclick = logout;
            
            loadProfiles();
        } else {
            console.log('User is NOT authenticated');
            document.getElementById('loginOverlay').style.display = 'flex';
        }
    } catch (e) { 
        console.error('Auth check error:', e); 
    }
}

function loginWithGoogle() { window.location.href = `${AUTH_URL}/login`; }
async function logout() { await fetch(`${AUTH_URL}/logout`, { method: 'POST', credentials: 'include' }); window.location.reload(); }

// =========================
// DATA LOADING
// =========================
async function loadProfiles() {
    try {
        const resp = await fetch(`${API_URL}/api/v1/profiles`, { credentials: 'include' });
        const data = await resp.json();
        if (data.success && data.data.length > 0) {
            profiles = data.data;
            currentProfile = profiles[0]; // Default to first
            updateProfileUI();
            loadDictionaries();
        } else {
            toggleProfilesModal(); // Force create profile
        }
    } catch (e) {
        console.error("Error loading profiles:", e);
    }
}

async function loadDictionaries() {
    try {
        // 1. Specialties
        const specResp = await fetch(`${API_URL}/api/v1/dictionaries/specialties?profile=${currentProfile}`, { credentials: 'include' });
        const specData = await specResp.json();
        allSpecialties = specData.data || [];
        renderSpecialties();

        // 2. Doctors
        const docResp = await fetch(`${API_URL}/api/v1/dictionaries/doctors`, { credentials: 'include' });
        const docData = await docResp.json();
        allDoctors = docData.data || [];
        renderMultiSelect('doctorsList', allDoctors, selectedDoctors, 'doctor');

        // 3. Clinics
        const clinicResp = await fetch(`${API_URL}/api/v1/dictionaries/clinics`, { credentials: 'include' });
        const clinicData = await clinicResp.json();
        allClinics = clinicData.data || [];
        renderMultiSelect('clinicsList', allClinics, selectedClinics, 'clinic');
    } catch (e) {
        console.error("Error loading dictionaries:", e);
    }
}

// =========================
// UI LOGIC
// =========================
function updateProfileUI() {
    document.getElementById('currentProfileLabel').textContent = `${currentProfile}`;
    // Re-render list in modal
    const list = document.getElementById('profilesList');
    if (list) {
        list.innerHTML = profiles.map(p => 
            `<div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                <span>${p}</span>
                <button class="btn btn-sm" onclick="switchProfile('${p}')">Wybierz</button>
             </div>`
        ).join('');
    }
}

function switchProfile(name) {
    currentProfile = name;
    updateProfileUI();
    toggleProfilesModal();
    loadDictionaries(); // Reload specialties (might differ for child/adult)
}

function renderSpecialties() {
    const sel = document.getElementById('specialtySelect');
    if (!sel) return;
    sel.innerHTML = '<option value="">-- Wybierz --</option>' + 
        allSpecialties.map(s => `<option value="${s.ids.join(',')}">${s.name}</option>`).join('');
}

function handleSpecialtyChange() {
    const val = document.getElementById('specialtySelect').value;
    if (!val) {
        // Reset doctors filter -> show all
        renderMultiSelect('doctorsList', allDoctors, selectedDoctors, 'doctor');
        return;
    }

    const specIds = val.split(',').map(Number);
    // Filter doctors who have at least one matching specialty ID
    const filteredDocs = allDoctors.filter(d => 
        d.specialty_ids.some(sid => specIds.includes(sid))
    );
    
    // Clear selection of doctors not in new list
    const validIds = new Set(filteredDocs.map(d => d.id));
    selectedDoctors = new Set([...selectedDoctors].filter(id => validIds.has(id)));
    
    renderMultiSelect('doctorsList', filteredDocs, selectedDoctors, 'doctor');
    updateTriggerLabel('doctorsTrigger', selectedDoctors, 'Lekarze');
}

// Multi-Select Renderer
function renderMultiSelect(elementId, items, selectionSet, type) {
    const container = document.getElementById(elementId);
    if (!container) return;
    
    container.innerHTML = items.map(item => {
        const isChecked = selectionSet.has(item.id) ? 'checked' : '';
        return `<div class="dropdown-item" onclick="toggleSelection('${type}', '${item.id}', this)">
            <input type="checkbox" ${isChecked} style="pointer-events:none;">
            <span>${item.name}</span>
        </div>`;
    }).join('');
    
    // Update label immediately
    const label = type === 'doctor' ? 'Lekarze' : 'Placówki';
    const triggerId = type === 'doctor' ? 'doctorsTrigger' : 'clinicsTrigger';
    updateTriggerLabel(triggerId, selectionSet, label);
}

function toggleSelection(type, id, element) {
    const set = type === 'doctor' ? selectedDoctors : selectedClinics;
    // Cast ID to correct type (usually int from backend, but string in HTML)
    id = parseInt(id); 

    if (set.has(id)) {
        set.delete(id);
        element.querySelector('input').checked = false;
    } else {
        set.add(id);
        element.querySelector('input').checked = true;
    }
    
    const label = type === 'doctor' ? 'Lekarze' : 'Placówki';
    const triggerId = type === 'doctor' ? 'doctorsTrigger' : 'clinicsTrigger';
    updateTriggerLabel(triggerId, set, label);
}

function updateTriggerLabel(elementId, set, baseLabel) {
    const count = set.size;
    const btn = document.getElementById(elementId);
    if (!btn) return;
    
    if (count === 0) btn.textContent = "Wybierz...";
    else btn.textContent = `${count} zaznaczonych`;
}

function clearSelection(listId) {
    const type = listId.includes('doctors') ? 'doctor' : 'clinic';
    const set = type === 'doctor' ? selectedDoctors : selectedClinics;
    set.clear();
    const triggerId = type === 'doctor' ? 'doctorsTrigger' : 'clinicsTrigger';
    const baseLabel = type === 'doctor' ? 'Lekarze' : 'Placówki';
    
    updateTriggerLabel(triggerId, set, baseLabel);
    
    // Uncheck all inputs
    document.querySelectorAll(`#${listId} input`).forEach(cb => cb.checked = false);
}

function toggleDropdown(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const wasOpen = el.classList.contains('open');
    // Close all others
    document.querySelectorAll('.custom-dropdown').forEach(d => d.classList.remove('open'));
    if (!wasOpen) el.classList.add('open');
}

function filterDropdown(input, listId) {
    const filter = input.value.toLowerCase();
    const items = document.getElementById(listId).getElementsByClassName('dropdown-item');
    for (let item of items) {
        const txt = item.textContent || item.innerText;
        item.style.display = txt.toLowerCase().indexOf(filter) > -1 ? "" : "none";
    }
}

// Weekdays Init
function initWeekdays() {
    const days = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Nd'];
    const container = document.getElementById('weekdaysContainer');
    if (!container) return;
    
    container.innerHTML = days.map((d, i) => `
        <label class="weekday-check">
            <input type="checkbox" checked value="${i+1}"> ${d}
        </label>
    `).join('');
}

function setDefaultDates() {
    const today = new Date().toISOString().split('T')[0];
    const nextMonth = new Date();
    nextMonth.setMonth(nextMonth.getMonth() + 1);
    const nextStr = nextMonth.toISOString().split('T')[0];
    
    const dFrom = document.getElementById('dateFrom');
    const dTo = document.getElementById('dateTo');
    
    if (dFrom) dFrom.value = today;
    if (dTo) dTo.value = nextStr;
}

// =========================
// SEARCH
// =========================
async function searchAppointments() {
    if (!currentProfile) { showToast('Brak wybranego profilu', 'error'); return; }

    const specVal = document.getElementById('specialtySelect').value;
    
    const preferredDays = Array.from(document.querySelectorAll('#weekdaysContainer input:checked'))
        .map(cb => parseInt(cb.value));

    // Time range logic: Desktop uses simple hours 4-19
    const hFrom = document.getElementById('hourFrom').value.padStart(2, '0') + ":00";
    const hTo = document.getElementById('hourTo').value.padStart(2, '0') + ":00";
    const dFrom = document.getElementById('dateFrom').value;
    
    // Prosta obsługa daty 'excluded' - na razie pusta, można rozwinąć
    
    const payload = {
        profile: currentProfile,
        specialty_ids: specVal ? specVal.split(',').map(Number) : [],
        doctor_ids: Array.from(selectedDoctors),
        clinic_ids: Array.from(selectedClinics),
        preferred_days: preferredDays,
        time_range: { start: hFrom, end: hTo },
        excluded_dates: [] 
    };

    const btn = document.getElementById('searchBtn');
    btn.textContent = 'Szukam...';
    btn.disabled = true;

    try {
        const resp = await fetch(`${API_URL}/api/v1/appointments/search`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(payload)
        });
        const data = await resp.json();
        
        if (data.success) {
            searchResults = data.data;
            renderResults();
            showToast(`Znaleziono: ${searchResults.length}`, 'success');
        } else {
            showToast('Błąd: ' + (data.error || data.message), 'error');
        }
    } catch (e) {
        showToast('Błąd połączenia', 'error');
        console.error(e);
    } finally {
        btn.textContent = 'Wyszukaj';
        btn.disabled = false;
    }
}

function renderResults() {
    const tbody = document.getElementById('resultsBody');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    if (searchResults.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Brak wyników</td></tr>';
        return;
    }

    searchResults.forEach((apt, index) => {
        const dateObj = new Date(apt.datetime || apt.visitDate); 
        const dateStr = dateObj.toLocaleDateString('pl-PL');
        const timeStr = dateObj.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'});
        
        const tr = document.createElement('tr');
        tr.onclick = () => selectRow(tr, apt);
        tr.innerHTML = `
            <td>${dateStr}</td>
            <td>${timeStr}</td>
            <td>${apt.doctor_name || apt.doctor?.name}</td>
            <td>${apt.specialty_name || apt.specialty?.name}</td>
            <td>${apt.clinic_name || apt.clinic?.name}</td>
        `;
        tbody.appendChild(tr);
    });
}

function selectRow(tr, apt) {
    document.querySelectorAll('.results-table tr').forEach(r => r.classList.remove('selected'));
    tr.classList.add('selected');
    selectedAppointment = apt;
    document.getElementById('bookSelectedBtn').disabled = false;
}

// =========================
// ACTIONS
// =========================
async function bookSelected() {
    if (!selectedAppointment) return;
    
    const docName = selectedAppointment.doctor_name || selectedAppointment.doctor?.name;
    const dateVal = selectedAppointment.datetime || selectedAppointment.visitDate;

    if (!confirm(`Czy na pewno chcesz zarezerwować wizytę?\n\nLekarz: ${docName}\nData: ${dateVal}`)) return;

    try {
        const resp = await fetch(`${API_URL}/api/v1/appointments/book`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({
                profile: currentProfile,
                appointment_id: selectedAppointment.id 
            })
        });
        const data = await resp.json();
        if (data.success) {
            showToast('Zarezerwowano pomyślnie!', 'success');
            // Remove from list
            searchResults = searchResults.filter(a => a.id !== selectedAppointment.id);
            renderResults();
            selectedAppointment = null;
            document.getElementById('bookSelectedBtn').disabled = true;
        } else {
            showToast('Błąd rezerwacji: ' + (data.message || data.error), 'error');
        }
    } catch (e) {
        showToast('Błąd krytyczny', 'error');
    }
}

function exportResults() {
    if (searchResults.length === 0) { showToast('Brak danych do eksportu', 'error'); return; }
    
    let csvContent = "Data,Godzina,Lekarz,Specjalnosc,Placowka\n";
    searchResults.forEach(row => {
        const d = new Date(row.datetime || row.visitDate);
        const date = d.toLocaleDateString();
        const time = d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        const doc = row.doctor_name || row.doctor?.name || '';
        const spec = row.specialty_name || row.specialty?.name || '';
        const clin = row.clinic_name || row.clinic?.name || '';
        csvContent += `${date},${time},"${doc}","${spec}","${clin}"\n`;
    });

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", "wyniki_medifinder.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function resetFilters() {
    const specSel = document.getElementById('specialtySelect');
    if (specSel) {
        specSel.value = "";
        handleSpecialtyChange(); // Resets doctors
    }
    clearSelection('doctorsList');
    clearSelection('clinicsList');
    setDefaultDates();
    // Reset checkboxes
    document.querySelectorAll('#weekdaysContainer input').forEach(cb => cb.checked = true);
    if (document.getElementById('hourFrom')) document.getElementById('hourFrom').value = 4;
    if (document.getElementById('hourTo')) document.getElementById('hourTo').value = 19;
}

// =========================
// UTILS
// =========================
function showToast(msg, type) {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.className = `toast show`;
    t.style.backgroundColor = type === 'error' ? '#dc3545' : '#28a745';
    setTimeout(() => t.classList.remove('show'), 3000);
}

function toggleProfilesModal() {
    const el = document.getElementById('profilesModal');
    if (!el) return;
    if (el.classList.contains('hidden')) el.classList.remove('hidden');
    else el.classList.add('hidden');
}

// Obsługa dodawania profilu
const addProfForm = document.getElementById('addProfileForm');
if (addProfForm) {
    addProfForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('newProfileName').value;
        const login = document.getElementById('newProfileLogin').value;
        const pass = document.getElementById('newProfilePass').value;

        try {
            const resp = await fetch(`${API_URL}/api/v1/profiles/add`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify({ name, login, password: pass })
            });
            const data = await resp.json();
            if (data.success) {
                showToast('Profil dodany', 'success');
                loadProfiles();
                e.target.reset();
            } else {
                showToast('Błąd: ' + data.error, 'error');
            }
        } catch (e) {
            console.error(e);
            showToast('Błąd połączenia', 'error');
        }
    });
}
