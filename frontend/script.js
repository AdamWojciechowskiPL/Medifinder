// Medifinder Web - Backend Scheduler Integration
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

// Status polling interval
let statusPollingInterval = null;
let resultsPollingInterval = null;

// =========================
// INIT & AUTH
// =========================
document.addEventListener('DOMContentLoaded', () => {
    initWeekdays();
    setDefaultDates();
    checkAuth();

    // Event Listeners for UI
    document.getElementById('specialtySelect').addEventListener('change', handleSpecialtyChange);
    document.getElementById('searchBtn').addEventListener('click', () => searchAppointments(false));
    document.getElementById('resetBtn').addEventListener('click', resetFilters);
    document.getElementById('bookSelectedBtn').addEventListener('click', bookSelected);
    document.getElementById('exportBtn').addEventListener('click', exportResults);
    
    // Cyclic Check Listeners - Now controls backend scheduler
    document.getElementById('enableAutoCheck').addEventListener('change', toggleBackendScheduler);
    document.getElementById('checkInterval').addEventListener('change', updateSchedulerInterval);
});

async function checkAuth() {
    try {
        const resp = await fetch(`${AUTH_URL}/me`, { credentials: 'include' });
        const data = await resp.json();
        
        if (data.authenticated) {
            document.getElementById('loginOverlay').style.display = 'none';
            document.getElementById('appContent').classList.remove('hidden');
            document.getElementById('userLabel').textContent = data.user.name || data.user.email;
            
            const authBtn = document.getElementById('authBtn');
            authBtn.textContent = 'Wyloguj';
            authBtn.onclick = logout;
            
            loadProfiles();
        } else {
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
            
            // NOWE: Załaduj ostatnie wyniki schedulera i sprawdź status
            await loadLastSchedulerResults();
            await checkSchedulerStatus();
        } else {
            toggleProfilesModal(); // Force create profile
        }
    } catch (e) {
        console.error("Error loading profiles:", e);
    }
}

async function loadDictionaries() {
    try {
        const specResp = await fetch(`${API_URL}/api/v1/dictionaries/specialties?profile=${currentProfile}`, { credentials: 'include' });
        const specData = await specResp.json();
        allSpecialties = specData.data || [];
        renderSpecialties();

        const docResp = await fetch(`${API_URL}/api/v1/dictionaries/doctors`, { credentials: 'include' });
        const docData = await docResp.json();
        allDoctors = docData.data || [];
        renderMultiSelect('doctorsList', allDoctors, selectedDoctors, 'doctor');

        const clinicResp = await fetch(`${API_URL}/api/v1/dictionaries/clinics`, { credentials: 'include' });
        const clinicData = await clinicResp.json();
        allClinics = clinicData.data || [];
        renderMultiSelect('clinicsList', allClinics, selectedClinics, 'clinic');
    } catch (e) {
        console.error("Error loading dictionaries:", e);
    }
}

// =========================
// NOWE: ŁADOWANIE OSTATNICH WYNIKÓW SCHEDULERA
// =========================
async function loadLastSchedulerResults() {
    if (!currentProfile) return;
    
    try {
        const resp = await fetch(`${API_URL}/api/v1/scheduler/results?profile=${currentProfile}`, {
            credentials: 'include'
        });
        const data = await resp.json();
        
        if (data.success && data.data && data.data.appointments) {
            const results = data.data;
            console.log(`📊 Załadowano ${results.count} ostatnich wyników z ${results.timestamp}`);
            
            // Renderuj wyniki
            searchResults = results.appointments;
            renderResults();
            
            // Pokaż info o źródle wyników
            const timestamp = new Date(results.timestamp);
            const timeStr = timestamp.toLocaleString('pl-PL', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
            
            const sourceEl = document.getElementById('resultsSource');
            if (sourceEl) {
                sourceEl.innerHTML = `🔄 Ostatnie wyniki z schedulera (${timeStr})`;
            }
            
            showToast(`Załadowano ${results.count} wizyt z ostatniego sprawdzenia`, 'success');
        }
    } catch (e) {
        console.error('Błąd ładowania ostatnich wyników:', e);
    }
}

// =========================
// UI LOGIC
// =========================
function updateProfileUI() {
    document.getElementById('currentProfileLabel').textContent = `${currentProfile}`;
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
    loadDictionaries();
    
    // Załaduj dane dla nowego profilu
    loadLastSchedulerResults();
    checkSchedulerStatus();
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
        renderMultiSelect('doctorsList', allDoctors, selectedDoctors, 'doctor');
        return;
    }

    const specIds = val.split(',').map(Number);
    const filteredDocs = allDoctors.filter(d => 
        d.specialty_ids.some(sid => specIds.includes(sid))
    );
    
    const validIds = new Set(filteredDocs.map(d => d.id));
    selectedDoctors = new Set([...selectedDoctors].filter(id => validIds.has(id)));
    
    renderMultiSelect('doctorsList', filteredDocs, selectedDoctors, 'doctor');
    updateTriggerLabel('doctorsTrigger', selectedDoctors, 'Lekarze');
}

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
    
    const triggerId = type === 'doctor' ? 'doctorsTrigger' : 'clinicsTrigger';
    const label = type === 'doctor' ? 'Lekarze' : 'Placówki';
    updateTriggerLabel(triggerId, selectionSet, label);
}

