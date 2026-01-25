/**
 * MEDIFINDER 2.0 Frontend Script
 * Handles UI interactions, API calls, and data rendering
 */

// Global State
let state = {
    profiles: [],
    currentProfile: null, // profile login (card number)
    specialties: [],
    doctors: [],
    clinics: [],
    searchResults: [],
    schedulerStatus: null,
    ui: {
        filtersLocked: false
    },
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
const SEARCH_BTN_LABEL = '🔍 Wyszukaj';
const SEARCH_BTN_DISABLED_LABEL = '🔍 Wyszukaj (wyłącz automat)';
const FILTERS_LOCKED_TOAST = 'Wyłącz automat, aby zmienić filtry.';

const FILTERS_STORAGE_PREFIX = 'medifinder_last_filters__';
const LEGACY_FILTERS_KEY = 'medifinder_last_filters';

const SELECTED_PROFILE_KEY = 'medifinder_selected_profile';

function getDefaultFilters() {
    return {
        specialtyIds: [],
        doctorIds: [],
        clinicIds: [],
        dateFrom: '',
        dateTo: '',
        timeRange: { start: '04:00', end: '22:00' },
        preferredDays: [],
        excludedDates: [],
        dayTimeRanges: {}
    };
}

function normalizeProfilesList(raw) {
    if (!Array.isArray(raw)) return [];

    const mapped = raw.map(p => {
        // Legacy: backend used to return array of strings
        if (typeof p === 'string') {
            const login = String(p);
            return { login, name: login, is_child: false };
        }

        if (!p || typeof p !== 'object') return null;

        const login = p.login ?? p.username ?? '';
        const name = (p.name ?? p.description ?? '').trim();
        const isChild = Boolean(p.is_child ?? p.isChild ?? p.is_child_account ?? p.isChildAccount ?? false);

        if (!login) return null;
        return {
            login: String(login),
            name: name ? String(name) : String(login),
            is_child: isChild
        };
    });

    return mapped.filter(Boolean);
}

function getProfileByLogin(login) {
    if (!login) return null;
    return state.profiles.find(p => p && p.login === login) || null;
}

function getProfileDisplayLabel(login) {
    const prof = getProfileByLogin(login);
    if (!prof) return String(login || '');

    // Show configured name first, but keep card number visible.
    if (prof.name && prof.name !== prof.login) {
        return `${prof.name} (${prof.login})`;
    }
    return prof.login;
}

function getFiltersStorageKey(profileLogin) {
    const p = profileLogin || state.currentProfile;
    if (!p) return null;
    // Keyed by login (card number) because that's the stable identifier used by backend.
    return `${FILTERS_STORAGE_PREFIX}${encodeURIComponent(String(p))}`;
}

function saveSelectedProfile(profileLogin) {
    if (!profileLogin) return;
    try {
        localStorage.setItem(SELECTED_PROFILE_KEY, String(profileLogin));
    } catch (e) {
        console.warn('LocalStorage save selected profile failed', e);
    }
}

function getSavedProfile() {
    try {
        const p = localStorage.getItem(SELECTED_PROFILE_KEY);
        return p ? String(p) : null;
    } catch (e) {
        return null;
    }
}

function clearSavedProfile() {
    try {
        localStorage.removeItem(SELECTED_PROFILE_KEY);
    } catch (e) {
        // ignore
    }
}

function normalizeIdArray(value) {
    if (!Array.isArray(value)) return [];
    return value
        .map(v => parseInt(v, 10))
        .filter(v => Number.isFinite(v));
}

function parseUtcDate(isoStr) {
    if (!isoStr) return null;
    const s = String(isoStr).trim();

    // If string already has a timezone (Z or offset), Date() will convert to local automatically.
    if (/[zZ]$/.test(s) || /[+-]\d\d:?\d\d$/.test(s)) {
        return new Date(s);
    }

    // If backend sends naive ISO (no timezone), treat it as UTC.
    return new Date(`${s}Z`);
}

function setManualSearchEnabled(enabled) {
    const btn = document.getElementById('searchBtn');
    if (!btn) return;

    if (enabled) {
        btn.disabled = false;
        btn.textContent = SEARCH_BTN_LABEL;
        btn.title = '';
        return;
    }

    btn.disabled = true;
    btn.textContent = SEARCH_BTN_DISABLED_LABEL;
    btn.title = 'Ręczne wyszukiwanie jest zablokowane, gdy automat jest włączony.';
}

function setPointerDisabled(el, disabled) {
    if (!el) return;
    el.style.pointerEvents = disabled ? 'none' : 'auto';
    el.style.opacity = disabled ? '0.6' : '1';
    el.setAttribute('aria-disabled', disabled ? 'true' : 'false');
}

function disableInputsInContainer(container, disabled) {
    if (!container) return;
    container.querySelectorAll('input, select, button, textarea').forEach(el => {
        el.disabled = disabled;
    });
}

function setFiltersEnabled(enabled) {
    const locked = !enabled;
    state.ui.filtersLocked = locked;

    // Filters panel main inputs
    ['specialtySelect', 'dateFrom', 'dateTo', 'hourFrom', 'hourTo', 'toggleAdvancedFilters', 'excludeDateInput', 'addExcludedDateBtn', 'resetBtn'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.disabled = locked;
    });

    // Custom dropdown triggers (they are divs)
    setPointerDisabled(document.getElementById('doctorsTrigger'), locked);
    setPointerDisabled(document.getElementById('clinicsTrigger'), locked);

    // Dropdown inner inputs/buttons/checkboxes
    disableInputsInContainer(document.getElementById('doctorsDropdown'), locked);
    disableInputsInContainer(document.getElementById('clinicsDropdown'), locked);
    disableInputsInContainer(document.getElementById('dayTimeRangesContainer'), locked);

    // Weekdays (divs)
    const weekdays = document.getElementById('weekdaysContainer');
    if (weekdays) {
        weekdays.querySelectorAll('.weekday-item').forEach(item => {
            item.style.pointerEvents = locked ? 'none' : 'auto';
            item.style.opacity = locked ? '0.6' : '1';
        });
    }

    // Excluded dates remove buttons (renderExcludedDates respects lock, but make sure UI updates)
    renderExcludedDates();

    // Close dropdowns if locked (avoid confusing open state)
    if (locked) {
        const dd1 = document.getElementById('doctorsDropdown');
        const dd2 = document.getElementById('clinicsDropdown');
        if (dd1) dd1.classList.remove('active');
        if (dd2) dd2.classList.remove('active');
    }
}

