/**
 * MEDIFINDER 2.0 Frontend Script
 * Handles UI interactions, API calls, and data rendering
 */

// Global State
let state = {
    profiles: [],
    currentProfile: null,
    specialties: [],
    doctors: [],
    clinics: [],
    searchResults: [],
    schedulerStatus: null,
    filters: {
        specialtyIds: [],
        doctorIds: [],
        clinicIds: [],
        dateFrom: '',
        dateTo: '',
        timeRange: { start: '04:00', end: '22:00' },
        preferredDays: [],
        excludedDates: [],
        dayTimeRanges: {}, // { "0": {start: "08:00", end: "16:00"}, ... }
    }
};

const API_BASE = '/api/v1';

function normalizeIdArray(value) {
    if (!Array.isArray(value)) return [];
    return value
        .map(v => parseInt(v, 10))
        .filter(v => Number.isFinite(v));
}

// --- INIT ---
document.addEventListener('DOMContentLoaded', async () => {
    checkAuthStatus();
    setupEventListeners();
    
    // Setup Twin Booking UI toggle
    const twinCheck = document.getElementById('enableTwinBooking');
    const twinSelect = document.getElementById('twinProfileSelect');
    if (twinCheck && twinSelect) {
        twinCheck.addEventListener('change', (e) => {
            twinSelect.style.display = e.target.checked ? 'inline-block' : 'none';
        });
    }
});

// --- AUTH ---
async function checkAuthStatus() {
    try {
        const res = await fetch('/auth/me');
        const data = await res.json();
        
        console.log('Auth Status:', data); // DEBUG

        if (data.authenticated) {
            document.getElementById('loginOverlay').style.display = 'none'; // Force hide
            document.getElementById('loginOverlay').classList.remove('visible'); // Remove class too
            document.getElementById('appContent').classList.remove('hidden');
            document.getElementById('userLabel').textContent = data.user.email;
            initializeApp();
        } else {
            document.getElementById('loginOverlay').style.display = 'flex'; // Force show
            document.getElementById('loginOverlay').classList.add('visible');
            document.getElementById('appContent').classList.add('hidden'); // Ensure app is hidden
        }
    } catch (e) {
        console.error('Auth check failed', e);
        // Fallback to login screen on error
        document.getElementById('loginOverlay').style.display = 'flex';
        document.getElementById('loginOverlay').classList.add('visible');
    }
}

function loginWithGoogle() {
    window.location.href = '/auth/login';
}

document.getElementById('authBtn').onclick = async () => {
    await fetch('/auth/logout', { method: 'POST' });
    window.location.reload();
};

// --- APP LOGIC ---

async function initializeApp() {
    await loadProfiles();
    restoreState();
}

async function loadProfiles() {
    try {
        const res = await fetch(`${API_BASE}/profiles`);
        const json = await res.json();
        if (json.success) {
            state.profiles = json.data;
            renderProfilesList();
            populateTwinProfileSelect(); // NEW
            
            // Auto select first profile if none selected
            if (!state.currentProfile && state.profiles.length > 0) {
                selectProfile(state.profiles[0]);
            }
        }
    } catch (e) {
        showToast('Błąd ładowania profili', 'error');
    }
}

// NEW: Helper for Twin Select
function populateTwinProfileSelect() {
    const select = document.getElementById('twinProfileSelect');
    if (!select) return;
    select.innerHTML = '<option value="">Wybierz drugie dziecko...</option>';
    
    state.profiles.forEach(p => {
        if (p !== state.currentProfile) { // Don't show current profile
            const opt = document.createElement('option');
            opt.value = p;
            opt.textContent = p;
            select.appendChild(opt);
        }
    });
}

function selectProfile(profileName) {
    state.currentProfile = profileName;
    document.getElementById('currentProfileLabel').textContent = profileName;
    document.getElementById('profilesModal').classList.add('hidden');
    
    // Refresh dictionaries for this profile
    loadDictionaries();
    checkSchedulerStatus();
    populateTwinProfileSelect(); // Update twin select to exclude current
}

async function loadDictionaries() {
    if (!state.currentProfile) return;

    // Load Specialties
    const specRes = await fetch(`${API_BASE}/dictionaries/specialties?profile=${state.currentProfile}`);
    const specJson = await specRes.json();
    if (specJson.success) {
        state.specialties = specJson.data;
        renderSpecialtiesSelect();
    }

    // Load Doctors
    const docRes = await fetch(`${API_BASE}/dictionaries/doctors`);
    const docJson = await docRes.json();
    if (docJson.success) {
        state.doctors = docJson.data;
        // Apply filter initially in case filters were restored
        filterDoctorsBySpecialty();
    }

    // Load Clinics
    const clinRes = await fetch(`${API_BASE}/dictionaries/clinics`);
    const clinJson = await clinRes.json();
    if (clinJson.success) {
        state.clinics = clinJson.data;
        renderDropdownList(state.clinics, 'clinicsList', 'clinicIds');
    }
    
    // Render Weekdays Grid
    renderWeekdaysGrid();
}

