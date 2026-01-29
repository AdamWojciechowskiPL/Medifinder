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
    selectedAppointment: null, // Currently selected appointment for booking
    schedulerStatus: null,
    ui: {
        filtersLocked: false,
        notificationsReady: false,
        lastSchedulerParamsSig: null
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

// Results must be scoped per-profile (multi-profile UX).
const RESULTS_STORAGE_PREFIX = 'medifinder_last_results__';

const SELECTED_PROFILE_KEY = 'medifinder_selected_profile';

const NOTIFY_LAST_RESULTS_PREFIX = 'medifinder_notify_last_results_ts__';
const NOTIFY_LAST_BOOKING_PREFIX = 'medifinder_notify_last_booking_ts__';

let schedulerCountdownInterval = null;
let schedulerCountdownNextRunIso = null;

let audioCtx = null;
let audioUnlocked = false;

function unlockAudio() {
    // Must be called from a user gesture at least once (browser policy).
    try {
        if (!audioCtx) {
            const Ctx = window.AudioContext || window.webkitAudioContext;
            if (!Ctx) return;
            audioCtx = new Ctx();
        }
        if (audioCtx.state === 'suspended') {
            audioCtx.resume().catch(() => { /* ignore */ });
        }
        audioUnlocked = true;
    } catch (e) {
        // ignore
    }
}

function playBeep() {
    if (!audioUnlocked || !audioCtx) return;

    try {
        const ctx = audioCtx;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.value = 880;

        // Subtle volume envelope.
        gain.gain.setValueAtTime(0.0001, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.12, ctx.currentTime + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.18);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start();
        osc.stop(ctx.currentTime + 0.2);
    } catch (e) {
        // ignore
    }
}

function getNotifyStorageKey(prefix, profileLogin) {
    const p = profileLogin || state.currentProfile;
    if (!p) return null;
    return `${prefix}${encodeURIComponent(String(p))}`;
}

function lsGet(key) {
    if (!key) return null;
    try {
        const v = localStorage.getItem(key);
        return v ? String(v) : null;
    } catch (e) {
        return null;
    }
}

function lsSet(key, value) {
    if (!key) return;
    try {
        localStorage.setItem(key, String(value));
    } catch (e) {
        // ignore
    }
}

async function ensureNotificationPermission() {
    if (!('Notification' in window)) return false;
    if (Notification.permission === 'granted') return true;
    if (Notification.permission === 'denied') return false;

    try {
        const perm = await Notification.requestPermission();
        return perm === 'granted';
    } catch (e) {
        return false;
    }
}

function sendSystemNotification(title, body) {
    if (!('Notification' in window)) return false;
    if (Notification.permission !== 'granted') return false;

    try {
        const n = new Notification(title, {
            body: body || '',
            silent: true
        });
        n.onclick = () => {
            try {
                window.focus();
            } catch (e) {
                // ignore
            }
            try {
                n.close();
            } catch (e) {
                // ignore
            }
        };
        return true;
    } catch (e) {
        return false;
    }
}

function notifyEvent(title, body, toastType = 'info') {
    const ok = sendSystemNotification(title, body);
    playBeep();

    // Fallback when notifications are blocked/unsupported.
    if (!ok) {
        showToast(body || title, toastType);
    }
}

function formatFirstAppointmentHint(appointments) {
    if (!Array.isArray(appointments) || appointments.length === 0) return '';

    const first = appointments[0];
    const iso = first?.appointmentDate || first?.appointment_date;
    if (!iso) return '';

    const d = parseUtcDate(iso) || new Date(iso);
    if (!d || Number.isNaN(d.getTime())) return '';

    const day = d.toLocaleDateString('pl-PL');
    const time = d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
    return ` Najbliższa: ${day} ${time}.`;
}

function processSchedulerNotifications(st, allowNotify) {
    if (!st) return;

    // --- New results notification ---
    const lr = st.last_results;
    const lrTs = lr?.timestamp ? String(lr.timestamp) : null;
    if (lrTs) {
        const key = getNotifyStorageKey(NOTIFY_LAST_RESULTS_PREFIX);
        const prevTs = lsGet(key);

        if (!prevTs) {
            // First run after page/profile load: record baseline (avoid spam).
            lsSet(key, lrTs);
        } else if (prevTs !== lrTs) {
            lsSet(key, lrTs);

            const cnt = parseInt(lr?.count ?? 0, 10) || 0;
            const pairsCnt = parseInt(lr?.pairs_count ?? 0, 10) || 0;

            if (allowNotify && cnt > 0) {
                let body = `Znaleziono ${cnt} wizyt.`;
                if (pairsCnt > 0) {
                    body += ` (Pary: ${pairsCnt}).`;
                }
                body += formatFirstAppointmentHint(lr?.appointments);

                notifyEvent('Medifinder: znaleziono wizyty', body, 'success');
            }
        }
    }

    // --- Booking notification ---
    const lb = st.last_booking;
    const lbTs = lb?.timestamp ? String(lb.timestamp) : null;
    if (lbTs) {
        const key = getNotifyStorageKey(NOTIFY_LAST_BOOKING_PREFIX);
        const prevTs = lsGet(key);

        if (!prevTs) {
            // Baseline; do not notify immediately after reload.
            lsSet(key, lbTs);
        } else if (prevTs !== lbTs) {
            lsSet(key, lbTs);

            if (allowNotify) {
                const mode = lb?.mode === 'twin' ? ' (bliźniaki)' : '';
                notifyEvent('Medifinder: auto-rezerwacja', `Zarezerwowano wizytę${mode}.`, 'success');
            }
        }
    }
}

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

function getResultsStorageKey(profileLogin) {
    const p = profileLogin || state.currentProfile;
    if (!p) return null;
    return `${RESULTS_STORAGE_PREFIX}${encodeURIComponent(String(p))}`;
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
    ['specialtySelect', 'dateFrom', 'dateTo', 'timeFrom', 'timeTo', 'toggleAdvancedFilters', 'excludeDateInput', 'addExcludedDateBtn', 'resetBtn'].forEach(id => {
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

function applyTimeRangeToUI() {
    const start = state.filters?.timeRange?.start;
    const end = state.filters?.timeRange?.end;

    const timeFromEl = document.getElementById('timeFrom');
    const timeToEl = document.getElementById('timeTo');

    if (timeFromEl && typeof start === 'string') {
        timeFromEl.value = start;
    }
    if (timeToEl && typeof end === 'string') {
        timeToEl.value = end;
    }
}

// Generate Time Options for Selects
function populateTimeSelect(selectElement, defaultValue = '') {
    if (!selectElement) return;
    selectElement.innerHTML = '';
    
    // Create options every 15 minutes
    for (let h = 0; h < 24; h++) {
        for (let m = 0; m < 60; m += 15) {
            const hh = String(h).padStart(2, '0');
            const mm = String(m).padStart(2, '0');
            const timeVal = `${hh}:${mm}`;
            const opt = document.createElement('option');
            opt.value = timeVal;
            opt.textContent = timeVal;
            selectElement.appendChild(opt);
        }
    }
    
    // Add end of day if needed
    if (!selectElement.querySelector('option[value="23:59"]')) {
         const opt = document.createElement('option');
         opt.value = '23:59';
         opt.textContent = '23:59';
         selectElement.appendChild(opt);
    }

    if (defaultValue) {
        selectElement.value = defaultValue;
    }
}

function clearResultsUI() {
    state.searchResults = [];
    state.selectedAppointment = null;

    const bookBtn = document.getElementById('bookSelectedBtn');
    if (bookBtn) bookBtn.disabled = true;

    const src = document.getElementById('resultsSource');
    if (src) src.textContent = '';

    renderResults();
}

// --- INIT ---
document.addEventListener('DOMContentLoaded', async () => {
    checkAuthStatus();
    setupEventListeners();

    // Populate global time selects
    populateTimeSelect(document.getElementById('timeFrom'), '04:00');
    populateTimeSelect(document.getElementById('timeTo'), '22:00');

    // Unlock audio on first user gesture so beeps can work even in background.
    document.addEventListener('click', unlockAudio, { once: true });

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
        const res = await fetch('/auth/me', { credentials: 'include' });
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
    await fetch('/auth/logout', { method: 'POST', credentials: 'include' });
    window.location.reload();
};

// --- APP LOGIC ---

async function initializeApp() {
    // loadProfiles() will auto-select a profile (if any) and selectProfile() handles restore per-profile.
    await loadProfiles();
}

async function loadProfiles() {
    try {
        const res = await fetch(`${API_BASE}/profiles`, { credentials: 'include' });
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
        // Persist filters & results of previous profile before switching.
        saveState();
        saveResultsState();
    }

    state.currentProfile = profileLogin;
    saveSelectedProfile(profileLogin);
    state.ui.notificationsReady = false;
    state.ui.lastSchedulerParamsSig = null;

    document.getElementById('currentProfileLabel').textContent = getProfileDisplayLabel(profileLogin);
    document.getElementById('profilesModal').classList.add('hidden');

    // IMPORTANT: results must not leak between profiles.
    clearResultsUI();

    // Reset filters to defaults and restore per-profile state
    state.filters = getDefaultFilters();
    restoreState();

    // Restore results for this profile (if any)
    restoreResultsState();

    // Refresh dictionaries for this profile
    loadDictionaries();
    checkSchedulerStatus();
    populateTwinProfileSelect();
}

async function loadDictionaries() {
    if (!state.currentProfile) return;

    // Load Specialties
    const specRes = await fetch(`${API_BASE}/dictionaries/specialties?profile=${state.currentProfile}`, { credentials: 'include' });
    const specJson = await specRes.json();
    if (specJson.success) {
        state.specialties = specJson.data;
        renderSpecialtiesSelect();
    }

    // Load Doctors
    const docRes = await fetch(`${API_BASE}/dictionaries/doctors`, { credentials: 'include' });
    const docJson = await docRes.json();
    if (docJson.success) {
        state.doctors = docJson.data;
        filterDoctorsBySpecialty();
    }

    // Load Clinics
    const clinRes = await fetch(`${API_BASE}/dictionaries/clinics`, { credentials: 'include' });
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

        // Use select elements instead of input time to enforce 24h
        const startSelect = document.createElement('select');
        startSelect.className = 'form-control form-control-sm';
        startSelect.style.width = '80px';
        startSelect.dataset.day = idx;
        startSelect.dataset.type = 'start';
        populateTimeSelect(startSelect, saved.start);

        const endSelect = document.createElement('select');
        endSelect.className = 'form-control form-control-sm';
        endSelect.style.width = '80px';
        endSelect.dataset.day = idx;
        endSelect.dataset.type = 'end';
        populateTimeSelect(endSelect, saved.end);

        row.innerHTML = `<span style="width: 30px; font-weight:500;">${dayName}</span>`;
        row.appendChild(startSelect);
        row.insertAdjacentHTML('beforeend', '<span>-</span>');
        row.appendChild(endSelect);

        startSelect.disabled = state.ui.filtersLocked;
        endSelect.disabled = state.ui.filtersLocked;

        const updateState = () => {
            if (state.ui.filtersLocked) return;
            const s = startSelect.value;
            const e = endSelect.value;
            if (s && e) {
                state.filters.dayTimeRanges[idx] = { start: s, end: e };
            } else {
                delete state.filters.dayTimeRanges[idx];
            }
            saveState();
        };

        startSelect.addEventListener('change', updateState);
        endSelect.addEventListener('change', updateState);

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

    // Clear selection on new search
    state.selectedAppointment = null;
    document.getElementById('bookSelectedBtn').disabled = true;

    try {
        const payload = buildSearchPayload();

        const res = await fetch(`${API_BASE}/appointments/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(payload)
        });

        const json = await res.json();
        if (json.success) {
            state.searchResults = json.data;
            renderResults();
            document.getElementById('resultsSource').textContent = `(Znaleziono: ${json.count})`;
            saveState();
            saveResultsState();
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

async function handleBookSelected() {
    if (!state.selectedAppointment) {
        showToast('Nie zaznaczono wizyty!', 'error');
        return;
    }

    const btn = document.getElementById('bookSelectedBtn');
    btn.disabled = true;
    btn.textContent = 'Rezerwowanie...';

    const payload = {
        profile: state.currentProfile,
        appointment_id: state.selectedAppointment.appointmentId,
        booking_string: state.selectedAppointment.bookingString
    };

    try {
        const res = await fetch(`${API_BASE}/appointments/book`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(payload)
        });
        const json = await res.json();
        if (json.success) {
            showToast('Zarezerwowano wizytę!', 'success');
            // Remove booked appointment from list
            state.searchResults = state.searchResults.filter(a => a.appointmentId !== state.selectedAppointment.appointmentId);
            state.selectedAppointment = null;
            renderResults();
            saveResultsState();
        } else {
            showToast(json.message || json.error || 'Błąd rezerwacji', 'error');
        }
    } catch (e) {
        showToast('Błąd połączenia', 'error');
    } finally {
        btn.disabled = !state.selectedAppointment;
        btn.textContent = 'Zarezerwuj zaznaczoną';
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

function formatLocalDateInput(d) {
    if (!d || Number.isNaN(d.getTime())) return '';
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function buildFiltersFromSearchParams(searchParams) {
    const base = getDefaultFilters();
    const sp = searchParams && typeof searchParams === 'object' ? searchParams : {};

    base.specialtyIds = normalizeIdArray(sp.specialty_ids ?? sp.specialtyIds);
    base.doctorIds = normalizeIdArray(sp.doctor_ids ?? sp.doctorIds);
    base.clinicIds = normalizeIdArray(sp.clinic_ids ?? sp.clinicIds);

    // Dates
    base.dateFrom = sp.start_date ? formatLocalDateInput(parseUtcDate(sp.start_date)) : '';
    base.dateTo = sp.end_date ? formatLocalDateInput(parseUtcDate(sp.end_date)) : '';

    // Time range
    const tr = sp.time_range ?? sp.timeRange;
    if (tr && typeof tr === 'object') {
        const start = typeof tr.start === 'string' ? tr.start : base.timeRange.start;
        const end = typeof tr.end === 'string' ? tr.end : base.timeRange.end;
        base.timeRange = { start, end };
    }

    // Preferred days
    if (Array.isArray(sp.preferred_days)) {
        base.preferredDays = sp.preferred_days
            .map(v => parseInt(v, 10))
            .filter(v => Number.isFinite(v) && v >= 0 && v <= 6);
    }

    // Excluded dates
    if (Array.isArray(sp.excluded_dates)) {
        base.excludedDates = sp.excluded_dates.map(v => String(v)).filter(Boolean);
    }

    // Day-specific time ranges
    if (sp.day_time_ranges && typeof sp.day_time_ranges === 'object') {
        base.dayTimeRanges = sp.day_time_ranges;
    }

    return base;
}

function applyFiltersToUI() {
    // Dates
    const dateFromEl = document.getElementById('dateFrom');
    const dateToEl = document.getElementById('dateTo');
    if (dateFromEl && typeof state.filters.dateFrom === 'string') dateFromEl.value = state.filters.dateFrom;
    if (dateToEl && typeof state.filters.dateTo === 'string') dateToEl.value = state.filters.dateTo;

    // Time
    applyTimeRangeToUI();

    // Specialty + dependent doctors
    if (Array.isArray(state.specialties) && state.specialties.length > 0) {
        renderSpecialtiesSelect();
    }

    if (Array.isArray(state.doctors) && state.doctors.length > 0) {
        filterDoctorsBySpecialty();
    }

    if (Array.isArray(state.clinics) && state.clinics.length > 0) {
        renderDropdownList(state.clinics, 'clinicsList', 'clinicIds');
    }

    renderWeekdaysGrid();
    renderExcludedDates();
}

function syncFiltersFromSchedulerStatus(st) {
    const sp = st?.search_params;
    if (!sp || typeof sp !== 'object') return false;

    let sig = null;
    try {
        sig = JSON.stringify(sp);
    } catch (e) {
        sig = null;
    }

    if (sig && state.ui.lastSchedulerParamsSig === sig) return false;
    state.ui.lastSchedulerParamsSig = sig;

    state.filters = buildFiltersFromSearchParams(sp);
    applyFiltersToUI();
    return true;
}

function syncSchedulerOptionsFromBackend(st) {
    if (!st || typeof st !== 'object') return;

    // Restore Auto-Booking checkbox
    const autoBookEl = document.getElementById('autoBook');
    if (autoBookEl) {
        autoBookEl.checked = Boolean(st.auto_book);
    }

    // Restore Twin Booking checkbox and select
    const twinCheckEl = document.getElementById('enableTwinBooking');
    const twinSelectEl = document.getElementById('twinProfileSelect');
    
    if (twinCheckEl && twinSelectEl) {
        const twinProfile = st.twin_profile || null;
        const isTwinEnabled = Boolean(twinProfile);
        
        twinCheckEl.checked = isTwinEnabled;
        twinSelectEl.style.display = isTwinEnabled ? 'inline-block' : 'none';
        
        if (isTwinEnabled && twinProfile) {
            // Try to select the twin profile in dropdown
            const option = Array.from(twinSelectEl.options).find(opt => opt.value === twinProfile);
            if (option) {
                twinSelectEl.value = twinProfile;
            }
        }
    }

    // Restore interval
    const intervalEl = document.getElementById('checkInterval');
    if (intervalEl && st.interval_minutes) {
        intervalEl.value = String(st.interval_minutes);
    }
}

async function startScheduler() {
    updateFiltersFromUI();
    if (state.filters.specialtyIds.length === 0) {
        showToast('Wybierz specjalność!', 'error');
        return;
    }

    // Ask for permissions from a user gesture.
    unlockAudio();
    ensureNotificationPermission();

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
            credentials: 'include',
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
            credentials: 'include',
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
        const res = await fetch(`${API_BASE}/scheduler/status?profile=${state.currentProfile}`, { credentials: 'include' });
        const json = await res.json();

        const statusBox = document.getElementById('autoCheckStatus');
        const switchEl = document.getElementById('enableAutoCheck');
        const detailsRow = document.getElementById('schedulerDetailsRow');

        const st = (json && json.success) ? (json.data || null) : null;
        if (st) {
            processSchedulerNotifications(st, state.ui.notificationsReady);
            state.ui.notificationsReady = true;
        }

        if (json.success && json.data && json.data.active) {
            state.schedulerStatus = json.data;
            statusBox.textContent = 'AKTYWNY';
            statusBox.classList.add('active');
            switchEl.checked = true;

            // Sync filters to backend search_params when scheduler is active (multi-device consistency)
            if (syncFiltersFromSchedulerStatus(json.data)) {
                saveState();
            }

            // NEW: Restore scheduler options (auto-book, twin booking) from backend
            syncSchedulerOptionsFromBackend(json.data);

            // Lock all filter params when scheduler is active
            setManualSearchEnabled(false);
            setFiltersEnabled(false);
            setSchedulerOptionsEnabled(false);

            // Show details + countdown
            if (detailsRow) detailsRow.style.display = 'block';
            renderSchedulerDetails();
            startSchedulerCountdown(json.data.next_run);

            // If we have fresh results from scheduler, show them
            if (json.data.last_results && json.data.last_results.appointments) {
                state.searchResults = json.data.last_results.appointments;
                renderResults();
                document.getElementById('resultsSource').textContent = '(z Automatu)';
                saveResultsState();
            }

        } else {
            state.schedulerStatus = json.data || null;
            statusBox.textContent = 'Wyłączony';
            statusBox.classList.remove('active');
            switchEl.checked = false;

            stopSchedulerCountdown();
            if (detailsRow) detailsRow.style.display = 'none';

            state.ui.lastSchedulerParamsSig = null;

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

    // Time - UPDATED to use time inputs
    const timeFromEl = document.getElementById('timeFrom');
    const timeToEl = document.getElementById('timeTo');
    if (timeFromEl && timeFromEl.value) {
        state.filters.timeRange.start = timeFromEl.value;
    }
    if (timeToEl && timeToEl.value) {
        state.filters.timeRange.end = timeToEl.value;
    }
}

function renderResults() {
    const tbody = document.getElementById('resultsBody');
    tbody.innerHTML = '';

    if (state.searchResults.length === 0) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 5;
        td.style.textAlign = 'center';
        td.style.padding = '20px';
        td.textContent = 'Brak wyników';
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }

    state.searchResults.forEach(apt => {
        const dateObj = new Date(apt.appointmentDate);
        const tr = document.createElement('tr');
        
        tr.dataset.appointmentId = apt.appointmentId;

        // Apply selection state (without re-rendering on each click)
        if (state.selectedAppointment && state.selectedAppointment.appointmentId === apt.appointmentId) {
            tr.classList.add('selected-row');
        }

        // --- XSS PROTECTION: Use textContent / createElement instead of innerHTML ---
        const tdDate = document.createElement('td');
        tdDate.textContent = dateObj.toLocaleDateString('pl-PL');
        tr.appendChild(tdDate);

        const tdTime = document.createElement('td');
        const strongTime = document.createElement('strong');
        strongTime.textContent = dateObj.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'});
        tdTime.appendChild(strongTime);
        tr.appendChild(tdTime);

        const tdDoc = document.createElement('td');
        tdDoc.textContent = apt.doctor ? apt.doctor.name : '-';
        tr.appendChild(tdDoc);

        const tdSpec = document.createElement('td');
        tdSpec.textContent = apt.specialty ? apt.specialty.name : '-';
        tr.appendChild(tdSpec);

        const tdClinic = document.createElement('td');
        tdClinic.textContent = apt.clinic ? apt.clinic.name : '-';
        tr.appendChild(tdClinic);
        // --------------------------------------------------------------------------

        tr.onclick = () => {
            // Toggle selection
            if (state.selectedAppointment && state.selectedAppointment.appointmentId === apt.appointmentId) {
                // Deselect
                state.selectedAppointment = null;
                tr.classList.remove('selected-row');
            } else {
                // Select new, deselect previous
                const prevSelected = tbody.querySelector('tr.selected-row');
                if (prevSelected) {
                    prevSelected.classList.remove('selected-row');
                }
                state.selectedAppointment = apt;
                tr.classList.add('selected-row');
            }
            
            // Update button state
            const bookBtn = document.getElementById('bookSelectedBtn');
            bookBtn.disabled = !state.selectedAppointment;
        };

        tbody.appendChild(tr);
    });

    // Sync button state
    const bookBtn = document.getElementById('bookSelectedBtn');
    if (bookBtn) {
        bookBtn.disabled = !state.selectedAppointment;
    }
}

function setupEventListeners() {
    // Search Button
    document.getElementById('searchBtn').addEventListener('click', handleSearch);

    // Book Selected Button
    const bookBtn = document.getElementById('bookSelectedBtn');
    if (bookBtn) {
        bookBtn.addEventListener('click', handleBookSelected);
    }

    // Date/Time changes (persist immediately)
    ['dateFrom', 'dateTo', 'timeFrom', 'timeTo'].forEach(id => {
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
        
        // Clear selection + results
        clearResultsUI();
        saveResultsState();

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

function formatCountdown(nextRunIsoStr) {
    const d = parseUtcDate(nextRunIsoStr);
    if (!d || Number.isNaN(d.getTime())) return '--:--';

    // ceil => bardziej "uczciwe" odliczanie (np. po opóźnieniach sieciowych / selenium)
    const diffSec = Math.max(0, Math.ceil((d.getTime() - Date.now()) / 1000));

    const h = Math.floor(diffSec / 3600);
    const m = Math.floor((diffSec % 3600) / 60);
    const s = diffSec % 60;

    const pad2 = (n) => String(n).padStart(2, '0');

    if (h > 0) {
        return `${pad2(h)}:${pad2(m)}:${pad2(s)}`;
    }
    return `${pad2(m)}:${pad2(s)}`;
}

function renderSchedulerDetails() {
    const detailsRow = document.getElementById('schedulerDetailsRow');
    const detailsText = document.getElementById('schedulerDetails');
    if (!detailsRow || !detailsText) return;

    const st = state.schedulerStatus;
    if (!st || !st.active) {
        detailsRow.style.display = 'none';
        return;
    }

    detailsRow.style.display = 'block';

    const runsCount = st.runs_count ?? 0;
    const countdown = formatCountdown(st.next_run);

    let info = `Następne za: ${countdown} | Przebiegi: ${runsCount}`;

    if (st.last_results) {
        const cnt = st.last_results.count ?? 0;
        info += ` | Ost. wynik: ${cnt} wizyt (${formatTime(st.last_results.timestamp, true)})`;
    }

    if (st.expires_at) {
        info += ` | ⏳ Do: ${formatTime(st.expires_at)}`;
    }

    if (st.twin_profile) {
        info += ` | 👯 Tryb Bliźniak: ${getProfileDisplayLabel(st.twin_profile)}`;
    }

    detailsText.textContent = info;
}

function startSchedulerCountdown(nextRunIsoStr) {
    if (!nextRunIsoStr) {
        stopSchedulerCountdown();
        return;
    }

    // Jeśli next_run się nie zmienił – nie restartuj interwału.
    if (schedulerCountdownInterval && schedulerCountdownNextRunIso === nextRunIsoStr) {
        return;
    }

    stopSchedulerCountdown();
    schedulerCountdownNextRunIso = nextRunIsoStr;

    schedulerCountdownInterval = setInterval(() => {
        if (!state.schedulerStatus || !state.schedulerStatus.active) {
            stopSchedulerCountdown();
            return;
        }
        renderSchedulerDetails();
    }, 1000);
}

function stopSchedulerCountdown() {
    if (schedulerCountdownInterval) {
        clearInterval(schedulerCountdownInterval);
        schedulerCountdownInterval = null;
    }
    schedulerCountdownNextRunIso = null;
}

function formatTime(isoStr, includeSeconds = false) {
    const d = parseUtcDate(isoStr);
    if (!d || Number.isNaN(d.getTime())) return includeSeconds ? '--:--:--' : '--:--';

    const opts = { hour: '2-digit', minute: '2-digit' };
    if (includeSeconds) {
        opts.second = '2-digit';
    }

    return d.toLocaleTimeString('pl-PL', opts);
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
            credentials: 'include',
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

    // Apply time range to UI (timeFrom/timeTo)
    applyTimeRangeToUI();

    // Restore other UI elements
    renderExcludedDates();
}

function saveResultsState() {
    const key = getResultsStorageKey();
    if (!key) return;

    try {
        const payload = {
            results: Array.isArray(state.searchResults) ? state.searchResults : [],
            resultsSource: (document.getElementById('resultsSource')?.textContent) || '',
            ts: new Date().toISOString()
        };
        localStorage.setItem(key, JSON.stringify(payload));
    } catch (e) {
        console.warn('LocalStorage save results failed', key, e);
    }
}

function restoreResultsState() {
    const key = getResultsStorageKey();
    if (!key) return;

    const raw = lsGet(key);
    if (!raw) return;

    try {
        const parsed = JSON.parse(raw);
        const results = Array.isArray(parsed?.results) ? parsed.results : [];
        const srcText = typeof parsed?.resultsSource === 'string' ? parsed.resultsSource : '';

        state.searchResults = results;
        state.selectedAppointment = null;
        renderResults();

        const src = document.getElementById('resultsSource');
        if (src) src.textContent = srcText;
    } catch (e) {
        console.warn('LocalStorage restore results failed', key, e);
    }
}