function toggleSelection(type, id, element) {
    const set = type === 'doctor' ? selectedDoctors : selectedClinics;
    id = parseInt(id); 

    if (set.has(id)) {
        set.delete(id);
        element.querySelector('input').checked = false;
    } else {
        set.add(id);
        element.querySelector('input').checked = true;
    }
    
    const triggerId = type === 'doctor' ? 'doctorsTrigger' : 'clinicsTrigger';
    const label = type === 'doctor' ? 'Lekarze' : 'Placówki';
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
    document.querySelectorAll(`#${listId} input`).forEach(cb => cb.checked = false);
}

function toggleDropdown(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const wasOpen = el.classList.contains('open');
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

function initWeekdays() {
    const days = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Nd'];
    const container = document.getElementById('weekdaysContainer');
    if (!container) return;
    
    container.innerHTML = days.map((d, i) => `
        <label class="weekday-check">
            <input type="checkbox" checked value="${i}"> ${d}
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
// BACKEND SCHEDULER CONTROL
// =========================

async function toggleBackendScheduler() {
    const checkbox = document.getElementById('enableAutoCheck');
    const enabled = checkbox.checked;
    
    if (enabled) {
        await startBackendScheduler();
    } else {
        await stopBackendScheduler();
    }
}

async function updateSchedulerInterval() {
    // If scheduler is running, restart it with new interval
    const checkbox = document.getElementById('enableAutoCheck');
    if (checkbox.checked) {
        await startBackendScheduler();
    }
}

async function startBackendScheduler() {
    if (!currentProfile) {
        showToast('Wybierz profil przed uruchomieniem', 'error');
        document.getElementById('enableAutoCheck').checked = false;
        return;
    }
    
    const specVal = document.getElementById('specialtySelect').value;
    const preferredDays = Array.from(document.querySelectorAll('#weekdaysContainer input:checked'))
        .map(cb => parseInt(cb.value));
    const hFrom = document.getElementById('hourFrom').value.padStart(2, '0') + ":00";
    const hTo = document.getElementById('hourTo').value.padStart(2, '0') + ":00";
    const intervalMin = parseInt(document.getElementById('checkInterval').value) || 5;
    const autoBook = document.getElementById('autoBook').checked;
    
    const payload = {
        profile: currentProfile,
        specialty_ids: specVal ? specVal.split(',').map(Number) : [],
        doctor_ids: Array.from(selectedDoctors),
        clinic_ids: Array.from(selectedClinics),
        preferred_days: preferredDays,
        time_range: { start: hFrom, end: hTo },
        excluded_dates: [],
        interval_minutes: intervalMin,
        auto_book: autoBook
    };
    
    try {
        const resp = await fetch(`${API_URL}/api/v1/scheduler/start`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(payload)
        });
        
        const data = await resp.json();
        
        if (data.success) {
            showToast(`✅ Zadanie uruchomione (co ${intervalMin} min)`, 'success');
            
            // Update UI
            document.getElementById('enableAutoCheck').checked = true;
            const statusEl = document.getElementById('autoCheckStatus');
            statusEl.textContent = `Włączone (co ${intervalMin} min)`;
            statusEl.style.color = 'green';
            statusEl.style.fontWeight = 'bold';
            
            // Update auto-book status
            const autoBookStatusEl = document.getElementById('autoBookStatus');
            if (autoBook) {
                autoBookStatusEl.textContent = 'Włączona';
                autoBookStatusEl.style.color = 'green';
                autoBookStatusEl.style.fontWeight = 'bold';
            } else {
                autoBookStatusEl.textContent = 'Wyłączona';
                autoBookStatusEl.style.color = 'black';
                autoBookStatusEl.style.fontWeight = 'normal';
            }
            
            // Start polling for status updates
            startStatusPolling();
            startResultsPolling();
        } else {
            showToast('Błąd: ' + (data.error || data.message), 'error');
            document.getElementById('enableAutoCheck').checked = false;
        }
    } catch (e) {
        showToast('Błąd połączenia z serwerem', 'error');
        console.error(e);
        document.getElementById('enableAutoCheck').checked = false;
    }
}

async function stopBackendScheduler() {
    if (!currentProfile) return;
    
    try {
        const resp = await fetch(`${API_URL}/api/v1/scheduler/stop`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({ profile: currentProfile })
        });
        
        const data = await resp.json();
        
        if (data.success) {
            showToast('Zadanie zatrzymane', 'success');
            
            // Update UI
            document.getElementById('enableAutoCheck').checked = false;
            const statusEl = document.getElementById('autoCheckStatus');
            statusEl.textContent = 'Wyłączone';
            statusEl.style.color = 'black';
            statusEl.style.fontWeight = 'normal';
            
            // Hide details
            document.getElementById('schedulerDetailsRow').style.display = 'none';
            
            // Stop polling
            stopStatusPolling();
            stopResultsPolling();
        } else {
            showToast('Błąd zatrzymywania: ' + (data.error || data.message), 'error');
        }
    } catch (e) {
        showToast('Błąd połączenia z serwerem', 'error');
        console.error(e);
    }
}

async function checkSchedulerStatus() {
    if (!currentProfile) return;
    
    try {
        const resp = await fetch(`${API_URL}/api/v1/scheduler/status?profile=${currentProfile}`, {
            credentials: 'include'
        });
        
        const data = await resp.json();
        
        if (data.success && data.data) {
            const status = data.data;
            
            // Update UI based on backend status
            if (status.active) {
                document.getElementById('enableAutoCheck').checked = true;
                
                const statusEl = document.getElementById('autoCheckStatus');
                const intervalMin = status.interval_minutes || 5;
                
                // Calculate time until next run
                if (status.next_run) {
                    const nextRun = new Date(status.next_run);
                    const now = new Date();
                    const diff = nextRun - now;
                    
                    if (diff > 0) {
                        const min = Math.floor(diff / 60000);
                        const sec = Math.floor((diff % 60000) / 1000);
                        statusEl.textContent = `Następne za ${min}:${sec.toString().padStart(2, '0')}`;
                    } else {
                        statusEl.textContent = 'Sprawdzanie...';
                    }
                } else {
                    statusEl.textContent = `Włączone (co ${intervalMin} min)`;
                }
                
                statusEl.style.color = 'green';
                statusEl.style.fontWeight = 'bold';
                
                // NOWE: Pokaż szczegółowy status
                updateSchedulerDetails(status);
                
                // Update auto-book status
                const autoBookStatusEl = document.getElementById('autoBookStatus');
                if (status.auto_book) {
                    autoBookStatusEl.textContent = 'Włączona';
                    autoBookStatusEl.style.color = 'green';
                    autoBookStatusEl.style.fontWeight = 'bold';
                }
                
                // Start polling if not already running
                if (!statusPollingInterval) {
                    startStatusPolling();
                    startResultsPolling();
                }
            } else {
                // Inactive
                document.getElementById('enableAutoCheck').checked = false;
                document.getElementById('autoCheckStatus').textContent = 'Wyłączone';
                document.getElementById('autoCheckStatus').style.color = 'black';
                document.getElementById('autoCheckStatus').style.fontWeight = 'normal';
                document.getElementById('schedulerDetailsRow').style.display = 'none';
            }
        }
    } catch (e) {
        console.error('Error checking scheduler status:', e);
    }
}

function updateSchedulerDetails(status) {
    const detailsRow = document.getElementById('schedulerDetailsRow');
    const detailsEl = document.getElementById('schedulerDetails');
    
    if (!detailsRow || !detailsEl) return;
    
    let html = '<div style="display: flex; flex-direction: column; gap: 3px;">';
    
    // Ostatnie sprawdzenie
    if (status.last_run) {
        const lastRun = new Date(status.last_run);
        const timeStr = lastRun.toLocaleString('pl-PL', {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
        html += `<span>🕒 Ostatnie: ${timeStr}</span>`;
    }
    
    // Liczba wykonań
    if (status.runs_count !== undefined) {
        html += `<span>🔢 Wykonań: ${status.runs_count}</span>`;
    }
    
    // Ostatnie wyniki
    if (status.last_results) {
        const resTime = new Date(status.last_results.timestamp);
        const resTimeStr = resTime.toLocaleString('pl-PL', {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
        html += `<span>📊 Ostatnie wyniki: ${status.last_results.count} wizyt (${resTimeStr})</span>`;
    }
    
    // Ostatni błąd
    if (status.last_error) {
        const errTime = new Date(status.last_error.timestamp);
        const errTimeStr = errTime.toLocaleTimeString('pl-PL', {
            hour: '2-digit',
            minute: '2-digit'
        });
        html += `<span style="color: #dc3545;">⚠️ Błąd: ${status.last_error.error.substring(0, 50)} (${errTimeStr})</span>`;
    }
    
    html += '</div>';
    
    detailsEl.innerHTML = html;
    detailsRow.style.display = 'block';
}

function startStatusPolling() {
    // Poll every 5 seconds to update countdown
    if (statusPollingInterval) clearInterval(statusPollingInterval);
    
    statusPollingInterval = setInterval(() => {
        checkSchedulerStatus();
    }, 5000);
}

function stopStatusPolling() {
    if (statusPollingInterval) {
        clearInterval(statusPollingInterval);
        statusPollingInterval = null;
    }
}

function startResultsPolling() {
    // Poll every 30 seconds to load new results
    if (resultsPollingInterval) clearInterval(resultsPollingInterval);
    
    resultsPollingInterval = setInterval(() => {
        loadLastSchedulerResults();
    }, 30000);
}

function stopResultsPolling() {
    if (resultsPollingInterval) {
        clearInterval(resultsPollingInterval);
        resultsPollingInterval = null;
    }
}

// =========================
// SEARCH & APPOINTMENTS
// =========================

async function searchAppointments(isBackground = false) {
    if (!currentProfile) { 
        if (!isBackground) showToast('Brak wybranego profilu', 'error'); 
        return []; 
    }

    const specVal = document.getElementById('specialtySelect').value;
    const preferredDays = Array.from(document.querySelectorAll('#weekdaysContainer input:checked'))
        .map(cb => parseInt(cb.value));
    const hFrom = document.getElementById('hourFrom').value.padStart(2, '0') + ":00";
    const hTo = document.getElementById('hourTo').value.padStart(2, '0') + ":00";
    
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
    if (!isBackground) {
        btn.textContent = 'Szukam...';
        btn.disabled = true;
    }

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
            
            // Wyczyść info o źródle - to są świeże wyniki
            const sourceEl = document.getElementById('resultsSource');
            if (sourceEl) sourceEl.innerHTML = '';
            
            if (!isBackground) showToast(`Znaleziono: ${searchResults.length}`, 'success');
            return searchResults;
        } else {
            if (!isBackground) showToast('Błąd: ' + (data.error || data.message), 'error');
            return [];
        }
    } catch (e) {
        if (!isBackground) showToast('Błąd połączenia', 'error');
        console.error(e);
        return [];
    } finally {
        if (!isBackground) {
            btn.textContent = 'Wyszukaj';
            btn.disabled = false;
        }
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
        let dateObj = null;
        const datetime_str = apt.appointmentDate || ""; 
        
        if (datetime_str) {
             const clean_str = datetime_str.replace('Z', '+00:00');
             dateObj = new Date(clean_str);
        }

        const dateStr = (dateObj && !isNaN(dateObj)) ? dateObj.toLocaleDateString('pl-PL') : 'Błąd daty';
        const timeStr = (dateObj && !isNaN(dateObj)) ? dateObj.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'}) : '--:--';
        
        const doctorName = apt.doctor && apt.doctor.name ? apt.doctor.name : "Nieznany lekarz";
        const specialtyName = apt.specialty && apt.specialty.name ? apt.specialty.name : "Nieznana specjalność";
        const clinicName = apt.clinic && apt.clinic.name ? apt.clinic.name : "Nieznana placówka";

        const tr = document.createElement('tr');
        tr.onclick = () => selectRow(tr, apt);
        tr.innerHTML = `
            <td>${dateStr}</td>
            <td>${timeStr}</td>
            <td>${doctorName}</td>
            <td>${specialtyName}</td>
            <td>${clinicName}</td>
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
    await performBooking(selectedAppointment, false);
}

async function performBooking(appointment, silent = false) {
    const docName = appointment.doctor && appointment.doctor.name ? appointment.doctor.name : "Nieznany";
    
    let dateObj = null;
    const datetime_str = appointment.appointmentDate || "";
    if (datetime_str) {
         const clean_str = datetime_str.replace('Z', '+00:00');
         dateObj = new Date(clean_str);
    }
    const dateVal = (dateObj && !isNaN(dateObj)) ? dateObj.toLocaleString('pl-PL') : "Nieznana data";

    if (!silent) {
        if (!confirm(`Czy na pewno chcesz zarezerwować wizytę?\n\nLekarz: ${docName}\nData: ${dateVal}`)) return false;
    }

    const bookingString = appointment.bookingString;
    const aptId = appointment.appointmentId || appointment.id;

    if (!bookingString) {
        if (!silent) showToast('Błąd: Brak bookingString', 'error');
        return false;
    }

    try {
        const resp = await fetch(`${API_URL}/api/v1/appointments/book`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({
                profile: currentProfile,
                appointment_id: aptId,
                booking_string: bookingString
            })
        });
        const data = await resp.json();
        if (data.success) {
            if (!silent) showToast('Zarezerwowano pomyślnie!', 'success');
            searchResults = searchResults.filter(a => a !== appointment);
            renderResults();
            selectedAppointment = null;
            document.getElementById('bookSelectedBtn').disabled = true;
            return true;
        } else {
            if (!silent) showToast('Błąd rezerwacji: ' + (data.message || data.error), 'error');
            return false;
        }
    } catch (e) {
        if (!silent) showToast('Błąd krytyczny', 'error');
        console.error(e);
        return false;
    }
}

function exportResults() {
    if (searchResults.length === 0) { showToast('Brak danych do eksportu', 'error'); return; }
    
    let csvContent = "Data,Godzina,Lekarz,Specjalnosc,Placowka\n";
    searchResults.forEach(row => {
        let dateObj = null;
        const datetime_str = row.appointmentDate || "";
        if (datetime_str) {
             const clean_str = datetime_str.replace('Z', '+00:00');
             dateObj = new Date(clean_str);
        }

        const date = (dateObj && !isNaN(dateObj)) ? dateObj.toLocaleDateString() : "";
        const time = (dateObj && !isNaN(dateObj)) ? dateObj.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : "";
        
        const doc = row.doctor && row.doctor.name ? row.doctor.name : "";
        const spec = row.specialty && row.specialty.name ? row.specialty.name : "";
        const clin = row.clinic && row.clinic.name ? row.clinic.name : "";
        
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
        handleSpecialtyChange(); 
    }
    clearSelection('doctorsList');
    clearSelection('clinicsList');
    setDefaultDates();
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

const addProfForm = document.getElementById('addProfileForm');
if (addProfForm) {
    addProfForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('newProfileName').value;
        const login = document.getElementById('newProfileLogin').value;
        const pass = document.getElementById('newProfilePass').value;
        const isChild = document.getElementById('newProfileIsChild').checked;

        try {
            const resp = await fetch(`${API_URL}/api/v1/profiles/add`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify({ 
                    name, 
                    login, 
                    password: pass,
                    is_child_account: isChild 
                })
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