// --- UI RENDERING ---

function renderSpecialtiesSelect() {
    const select = document.getElementById('specialtySelect');
    select.innerHTML = '<option value="">Wybierz specjalność...</option>';
    state.specialties.forEach(s => {
        const opt = document.createElement('option');
        opt.value = JSON.stringify(s.ids); // Store array as string value
        opt.textContent = s.name;
        select.appendChild(opt);
    });
    
    // Restore selection if exists
    if (state.filters.specialtyIds.length > 0) {
         const val = JSON.stringify(state.filters.specialtyIds);
         for(let i=0; i<select.options.length; i++) {
             if (select.options[i].value === val) {
                 select.selectedIndex = i;
                 break;
             }
         }
    }
    
    // Add change listener for doctor filtering
    select.onchange = () => {
        updateFiltersFromUI();
        filterDoctorsBySpecialty();
    };
}

function filterDoctorsBySpecialty() {
    const selectedSpecIds = normalizeIdArray(state.filters.specialtyIds || []);
    let filtered = state.doctors;
    
    if (selectedSpecIds.length > 0) {
        filtered = state.doctors.filter(d => {
            const docSpecsRaw = d.specialty_ids ?? d.specialtyIds ?? d.specialties;
            const docSpecs = normalizeIdArray(docSpecsRaw);
            if (docSpecs.length === 0) return false;
            return docSpecs.some(id => selectedSpecIds.includes(id));
        });
    }
    
    renderDropdownList(filtered, 'doctorsList', 'doctorIds');
    document.getElementById('doctorsCount').textContent = filtered.length;
}

function renderDropdownList(items, containerId, filterKey) {
    const container = document.getElementById(containerId);
    container.innerHTML = '';
    
    items.forEach(item => {
        const div = document.createElement('div');
        div.className = 'dropdown-item';
        div.innerHTML = `
            <input type="checkbox" value="${item.id}" id="${filterKey}_${item.id}">
            <label for="${filterKey}_${item.id}">${item.name}</label>
        `;
        
        // Restore checked state
        if (state.filters[filterKey].includes(parseInt(item.id))) {
            div.querySelector('input').checked = true;
        }

        div.querySelector('input').addEventListener('change', (e) => {
            const val = parseInt(item.id);
            if (e.target.checked) {
                if (!state.filters[filterKey].includes(val)) {
                    state.filters[filterKey].push(val);
                }
            } else {
                state.filters[filterKey] = state.filters[filterKey].filter(id => id !== val);
            }
            updateDropdownTriggerLabel(containerId.replace('List', 'Trigger'), state.filters[filterKey].length);
        });
        container.appendChild(div);
    });
    
    // Update label count initially
    updateDropdownTriggerLabel(containerId.replace('List', 'Trigger'), state.filters[filterKey].length);
}

function renderWeekdaysGrid() {
    const container = document.getElementById('weekdaysContainer');
    const days = ['Pn', 'Wt', 'Śr', 'Cz', 'Pt', 'So', 'Nd'];
    container.innerHTML = '';
    
    days.forEach((day, index) => {
        const div = document.createElement('div');
        div.className = 'weekday-item';
        if (state.filters.preferredDays.includes(index)) div.classList.add('selected');
        div.textContent = day;
        div.dataset.day = index;
        div.onclick = () => {
            div.classList.toggle('selected');
            if (div.classList.contains('selected')) {
                if (!state.filters.preferredDays.includes(index)) state.filters.preferredDays.push(index);
            } else {
                state.filters.preferredDays = state.filters.preferredDays.filter(d => d !== index);
            }
        };
        container.appendChild(div);
    });
    
    // Also init advanced time ranges
    renderDayTimeRanges(days);
}