function setSchedulerOptionsEnabled(enabled) {
    const locked = !enabled;
    ['checkInterval', 'autoBook', 'enableTwinBooking', 'twinProfileSelect'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.disabled = locked;
    });
}

function pad2(val) {
    const n = parseInt(val, 10);
    if (!Number.isFinite(n)) return '';
    return String(n).padStart(2, '0');
}

function applyTimeRangeToUI() {
    const start = state.filters?.timeRange?.start;
    const end = state.filters?.timeRange?.end;

    const hourFromEl = document.getElementById('hourFrom');
    const hourToEl = document.getElementById('hourTo');

    if (hourFromEl && typeof start === 'string' && start.includes(':')) {
        hourFromEl.value = pad2(start.split(':')[0]);
    }
    if (hourToEl && typeof end === 'string' && end.includes(':')) {
        hourToEl.value = pad2(end.split(':')[0]);
    }
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
            document.getElementById('loginOverlay').style.display = 'none';
            document.getElementById('loginOverlay').classList.remove('visible');
            document.getElementById('appContent').classList.remove('hidden');
            document.getElementById('userLabel').textContent = data.user.email;
            initializeApp();
        } else {
            document.getElementById('loginOverlay').style.display = 'flex';
            document.getElementById('loginOverlay').classList.add('visible');
            document.getElementById('appContent').classList.add('hidden');
        }
    } catch (e) {
        console.error('Auth check failed', e);
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
    // loadProfiles() will auto-select a profile (if any) and selectProfile() handles restore per-profile.
    await loadProfiles();
}

