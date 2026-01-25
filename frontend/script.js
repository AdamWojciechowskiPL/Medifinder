// Medifinder - Appointment Finder
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

// Advanced Filters State
let excludedDates = new Set();
let dayTimeRanges = {}; // { 0: {start: "16:00", end: "20:00"}, 1: ... }

// Status polling interval
let statusPollingInterval = null;
let resultsPollingInterval = null;

// =========================
// UTILITY: UTC TO LOCAL TIME CONVERSION
// =========================
function utcToLocal(utcDateString) {
    if (!utcDateString) return null;
    let dateStr = utcDateString;
    if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('T')) {
        dateStr = dateStr + 'Z';
    } else if (dateStr.includes('T') && !dateStr.endsWith('Z') && !dateStr.includes('+')) {
        dateStr = dateStr + 'Z';
    }
    const date = new Date(dateStr);
    return date;
}

function formatLocalDateTime(utcDateString) {
    const date = utcToLocal(utcDateString);
    if (!date || isNaN(date)) return 'Nieznana data';
    return date.toLocaleString('pl-PL', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatLocalDate(utcDateString) {
    const date = utcToLocal(utcDateString);
    if (!date || isNaN(date)) return 'Błąd daty';
    return date.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function formatLocalTime(utcDateString) {
    const date = utcToLocal(utcDateString);
    if (!date || isNaN(date)) return '--:--';
    return date.toLocaleTimeString('pl-PL', { hour:'2-digit', minute:'2-digit' });
}

function getDateRangeFromUI() {
    const dFromEl = document.getElementById('dateFrom');
    const dToEl = document.getElementById('dateTo');
    const dateFrom = dFromEl ? (dFromEl.value || null) : null;
    const dateTo = dToEl ? (dToEl.value || null) : null;
    if (dateFrom && dateTo && dateFrom > dateTo) {
        return { valid: false, dateFrom, dateTo };
    }
    return { valid: true, dateFrom, dateTo };
}

// =========================
// INIT & AUTH
// =========================
document.addEventListener('DOMContentLoaded', () => {
    initWeekdays();
    setDefaultDates();
    checkAuth();
    initAdvancedFiltersUI();

    document.getElementById('specialtySelect').addEventListener('change', handleSpecialtyChange);
    document.getElementById('searchBtn').addEventListener('click', () => searchAppointments(false));
    document.getElementById('resetBtn').addEventListener('click', resetFilters);
    document.getElementById('bookSelectedBtn').addEventListener('click', bookSelected);
    document.getElementById('exportBtn').addEventListener('click', exportResults);
    
    document.getElementById('enableAutoCheck').addEventListener('change', toggleBackendScheduler);
    document.getElementById('checkInterval').addEventListener('change', updateSchedulerInterval);
    document.getElementById('autoBook').addEventListener('change', handleAutoBookToggle);

    const dFrom = document.getElementById('dateFrom');
    const dTo = document.getElementById('dateTo');
    if (dFrom) dFrom.addEventListener('change', updateSchedulerInterval);
    if (dTo) dTo.addEventListener('change', updateSchedulerInterval);
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
    } catch (e) { console.error('Auth check error:', e); }
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
            currentProfile = profiles[0];
            updateProfileUI();
            await loadDictionaries();
            await loadLastSchedulerResults();
            await checkSchedulerStatus();
        } else {
            toggleProfilesModal();
        }
    } catch (e) { console.error("Error loading profiles:", e); }
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
        
        restoreLastSearch();
    } catch (e) { console.error("Error loading dictionaries:", e); }
}