function renderDayTimeRanges(days) {
    const container = document.getElementById('dayTimeRangesContainer');
    if(!container) return;
    container.innerHTML = '';
    
    days.forEach((dayName, idx) => {
        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.alignItems = 'center';
        row.style.justifyContent = 'space-between';
        row.style.fontSize = '0.85rem';
        
        const saved = state.filters.dayTimeRanges[idx] || {};
        
        row.innerHTML = `
            <span style="width: 30px; font-weight:500;">${dayName}</span>
            <input type="time" class="form-control form-control-sm" style="width:80px" data-day="${idx}" data-type="start" value="${saved.start || ''}">
            <span>-</span>
            <input type="time" class="form-control form-control-sm" style="width:80px" data-day="${idx}" data-type="end" value="${saved.end || ''}">
        `;
        
        // Add listeners
        const startIn = row.querySelector('[data-type="start"]');
        const endIn = row.querySelector('[data-type="end"]');
        
        const updateState = () => {
            const s = startIn.value;
            const e = endIn.value;
            if (s && e) {
                state.filters.dayTimeRanges[idx] = { start: s, end: e };
            } else {
                delete state.filters.dayTimeRanges[idx];
            }
        };
        
        startIn.addEventListener('change', updateState);
        endIn.addEventListener('change', updateState);
        
        container.appendChild(row);
    });
}

function renderExcludedDates() {
    const list = document.getElementById('excludedDatesList');
    if(!list) return;
    list.innerHTML = '';
    
    state.filters.excludedDates.forEach(dateStr => {
        const tag = document.createElement('span');
        tag.className = 'badge badge-secondary';
        tag.style.display = 'flex';
        tag.style.alignItems = 'center';
        tag.style.gap = '4px';
        tag.innerHTML = `${dateStr} <span style="cursor:pointer; font-weight:bold;">&times;</span>`;
        
        tag.querySelector('span').onclick = () => {
            state.filters.excludedDates = state.filters.excludedDates.filter(d => d !== dateStr);
            renderExcludedDates();
        };
        list.appendChild(tag);
    });
}


// --- ACTIONS ---

async function handleSearch() {
    updateFiltersFromUI();
    
    if (state.filters.specialtyIds.length === 0) {
        showToast('Wybierz specjalność!', 'error');
        return;
    }

    const btn = document.getElementById('searchBtn');
    btn.disabled = true;
    btn.textContent = 'Szukanie...';
    
    try {
        const payload = buildSearchPayload();
        
        const res = await fetch(`${API_BASE}/appointments/search`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        
        const json = await res.json();
        if (json.success) {
            state.searchResults = json.data;
            renderResults();
            document.getElementById('resultsSource').textContent = `(Znaleziono: ${json.count})`;
            saveState(); // Save successful search params
        } else {
            showToast(json.error || 'Błąd wyszukiwania', 'error');
        }
    } catch (e) {
        showToast('Błąd połączenia', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '🔍 Wyszukaj';
    }
}

function buildSearchPayload() {
    return {
        profile: state.currentProfile,
        specialty_ids: state.filters.specialtyIds,
        doctor_ids: state.filters.doctorIds,
        clinic_ids: state.filters.clinicIds,
        start_date: state.filters.dateFrom ? new Date(state.filters.dateFrom).toISOString() : null,
        end_date: state.filters.dateTo ? new Date(state.filters.dateTo).toISOString() : null,
        preferred_days: state.filters.preferredDays,
        time_range: state.filters.timeRange,
        day_time_ranges: state.filters.dayTimeRanges,
        excluded_dates: state.filters.excludedDates
    };
}

async function startScheduler() {
    updateFiltersFromUI();
    if (state.filters.specialtyIds.length === 0) {
        showToast('Wybierz specjalność!', 'error');
        return;
    }
    
    const interval = document.getElementById('checkInterval').value;
    const autoBook = document.getElementById('autoBook').checked;
    
    // TWIN BOOKING PARAMS
    const twinEnabled = document.getElementById('enableTwinBooking').checked;
    const twinProfile = document.getElementById('twinProfileSelect').value;
    
    if (twinEnabled && !twinProfile) {
        showToast('Wybierz profil drugiego dziecka!', 'error');
        // Reset checkbox to prevent confusion
        document.getElementById('enableTwinBooking').checked = false;
        document.getElementById('enableAutoCheck').checked = false;
        return;
    }

    const payload = {
        ...buildSearchPayload(),
        interval_minutes: parseInt(interval),
        auto_book: autoBook,
        twin_profile: twinEnabled ? twinProfile : null // Pass twin profile if enabled
    };

    try {
        const res = await fetch(`${API_BASE}/scheduler/start`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const json = await res.json();
        if (json.success) {
            showToast('Automat uruchomiony', 'success');
            checkSchedulerStatus();
        } else {
            showToast(json.error, 'error');
            document.getElementById('enableAutoCheck').checked = false; // Revert switch
        }
    } catch (e) {
        showToast('Błąd startu automatu', 'error');
    }
}

async function stopScheduler() {
    if (!state.currentProfile) return;
    try {
        await fetch(`${API_BASE}/scheduler/stop`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ profile: state.currentProfile })
        });
        showToast('Automat zatrzymany', 'info');
        checkSchedulerStatus();
    } catch (e) { console.error(e); }
}