async function loadProfiles() {
    try {
        const res = await fetch(`${API_BASE}/profiles`);
        const json = await res.json();
        if (json.success) {
            state.profiles = normalizeProfilesList(json.data);
            renderProfilesList();
            populateTwinProfileSelect();

            // Prefer saved profile if available
            if (!state.currentProfile && state.profiles.length > 0) {
                const savedProfile = getSavedProfile();
                const savedExists = savedProfile && state.profiles.some(p => p.login === savedProfile);

                if (savedExists) {
                    selectProfile(savedProfile);
                } else {
                    if (savedProfile && !savedExists) {
                        clearSavedProfile();
                    }
                    selectProfile(state.profiles[0].login);
                }
            }
        }
    } catch (e) {
        showToast('Błąd ładowania profili', 'error');
    }
}

function populateTwinProfileSelect() {
    const select = document.getElementById('twinProfileSelect');
    if (!select) return;
    select.innerHTML = '<option value="">Wybierz drugie dziecko...</option>';

    state.profiles.forEach(p => {
        if (!p || p.login === state.currentProfile) return;

        const opt = document.createElement('option');
        opt.value = p.login; // keep login (card number) for API calls
        opt.textContent = getProfileDisplayLabel(p.login);
        select.appendChild(opt);
    });
}

function selectProfile(profileLogin) {
    const prevProfile = state.currentProfile;
    if (prevProfile && prevProfile !== profileLogin) {
        // Persist filters of previous profile before switching.
        saveState();
    }

    state.currentProfile = profileLogin;
    saveSelectedProfile(profileLogin);

    document.getElementById('currentProfileLabel').textContent = getProfileDisplayLabel(profileLogin);
    document.getElementById('profilesModal').classList.add('hidden');

    // Reset filters to defaults and restore per-profile state
    state.filters = getDefaultFilters();
    restoreState();

    // Refresh dictionaries for this profile
    loadDictionaries();
    checkSchedulerStatus();
    populateTwinProfileSelect();
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

    // Ensure inputs reflect current lock status
    setFiltersEnabled(!state.ui.filtersLocked);
}

// --- UI RENDERING ---