// =========================
// ADVANCED FILTERS UI
// =========================
function initAdvancedFiltersUI() {
    // Excluded Dates
    document.getElementById('addExcludedDateBtn').addEventListener('click', () => {
        const input = document.getElementById('excludeDateInput');
        const date = input.value;
        if (date) {
            if (excludedDates.has(date)) {
                showToast('Ta data jest już wykluczona', 'error');
                return;
            }
            excludedDates.add(date);
            renderExcludedDates();
            input.value = '';
            updateSchedulerInterval(); // Refresh if active
        }
    });

    // Per-day time ranges
    // Generate UI for each day
    const days = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Nd'];
    const container = document.getElementById('dayTimeRangesContainer');
    if (container) {
        container.innerHTML = days.map((d, i) => `
            <div class="day-range-row">
                <div style="width: 40px; font-weight: 500;">${d}</div>
                <input type="time" class="form-control form-control-sm" id="dayStart_${i}" placeholder="Od" onchange="updateDayTimeRange(${i})">
                <span style="margin: 0 4px;">-</span>
                <input type="time" class="form-control form-control-sm" id="dayEnd_${i}" placeholder="Do" onchange="updateDayTimeRange(${i})">
                <button class="btn btn-sm btn-outline-danger" style="margin-left: 8px; padding: 0 6px;" onclick="clearDayTimeRange(${i})">×</button>
            </div>
        `).join('');
    }
    
    // Toggle visibility
    document.getElementById('toggleAdvancedFilters').addEventListener('click', () => {
        const panel = document.getElementById('advancedFiltersPanel');
        if (panel.classList.contains('hidden')) {
            panel.classList.remove('hidden');
            document.getElementById('toggleAdvancedFilters').textContent = 'Mniej opcji ▲';
        } else {
            panel.classList.add('hidden');
            document.getElementById('toggleAdvancedFilters').textContent = 'Więcej opcji (wykluczenia, godziny dniowe) ▼';
        }
    });
}

function renderExcludedDates() {
    const container = document.getElementById('excludedDatesList');
    if (!container) return;
    
    if (excludedDates.size === 0) {
        container.innerHTML = '<span style="color: #6b7280; font-size: 0.85rem;">Brak wykluczonych dat</span>';
        return;
    }
    
    const sorted = Array.from(excludedDates).sort();
    container.innerHTML = sorted.map(d => `
        <span class="badge badge-danger">
            ${d} <span style="cursor:pointer; margin-left:4px;" onclick="removeExcludedDate('${d}')">×</span>
        </span>
    `).join('');
}

function removeExcludedDate(date) {
    excludedDates.delete(date);
    renderExcludedDates();
    updateSchedulerInterval();
}

function updateDayTimeRange(dayIndex) {
    const start = document.getElementById(`dayStart_${dayIndex}`).value;
    const end = document.getElementById(`dayEnd_${dayIndex}`).value;
    
    if (start || end) {
        dayTimeRanges[dayIndex] = {
            start: start || "00:00",
            end: end || "23:59"
        };
    } else {
        delete dayTimeRanges[dayIndex];
    }
    updateSchedulerInterval();
}

function clearDayTimeRange(dayIndex) {
    document.getElementById(`dayStart_${dayIndex}`).value = '';
    document.getElementById(`dayEnd_${dayIndex}`).value = '';
    delete dayTimeRanges[dayIndex];
    updateSchedulerInterval();
}

// =========================
// STATE PERSISTENCE
// =========================
function restoreLastSearch() {
    const saved = localStorage.getItem('medifinder_last_search');
    if (!saved) return;
    try {
        const state = JSON.parse(saved);
        if (state.specialty) {
            const sel = document.getElementById('specialtySelect');
            if (sel && allSpecialties.some(s => s.ids.join(',') === state.specialty)) sel.value = state.specialty;
        }
        if (state.doctors) selectedDoctors = new Set(state.doctors);
        if (state.clinics) selectedClinics = new Set(state.clinics);
        
        handleSpecialtyChange();
        renderMultiSelect('clinicsList', allClinics, selectedClinics, 'clinic');
        
        // Restore advanced filters
        if (state.excludedDates) {
            excludedDates = new Set(state.excludedDates);
            renderExcludedDates();
        }
        
        if (state.dayTimeRanges) {
            dayTimeRanges = state.dayTimeRanges;
            // Update UI
            Object.entries(dayTimeRanges).forEach(([day, range]) => {
                const startEl = document.getElementById(`dayStart_${day}`);
                const endEl = document.getElementById(`dayEnd_${day}`);
                if (startEl) startEl.value = range.start;
                if (endEl) endEl.value = range.end;
            });
        }

        if (state.results && state.results.length > 0) {
            searchResults = state.results;
            renderResults();
        }
    } catch (e) { console.error("Error restoring state", e); }
}