async function checkSchedulerStatus() {
    if (!state.currentProfile) return;
    try {
        const res = await fetch(`${API_BASE}/scheduler/status?profile=${state.currentProfile}`);
        const json = await res.json();
        
        const statusBox = document.getElementById('autoCheckStatus');
        const switchEl = document.getElementById('enableAutoCheck');
        const detailsRow = document.getElementById('schedulerDetailsRow');
        const detailsText = document.getElementById('schedulerDetails');
        
        if (json.success && json.data && json.data.active) {
            state.schedulerStatus = json.data;
            statusBox.textContent = 'AKTYWNY';
            statusBox.classList.add('active');
            switchEl.checked = true;
            
            // Show details
            detailsRow.style.display = 'block';
            let info = `Następne: ${formatTime(json.data.next_run)} | Przebiegi: ${json.data.runs_count}`;
            if (json.data.last_results) {
                info += ` | Ost. wynik: ${json.data.last_results.count} wizyt (${formatTime(json.data.last_results.timestamp)})`;
            }
            if (json.data.twin_profile) {
                 info += ` | 👯 Tryb Bliźniak: ${json.data.twin_profile}`;
            }
            detailsText.textContent = info;
            
            // If we have fresh results from scheduler, show them
            if (json.data.last_results && json.data.last_results.appointments) {
                state.searchResults = json.data.last_results.appointments;
                renderResults();
                document.getElementById('resultsSource').textContent = '(z Automatu)';
            }
            
        } else {
            statusBox.textContent = 'Wyłączony';
            statusBox.classList.remove('active');
            switchEl.checked = false;
            detailsRow.style.display = 'none';
        }
    } catch (e) { console.error(e); }
}

// --- UTILS ---

function updateFiltersFromUI() {
    // Specialty
    const specVal = document.getElementById('specialtySelect').value;
    if (specVal) {
        state.filters.specialtyIds = normalizeIdArray(JSON.parse(specVal));
    } else {
        state.filters.specialtyIds = [];
    }
    
    // Dates
    state.filters.dateFrom = document.getElementById('dateFrom').value;
    state.filters.dateTo = document.getElementById('dateTo').value;
    
    // Time
    state.filters.timeRange.start = document.getElementById('hourFrom').value + ":00";
    state.filters.timeRange.end = document.getElementById('hourTo').value + ":00";
}