function renderSpecialtiesSelect() {
    const select = document.getElementById('specialtySelect');
    select.innerHTML = '<option value="">Wybierz specjalność...</option>';
    state.specialties.forEach(s => {
        const opt = document.createElement('option');
        opt.value = JSON.stringify(s.ids);
        opt.textContent = s.name;
        select.appendChild(opt);
    });

    // Restore selection if exists
    if (state.filters.specialtyIds.length > 0) {
        const val = JSON.stringify(state.filters.specialtyIds);
        for (let i = 0; i < select.options.length; i++) {
            if (select.options[i].value === val) {
                select.selectedIndex = i;
                break;
            }
        }
    }

    // Add change listener for doctor filtering
    select.onchange = () => {
        if (state.ui.filtersLocked) {
            showToast(FILTERS_LOCKED_TOAST, 'info');
            return;
        }
        updateFiltersFromUI();
        filterDoctorsBySpecialty();
        saveState();
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

        const checkbox = div.querySelector('input');
        checkbox.disabled = state.ui.filtersLocked;

        // Restore checked state
        if (state.filters[filterKey].includes(parseInt(item.id))) {
            checkbox.checked = true;
        }

        checkbox.addEventListener('change', (e) => {
            if (state.ui.filtersLocked) {
                e.target.checked = !e.target.checked;
                showToast(FILTERS_LOCKED_TOAST, 'info');
                return;
            }

            const val = parseInt(item.id);
            if (e.target.checked) {
                if (!state.filters[filterKey].includes(val)) {
                    state.filters[filterKey].push(val);
                }
            } else {
                state.filters[filterKey] = state.filters[filterKey].filter(id => id !== val);
            }
            updateDropdownTriggerLabel(containerId.replace('List', 'Trigger'), state.filters[filterKey].length);
            saveState();
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
        div.style.pointerEvents = state.ui.filtersLocked ? 'none' : 'auto';
        div.style.opacity = state.ui.filtersLocked ? '0.6' : '1';

        div.onclick = () => {
            if (state.ui.filtersLocked) {
                showToast(FILTERS_LOCKED_TOAST, 'info');
                return;
            }
            div.classList.toggle('selected');
            if (div.classList.contains('selected')) {
                if (!state.filters.preferredDays.includes(index)) state.filters.preferredDays.push(index);
            } else {
                state.filters.preferredDays = state.filters.preferredDays.filter(d => d !== index);
            }
            saveState();
        };
        container.appendChild(div);
    });

    // Also init advanced time ranges
    renderDayTimeRanges(days);
}

function renderDayTimeRanges(days) {
    const container = document.getElementById('dayTimeRangesContainer');
    if (!container) return;
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

        const startIn = row.querySelector('[data-type="start"]');
        const endIn = row.querySelector('[data-type="end"]');
        startIn.disabled = state.ui.filtersLocked;
        endIn.disabled = state.ui.filtersLocked;

        const updateState = () => {
            if (state.ui.filtersLocked) return;
            const s = startIn.value;
            const e = endIn.value;
            if (s && e) {
                state.filters.dayTimeRanges[idx] = { start: s, end: e };
            } else {
                delete state.filters.dayTimeRanges[idx];
            }
            saveState();
        };

        startIn.addEventListener('change', updateState);
        endIn.addEventListener('change', updateState);

        container.appendChild(row);
    });
}

function renderExcludedDates() {
    const list = document.getElementById('excludedDatesList');
    if (!list) return;
    list.innerHTML = '';

    state.filters.excludedDates.forEach(dateStr => {
        const tag = document.createElement('span');
        tag.className = 'badge badge-secondary';
        tag.style.display = 'flex';
        tag.style.alignItems = 'center';
        tag.style.gap = '4px';

        const removeDisabled = state.ui.filtersLocked;
        tag.innerHTML = `${dateStr} <span style="cursor:${removeDisabled ? 'default' : 'pointer'}; font-weight:bold; opacity:${removeDisabled ? '0.5' : '1'};">&times;</span>`;

        const removeSpan = tag.querySelector('span');
        if (!removeDisabled) {
            removeSpan.onclick = () => {
                state.filters.excludedDates = state.filters.excludedDates.filter(d => d !== dateStr);
                renderExcludedDates();
                saveState();
            };
        }

        list.appendChild(tag);
    });
}

// --- ACTIONS ---