// =========================
// BACKEND SCHEDULER CONTROL
// =========================
async function loadLastSchedulerResults() {
    if (!currentProfile || searchResults.length > 0) return;
    try {
        const resp = await fetch(`${API_URL}/api/v1/scheduler/results?profile=${currentProfile}`, { credentials: 'include' });
        const data = await resp.json();
        if (data.success && data.data && data.data.appointments) {
            searchResults = data.data.appointments;
            renderResults();
            const timeStr = formatLocalDateTime(data.data.timestamp);
            const sourceEl = document.getElementById('resultsSource');
            if (sourceEl) sourceEl.innerHTML = `🔄 Ostatnie wyniki z schedulera (${timeStr})`;
            showToast(`Załadowano ${data.data.count} wizyt z ostatniego sprawdzenia`, 'success');
        }
    } catch (e) { console.error('Błąd ładowania ostatnich wyników:', e); }
}

async function toggleBackendScheduler() {
    const checkbox = document.getElementById('enableAutoCheck');
    const enabled = checkbox.checked;
    
    const specVal = document.getElementById('specialtySelect').value;
    if (enabled && !specVal) {
        showToast('Wybierz specjalność przed uruchomieniem schedulera', 'error');
        checkbox.checked = false;
        return;
    }
    const dr = getDateRangeFromUI();
    if (enabled && !dr.valid) {
        showToast('Nieprawidłowy zakres dat', 'error');
        checkbox.checked = false;
        return;
    }
    
    if (enabled) await startBackendScheduler();
    else await stopBackendScheduler();
}

async function updateSchedulerInterval() {
    const checkbox = document.getElementById('enableAutoCheck');
    if (checkbox.checked) await startBackendScheduler();
}

async function handleAutoBookToggle() {
    const checkbox = document.getElementById('enableAutoCheck');
    if (checkbox.checked) await startBackendScheduler();
}

async function startBackendScheduler() {
    if (!currentProfile) return;
    const specVal = document.getElementById('specialtySelect').value;
    if (!specVal) return;
    const dr = getDateRangeFromUI();
    
    const preferredDays = Array.from(document.querySelectorAll('#weekdaysContainer input:checked')).map(cb => parseInt(cb.value));
    const hFrom = document.getElementById('hourFrom').value.padStart(2, '0') + ":00";
    const hTo = document.getElementById('hourTo').value.padStart(2, '0') + ":00";
    const intervalMin = parseInt(document.getElementById('checkInterval').value) || 5;
    const autoBook = document.getElementById('autoBook').checked;
    
    const payload = {
        profile: currentProfile,
        specialty_ids: specVal.split(',').map(Number),
        doctor_ids: Array.from(selectedDoctors),
        clinic_ids: Array.from(selectedClinics),
        preferred_days: preferredDays,
        time_range: { start: hFrom, end: hTo },
        
        // NEW PARAMS
        day_time_ranges: dayTimeRanges,
        excluded_dates: Array.from(excludedDates),
        
        start_date: dr.dateFrom,
        end_date: dr.dateTo,
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
            showToast(`✅ Scheduler uruchomiony (co ${intervalMin} min)`, 'success');
            document.getElementById('enableAutoCheck').checked = true;
            document.getElementById('autoCheckStatus').textContent = `Aktywny (co ${intervalMin} min)`;
            document.getElementById('autoCheckStatus').style.color = 'var(--success)';
            startStatusPolling();
            startResultsPolling();
        } else {
            showToast('Błąd: ' + (data.error || data.message), 'error');
            document.getElementById('enableAutoCheck').checked = false;
        }
    } catch (e) {
        showToast('Błąd połączenia z serwerem', 'error');
        document.getElementById('enableAutoCheck').checked = false;
    }
}

async function stopBackendScheduler() {
    if (!currentProfile) return;
    try {
        await fetch(`${API_URL}/api/v1/scheduler/stop`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({ profile: currentProfile })
        });
        showToast('Scheduler zatrzymany', 'success');
        document.getElementById('enableAutoCheck').checked = false;
        document.getElementById('autoCheckStatus').textContent = 'Wyłączony';
        document.getElementById('autoCheckStatus').style.color = 'var(--dark)';
        stopStatusPolling();
        stopResultsPolling();
    } catch (e) { showToast('Błąd połączenia', 'error'); }
}