function renderResults() {
    const tbody = document.getElementById('resultsBody');
    tbody.innerHTML = '';
    
    if (state.searchResults.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 20px;">Brak wyników</td></tr>';
        return;
    }
    
    state.searchResults.forEach(apt => {
        const dateObj = new Date(apt.appointmentDate);
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${dateObj.toLocaleDateString('pl-PL')}</td>
            <td><strong>${dateObj.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'})}</strong></td>
            <td>${apt.doctor ? apt.doctor.name : '-'}</td>
            <td>${apt.specialty ? apt.specialty.name : '-'}</td>
            <td>${apt.clinic ? apt.clinic.name : '-'}</td>
        `;
        tbody.appendChild(tr);
    });
}

function setupEventListeners() {
    // Search Button
    document.getElementById('searchBtn').addEventListener('click', handleSearch);
    
    // Scheduler Switch
    document.getElementById('enableAutoCheck').addEventListener('change', (e) => {
        if (e.target.checked) {
            startScheduler();
        } else {
            stopScheduler();
        }
    });

    // Reset Button
    document.getElementById('resetBtn').addEventListener('click', () => {
        // Clear filters
        state.filters.specialtyIds = [];
        state.filters.doctorIds = [];
        state.filters.clinicIds = [];
        state.filters.preferredDays = [];
        state.filters.excludedDates = [];
        state.filters.dayTimeRanges = {};
        
        // Reset defaults for dates
        const now = new Date();
        const tomorrow = new Date(now);
        tomorrow.setDate(tomorrow.getDate() + 1);
        state.filters.dateFrom = tomorrow.toISOString().split('T')[0];
        const next30 = new Date(tomorrow);
        next30.setDate(tomorrow.getDate() + 30);
        state.filters.dateTo = next30.toISOString().split('T')[0];
        
        // Reset UI
        document.querySelectorAll('input[type="checkbox"]').forEach(c => c.checked = false);
        document.getElementById('specialtySelect').value = "";
        document.getElementById('dateFrom').value = state.filters.dateFrom;
        document.getElementById('dateTo').value = state.filters.dateTo;
        document.getElementById('excludedDatesList').innerHTML = "";
        
        // Refresh
        filterDoctorsBySpecialty(); // Reset doctor filter
        renderProfilesList();
    });

    // Advanced Filters Toggle
    document.getElementById('toggleAdvancedFilters').addEventListener('click', () => {
        const panel = document.getElementById('advancedFiltersPanel');
        panel.classList.toggle('hidden');
    });

    // Excluded Date Add
    document.getElementById('addExcludedDateBtn').addEventListener('click', () => {
        const inp = document.getElementById('excludeDateInput');
        if (inp.value) {
            if (!state.filters.excludedDates.includes(inp.value)) {
                state.filters.excludedDates.push(inp.value);
                renderExcludedDates();
            }
            inp.value = '';
        }
    });

    // Polling for Scheduler Status
    setInterval(checkSchedulerStatus, 10000);
}

// Helpers
function toggleDropdown(id) {
    document.getElementById(id).classList.toggle('active');
}

function updateDropdownTriggerLabel(id, count) {
    const el = document.getElementById(id);
    if (count > 0) el.textContent = `Wybrano (${count})`;
    else el.textContent = 'Wybierz...';
}

function filterDropdown(input, listId) {
    const filter = input.value.toLowerCase();
    const items = document.getElementById(listId).getElementsByClassName('dropdown-item');
    Array.from(items).forEach(item => {
        const text = item.textContent || item.innerText;
        item.style.display = text.toLowerCase().indexOf(filter) > -1 ? "" : "none";
    });
}

function formatTime(isoStr) {
    if (!isoStr) return '--:--';
    return new Date(isoStr).toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'});
}

function showToast(msg, type='info') {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = `toast visible ${type}`;
    setTimeout(() => t.classList.remove('visible'), 3000);
}

function toggleProfilesModal() {
    document.getElementById('profilesModal').classList.toggle('hidden');
}

function renderProfilesList() {
    const list = document.getElementById('profilesList');
    list.innerHTML = '';
    state.profiles.forEach(p => {
        const div = document.createElement('div');
        div.className = 'profile-item';
        if (p === state.currentProfile) div.classList.add('active');
        div.textContent = p;
        div.onclick = () => selectProfile(p);
        list.appendChild(div);
    });
}

// Add Profile Form
document.getElementById('addProfileForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('newProfileName').value;
    const login = document.getElementById('newProfileLogin').value;
    const pass = document.getElementById('newProfilePass').value;
    const isChild = document.getElementById('newProfileIsChild').checked;
    
    try {
        const res = await fetch(`${API_BASE}/profiles/add`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, login, password: pass, is_child_account: isChild })
        });
        const json = await res.json();
        if (json.success) {
            showToast('Profil dodany', 'success');
            document.getElementById('addProfileForm').reset();
            loadProfiles();
        } else {
            showToast(json.error || 'Błąd', 'error');
        }
    } catch(e) { console.error(e); }
});

// Save/Restore State (simplified)
function saveState() {
    localStorage.setItem('medifinder_last_filters', JSON.stringify(state.filters));
}

function restoreState() {
    const saved = localStorage.getItem('medifinder_last_filters');
    if (saved) {
        try {
            const parsed = JSON.parse(saved);
            state.filters = {...state.filters, ...parsed};
        } catch(e) {}
    }

    // Normalize stored ids (important when JSON contains strings)
    state.filters.specialtyIds = normalizeIdArray(state.filters.specialtyIds);
    state.filters.doctorIds = normalizeIdArray(state.filters.doctorIds);
    state.filters.clinicIds = normalizeIdArray(state.filters.clinicIds);

    // --- Default Dates (Tomorrow to +30 days) ---
    if (!state.filters.dateFrom || state.filters.dateFrom === '') {
        const now = new Date();
        const tomorrow = new Date(now);
        tomorrow.setDate(tomorrow.getDate() + 1);
        state.filters.dateFrom = tomorrow.toISOString().split('T')[0];
        
        const next30 = new Date(tomorrow);
        next30.setDate(tomorrow.getDate() + 30);
        state.filters.dateTo = next30.toISOString().split('T')[0];
    }

    // Apply to UI
    if(document.getElementById('dateFrom')) document.getElementById('dateFrom').value = state.filters.dateFrom;
    if(document.getElementById('dateTo')) document.getElementById('dateTo').value = state.filters.dateTo;
    
    // Restore other UI elements
    renderExcludedDates();
}