async function handleSearch() {
    // Manual search is blocked when scheduler is active.
    if (state.schedulerStatus && state.schedulerStatus.active) {
        showToast('Wyłącz automat, aby wykonać ręczne wyszukiwanie.', 'info');
        return;
    }

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
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const json = await res.json();
        if (json.success) {
            state.searchResults = json.data;
            renderResults();
            document.getElementById('resultsSource').textContent = `(Znaleziono: ${json.count})`;
            saveState();
        } else {
            showToast(json.error || 'Błąd wyszukiwania', 'error');
        }
    } catch (e) {
        showToast('Błąd połączenia', 'error');
    } finally {
        // If scheduler became active in the meantime, keep the button disabled.
        setManualSearchEnabled(!(state.schedulerStatus && state.schedulerStatus.active));
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
        document.getElementById('enableTwinBooking').checked = false;
        document.getElementById('enableAutoCheck').checked = false;
        return;
    }

    const payload = {
        ...buildSearchPayload(),
        interval_minutes: parseInt(interval),
        auto_book: autoBook,
        twin_profile: twinEnabled ? twinProfile : null
    };

    try {
        const res = await fetch(`${API_BASE}/scheduler/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const json = await res.json();
        if (json.success) {
            showToast('Automat uruchomiony', 'success');
            // Immediately lock UI params.
            setManualSearchEnabled(false);
            setFiltersEnabled(false);
            setSchedulerOptionsEnabled(false);
            checkSchedulerStatus();
        } else {
            showToast(json.error, 'error');
            document.getElementById('enableAutoCheck').checked = false;
            setManualSearchEnabled(true);
            setFiltersEnabled(true);
            setSchedulerOptionsEnabled(true);
        }
    } catch (e) {
        showToast('Błąd startu automatu', 'error');
        setManualSearchEnabled(true);
        setFiltersEnabled(true);
        setSchedulerOptionsEnabled(true);
    }
}

async function stopScheduler() {
    if (!state.currentProfile) return;
    try {
        await fetch(`${API_BASE}/scheduler/stop`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile: state.currentProfile })
        });
        showToast('Automat zatrzymany', 'info');
        setManualSearchEnabled(true);
        setFiltersEnabled(true);
        setSchedulerOptionsEnabled(true);
        checkSchedulerStatus();
    } catch (e) {
        console.error(e);
    }
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

            // Lock all filter params when scheduler is active
            setManualSearchEnabled(false);
            setFiltersEnabled(false);
            setSchedulerOptionsEnabled(false);

            // Show details
            detailsRow.style.display = 'block';
            let info = `Następne: ${formatTime(json.data.next_run)} | Przebiegi: ${json.data.runs_count}`;
            if (json.data.last_results) {
                info += ` | Ost. wynik: ${json.data.last_results.count} wizyt (${formatTime(json.data.last_results.timestamp)})`;
            }
            if (json.data.twin_profile) {
                info += ` | 👯 Tryb Bliźniak: ${getProfileDisplayLabel(json.data.twin_profile)}`;
            }
            detailsText.textContent = info;

            // If we have fresh results from scheduler, show them
            if (json.data.last_results && json.data.last_results.appointments) {
                state.searchResults = json.data.last_results.appointments;
                renderResults();
                document.getElementById('resultsSource').textContent = '(z Automatu)';
            }

        } else {
            state.schedulerStatus = json.data || null;
            statusBox.textContent = 'Wyłączony';
            statusBox.classList.remove('active');
            switchEl.checked = false;
            detailsRow.style.display = 'none';

            setManualSearchEnabled(true);
            setFiltersEnabled(true);
            setSchedulerOptionsEnabled(true);
        }
    } catch (e) {
        console.error(e);
    }
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

    // Date/Time changes (persist immediately)
    ['dateFrom', 'dateTo', 'hourFrom', 'hourTo'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.addEventListener('change', () => {
            if (state.ui.filtersLocked) {
                showToast(FILTERS_LOCKED_TOAST, 'info');
                return;
            }
            updateFiltersFromUI();
            saveState();
        });
    });

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
        if (state.ui.filtersLocked) {
            showToast(FILTERS_LOCKED_TOAST, 'info');
            return;
        }

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
        applyTimeRangeToUI();
        document.getElementById('excludedDatesList').innerHTML = "";

        // Refresh
        filterDoctorsBySpecialty();
        renderDropdownList(state.clinics, 'clinicsList', 'clinicIds');
        renderWeekdaysGrid();
        renderExcludedDates();
        renderProfilesList();

        saveState();
    });

    // Advanced Filters Toggle
    document.getElementById('toggleAdvancedFilters').addEventListener('click', () => {
        if (state.ui.filtersLocked) {
            showToast(FILTERS_LOCKED_TOAST, 'info');
            return;
        }
        const panel = document.getElementById('advancedFiltersPanel');
        panel.classList.toggle('hidden');
    });

    // Excluded Date Add
    document.getElementById('addExcludedDateBtn').addEventListener('click', () => {
        if (state.ui.filtersLocked) {
            showToast(FILTERS_LOCKED_TOAST, 'info');
            return;
        }

        const inp = document.getElementById('excludeDateInput');
        if (inp.value) {
            if (!state.filters.excludedDates.includes(inp.value)) {
                state.filters.excludedDates.push(inp.value);
                renderExcludedDates();
                saveState();
            }
            inp.value = '';
        }
    });

    // Polling for Scheduler Status
    setInterval(checkSchedulerStatus, 10000);
}

// Helpers
function toggleDropdown(id) {
    if (state.ui.filtersLocked) {
        showToast(FILTERS_LOCKED_TOAST, 'info');
        return;
    }
    document.getElementById(id).classList.toggle('active');
}

function updateDropdownTriggerLabel(id, count) {
    const el = document.getElementById(id);
    if (count > 0) el.textContent = `Wybrano (${count})`;
    else el.textContent = 'Wybierz...';
}

function filterDropdown(input, listId) {
    if (state.ui.filtersLocked) return;
    const filter = input.value.toLowerCase();
    const items = document.getElementById(listId).getElementsByClassName('dropdown-item');
    Array.from(items).forEach(item => {
        const text = item.textContent || item.innerText;
        item.style.display = text.toLowerCase().indexOf(filter) > -1 ? "" : "none";
    });
}

function clearSelection(listId) {
    if (state.ui.filtersLocked) {
        showToast(FILTERS_LOCKED_TOAST, 'info');
        return;
    }

    let filterKey = '';
    if (listId === 'doctorsList') filterKey = 'doctorIds';
    if (listId === 'clinicsList') filterKey = 'clinicIds';

    if (filterKey) {
        state.filters[filterKey] = [];
        const container = document.getElementById(listId);
        if (container) {
            container.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
        }
        updateDropdownTriggerLabel(listId.replace('List', 'Trigger'), 0);
        saveState();
    }
}

function formatTime(isoStr) {
    const d = parseUtcDate(isoStr);
    if (!d || Number.isNaN(d.getTime())) return '--:--';
    return d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
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
        if (!p) return;

        const div = document.createElement('div');
        div.className = 'profile-item';
        if (p.login === state.currentProfile) div.classList.add('active');
        div.textContent = getProfileDisplayLabel(p.login);
        div.onclick = () => selectProfile(p.login);
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
            headers: { 'Content-Type': 'application/json' },
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
    } catch (e) {
        console.error(e);
    }
});

// Save/Restore State
function saveState() {
    const key = getFiltersStorageKey();
    if (!key) return;

    try {
        localStorage.setItem(key, JSON.stringify(state.filters));
    } catch (e) {
        console.warn('LocalStorage save failed', key, e);
    }
}

function restoreState() {
    const key = getFiltersStorageKey();
    if (!key) return;

    let saved = localStorage.getItem(key);

    // One-time migration from legacy single-key storage.
    if (!saved) {
        const legacy = localStorage.getItem(LEGACY_FILTERS_KEY);
        if (legacy) {
            saved = legacy;
            try {
                localStorage.setItem(key, legacy);
                localStorage.removeItem(LEGACY_FILTERS_KEY);
            } catch (e) {
                // ignore
            }
        }
    }

    if (saved) {
        try {
            const parsed = JSON.parse(saved);
            state.filters = { ...state.filters, ...parsed };
        } catch (e) {
            console.warn('LocalStorage restore failed', key, e);
        }
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
    const dateFromEl = document.getElementById('dateFrom');
    const dateToEl = document.getElementById('dateTo');
    if (dateFromEl) dateFromEl.value = state.filters.dateFrom;
    if (dateToEl) dateToEl.value = state.filters.dateTo;

    // Apply time range to UI (hourFrom/hourTo)
    applyTimeRangeToUI();

    // Restore other UI elements
    renderExcludedDates();
}