async function checkSchedulerStatus() {
    if (!currentProfile) return;
    try {
        const resp = await fetch(`${API_URL}/api/v1/scheduler/status?profile=${currentProfile}`, { credentials: 'include' });
        const data = await resp.json();
        if (data.success && data.data) {
            const status = data.data;
            if (status.active) {
                document.getElementById('enableAutoCheck').checked = true;
                document.getElementById('autoCheckStatus').textContent = `Aktywny (co ${status.interval_minutes} min)`;
                document.getElementById('autoCheckStatus').style.color = 'var(--success)';
                
                // Update Advanced Filters from status if not set locally? 
                // Maybe better to keep local state as source of truth for edit
                
                updateSchedulerDetails(status);
                if (!statusPollingInterval) { startStatusPolling(); startResultsPolling(); }
            } else {
                document.getElementById('enableAutoCheck').checked = false;
                document.getElementById('autoCheckStatus').textContent = 'Wyłączony';
                document.getElementById('autoCheckStatus').style.color = 'var(--dark)';
            }
            validateAutoCheckEnabled();
        }
    } catch (e) { console.error('Error checking scheduler status:', e); }
}

function updateSchedulerDetails(status) {
    const detailsRow = document.getElementById('schedulerDetailsRow');
    const detailsEl = document.getElementById('schedulerDetails');
    if (!detailsRow || !detailsEl) return;
    
    let html = '<div style="display: flex; flex-direction: column; gap: 6px;">';
    if (status.last_run) html += `<span>🕒 Ostatnie: ${formatLocalDateTime(status.last_run)}</span>`;
    if (status.runs_count !== undefined) html += `<span>🔢 Wykonań: ${status.runs_count}</span>`;
    if (status.last_results) html += `<span>📊 Wyniki: ${status.last_results.count} wizyt</span>`;
    if (status.last_error) html += `<span style="color:var(--danger);">⚠️ Błąd: ${status.last_error.error.substring(0,30)}...</span>`;
    html += '</div>';
    detailsEl.innerHTML = html;
    detailsRow.style.display = 'block';
}

function startStatusPolling() {
    if (statusPollingInterval) clearInterval(statusPollingInterval);
    statusPollingInterval = setInterval(() => checkSchedulerStatus(), 5000);
}
function stopStatusPolling() {
    if (statusPollingInterval) { clearInterval(statusPollingInterval); statusPollingInterval = null; }
}
function startResultsPolling() {
    if (resultsPollingInterval) clearInterval(resultsPollingInterval);
    resultsPollingInterval = setInterval(() => loadLastSchedulerResults(), 30000);
}
function stopResultsPolling() {
    if (resultsPollingInterval) { clearInterval(resultsPollingInterval); resultsPollingInterval = null; }
}

// =========================
// SEARCH
// =========================
async function searchAppointments(isBackground = false) {
    if (!currentProfile) { if(!isBackground) showToast('Wybierz profil', 'error'); return []; }
    const specVal = document.getElementById('specialtySelect').value;
    if (!specVal) { if(!isBackground) showToast('Wybierz specjalność', 'error'); return []; }
    const dr = getDateRangeFromUI();
    if (!dr.valid) { if(!isBackground) showToast('Błąd dat', 'error'); return []; }

    const preferredDays = Array.from(document.querySelectorAll('#weekdaysContainer input:checked')).map(cb => parseInt(cb.value));
    const hFrom = document.getElementById('hourFrom').value.padStart(2, '0') + ":00";
    const hTo = document.getElementById('hourTo').value.padStart(2, '0') + ":00";
    
    const payload = {
        profile: currentProfile,
        specialty_ids: specVal.split(',').map(Number),
        doctor_ids: Array.from(selectedDoctors),
        clinic_ids: Array.from(selectedClinics),
        preferred_days: preferredDays,
        time_range: { start: hFrom, end: hTo },
        
        // NEW PARAMS
        day_time_ranges: dayTimeRanges,
        excluded_dates: Array.from(excludedDates),
        
        start_date: dr.dateFrom,
        end_date: dr.dateTo
    };

    const btn = document.getElementById('searchBtn');
    if (!isBackground) { btn.textContent = '🔍 Szukam...'; btn.disabled = true; }

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
            if (!isBackground) showToast(`✅ Znaleziono: ${searchResults.length}`, 'success');
            
            // Save state
            const state = {
                profile: currentProfile,
                specialty: specVal,
                doctors: Array.from(selectedDoctors),
                clinics: Array.from(selectedClinics),
                excludedDates: Array.from(excludedDates),
                dayTimeRanges: dayTimeRanges,
                results: searchResults,
                timestamp: new Date().getTime()
            };
            localStorage.setItem('medifinder_last_search', JSON.stringify(state));
            
            return searchResults;
        } else {
            if (!isBackground) showToast('Błąd: ' + data.error, 'error');
            return [];
        }
    } catch (e) {
        if (!isBackground) showToast('Błąd połączenia', 'error');
        return [];
    } finally {
        if (!isBackground) { btn.textContent = '🔍 Wyszukaj'; btn.disabled = false; }
    }
}

// ... (renderResults, bookSelected, performBooking, exportResults, resetFilters, UI utils - same as before) ...
function renderResults() {
    const tbody = document.getElementById('resultsBody');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (searchResults.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 40px; color: #6b7280;">Brak wyników</td></tr>`;
        return;
    }
    searchResults.forEach(apt => {
        const tr = document.createElement('tr');
        tr.onclick = () => selectRow(tr, apt);
        tr.innerHTML = `
            <td>${formatLocalDate(apt.appointmentDate)}</td>
            <td><strong>${formatLocalTime(apt.appointmentDate)}</strong></td>
            <td>${apt.doctor?.name || "Nieznany"}</td>
            <td>${apt.specialty?.name || "Specjalność"}</td>
            <td>${apt.clinic?.name || "Placówka"}</td>
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
async function bookSelected() { if(selectedAppointment) performBooking(selectedAppointment, false); }
async function performBooking(appointment, silent) {
    if (!silent && !confirm('Rezerwować?')) return;
    const bookingString = appointment.bookingString;
    const aptId = appointment.appointmentId || appointment.id;
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
            if(!silent) showToast('✅ Zarezerwowano!', 'success');
            searchResults = searchResults.filter(a => a !== appointment);
            renderResults();
        } else {
            if(!silent) showToast('Błąd: ' + data.message, 'error');
        }
    } catch (e) { if(!silent) showToast('Błąd', 'error'); }
}
function exportResults() { /* simplified */ }
function resetFilters() {
    const specSel = document.getElementById('specialtySelect');
    if (specSel) { specSel.value = ""; handleSpecialtyChange(); }
    selectedDoctors.clear(); selectedClinics.clear();
    excludedDates.clear(); dayTimeRanges = {};
    renderExcludedDates();
    if(document.getElementById('dayTimeRangesContainer')) document.getElementById('dayTimeRangesContainer').innerHTML = '';
    initAdvancedFiltersUI(); // Re-init day ranges UI
    setDefaultDates();
    showToast('Wyczyszczono', 'success');
}
function showToast(msg, type) {
    const t = document.getElementById('toast');
    if (t) {
        t.textContent = msg; t.className = `toast show`; t.style.backgroundColor = type === 'error' ? 'var(--danger)' : 'var(--success)';
        setTimeout(() => t.classList.remove('show'), 3500);
    }
}
function updateProfileUI() { document.getElementById('currentProfileLabel').textContent = `${currentProfile}`; }
function toggleProfilesModal() { document.getElementById('profilesModal').classList.toggle('hidden'); }
function handleSpecialtyChange() {
    const val = document.getElementById('specialtySelect').value;
    validateAutoCheckEnabled();
    if (!val) { renderMultiSelect('doctorsList', allDoctors, selectedDoctors, 'doctor'); return; }
    const specIds = val.split(',').map(Number);
    const filteredDocs = allDoctors.filter(d => d.specialty_ids.some(sid => specIds.includes(sid)));
    selectedDoctors = new Set([...selectedDoctors].filter(id => new Set(filteredDocs.map(d => d.id)).has(id)));
    renderMultiSelect('doctorsList', filteredDocs, selectedDoctors, 'doctor');
    updateTriggerLabel('doctorsTrigger', selectedDoctors, 'Lekarze');
}
function validateAutoCheckEnabled() {
    const specVal = document.getElementById('specialtySelect').value;
    const checkbox = document.getElementById('enableAutoCheck');
    if (!specVal) { checkbox.disabled = true; checkbox.checked = false; } else { checkbox.disabled = false; }
}
function renderMultiSelect(elId, items, set, type) { /* ... */ }
function updateTriggerLabel(elId, set, label) { /* ... */ }
function initWeekdays() { /* ... */ }
function setDefaultDates() { /* ... */ }
