import { countLabel, h, btn, norm } from '../shared.js';
import { statusOf, itemLabel, profileLabel, statusLabel } from './common.js';

export const PAGE_SIZE = 10;

const TYPE_OPTIONS = [
  ['all', 'Todos'],
  ['movie', 'Filme'],
  ['series', 'Série'],
  ['anime', 'Anime'],
];

const STATUS_ORDER = [
  'request_pending',
  'request_approved',
  'downloading',
  'queued',
  'searching',
  'requested',
  'downloaded',
  'partial',
  'missing',
  'error',
  'request_declined',
  'request_failed',
  'request_completed',
];

const GROUPS = {
  done: ['downloaded', 'partial', 'request_completed'],
  active: ['downloading', 'queued', 'searching', 'requested', 'request_pending', 'request_approved'],
  seerr: ['request_pending', 'request_approved'],
  attention: ['error', 'request_declined', 'request_failed'],
  missing: ['missing'],
};


function itemDate(item) {
  const candidates = [
    item.requestedAt,
    item.addedAt,
    item.dateAdded,
    item.createdAt,
    item.seerr && item.seerr.requestedAt,
    item.seerr && item.seerr.updatedAt,
    item.lastEvent && item.lastEvent.date,
    item.completedAt,
  ];
  for (const value of candidates) {
    if (!value) continue;
    const time = new Date(value).getTime();
    if (!Number.isNaN(time)) return time;
  }
  return 0;
}

function groupForStatuses(selected) {
  for (const [key, statuses] of Object.entries(GROUPS)) {
    if (statuses.length === selected.length && statuses.every((status) => selected.includes(status))) {
      return key;
    }
  }
  return null;
}

export function createFilters(ctx) {
  const { state, dom, helpers } = ctx;
  let shell = null;
  let backdrop = null;
  let previousFocus = null;
  let draft = null;

  function currentItems() {
    return state.view === 'history' ? state.historyItems : state.items;
  }

  let namesCache = { signature: '', map: new Map() };

  function profileNames() {
    const signature = `${state.lastLoaded}:${state.lastHistoryLoaded}:${state.items.length}:${state.historyItems.length}`;
    if (namesCache.signature === signature) return namesCache.map;
    const map = new Map();
    for (const source of [state.items, state.historyItems, state.profiles]) {
      for (const item of source || []) {
        if (!item || typeof item === 'string') continue;
        const id = item.profileId ?? item.id;
        const name = item.profileName || item.name;
        if (id == null || !name) continue;
        const kind = item.kind === 'episode' ? 'series' : item.kind;
        const key = kind ? `${kind}:${id}` : null;
        if (key && !map.has(key)) map.set(key, profileLabel(name));
      }
    }
    namesCache = { signature, map };
    return map;
  }

  function profileNameOf(item) {
    const direct = item.profileName || item.profile;
    const seerr = item.seerr && (item.seerr.profileName || item.seerr.profile);
    if (direct) return profileLabel(direct);
    if (seerr) return profileLabel(seerr);
    const id = item.profileId ?? (item.seerr && item.seerr.profileId);
    if (id != null) {
      const kind = item.kind === 'episode' ? 'series' : item.kind;
      const key = kind ? `${kind}:${id}` : null;
      return (key && profileNames().get(key)) || `Perfil ${id}`;
    }
    return '';
  }

  function typeOf(item) {
    const profile = norm(profileNameOf(item));
    const animeProfile = /anime/.test(profile);
    if (item.kind === 'movie') return animeProfile ? 'anime' : 'movie';
    if (item.kind === 'series' || item.kind === 'episode') {
      if (item.seriesType === 'anime' || animeProfile) return 'anime';
      return 'series';
    }
    return 'other';
  }

  function profileEntries() {
    const counts = new Map();
    const items = currentItems();
    for (const item of items) {
      const name = profileNameOf(item);
      if (!name) continue;
      counts.set(name, (counts.get(name) || 0) + 1);
    }
    const otherItems = state.view === 'history' ? state.items : state.historyItems;
    for (const item of otherItems) {
      const name = profileNameOf(item);
      if (name && !counts.has(name)) counts.set(name, 0);
    }
    for (const profile of state.profiles || []) {
      const name = typeof profile === 'string'
        ? profileLabel(profile)
        : profileLabel(profile.name || profile.profileName || (profile.id != null ? `Perfil ${profile.id}` : ''));
      if (name && !counts.has(name)) counts.set(name, 0);
    }
    return [...counts.entries()]
      .map(([value, count]) => ({ value, label: value, count }))
      .sort((a, b) => a.label.localeCompare(b.label, 'pt-BR', { numeric: true, sensitivity: 'base' }));
  }

  function statusCounts() {
    const counts = new Map();
    for (const item of currentItems()) {
      const status = statusOf(item);
      counts.set(status, (counts.get(status) || 0) + 1);
    }
    return counts;
  }

  function matchesType(item) {
    return state.typeFilter === 'all' || typeOf(item) === state.typeFilter;
  }

  function matchesProfile(item) {
    if (state.profileFilter === 'all') return true;
    return norm(profileNameOf(item)) === norm(state.profileFilter);
  }

  function matchesStatus(item) {
    const status = statusOf(item);
    if (state.statusFilter.length) return state.statusFilter.includes(status);
    const group = state.filter;
    if (group && group !== 'all' && GROUPS[group]) return GROUPS[group].includes(status);
    return true;
  }

  function matches(item) {
    return matchesType(item) && matchesProfile(item) && matchesStatus(item);
  }

  function sortItems(rows) {
    return rows.slice().sort((a, b) => {
      const diff = itemDate(b) - itemDate(a);
      if (diff) return diff;
      return itemLabel(a).localeCompare(itemLabel(b), 'pt-BR', { numeric: true, sensitivity: 'base' });
    });
  }

  function statusFilterActive() {
    if (state.statusFilter.length) return true;
    return Boolean(state.filter && state.filter !== 'all' && GROUPS[state.filter]);
  }

  function activeCount() {
    return (state.typeFilter !== 'all' ? 1 : 0)
      + (state.profileFilter !== 'all' ? 1 : 0)
      + (statusFilterActive() ? 1 : 0);
  }

  function updateButton() {
    if (!dom.filtersBtn) return;
    const count = activeCount();
    dom.filtersBtn.textContent = count ? `Filtros (${count})` : 'Filtros';
    dom.filtersBtn.dataset.count = String(count);
    dom.filtersBtn.setAttribute('aria-label', count ? `Filtros (${count} ativos)` : 'Filtros');
  }

  function close() {
    if (shell && shell._keydown) document.removeEventListener('keydown', shell._keydown);
    if (shell) shell.remove();
    if (backdrop) backdrop.remove();
    shell = null;
    backdrop = null;
    if (dom.filtersBtn) dom.filtersBtn.setAttribute('aria-expanded', 'false');
    if (previousFocus && previousFocus.isConnected && typeof previousFocus.focus === 'function') {
      previousFocus.focus();
    }
    previousFocus = null;
  }

  function open() {
    close();
    previousFocus = document.activeElement;
    if (dom.filtersBtn) dom.filtersBtn.setAttribute('aria-expanded', 'true');

    const initialStatuses = state.statusFilter.length
      ? state.statusFilter
      : (state.filter && GROUPS[state.filter] ? GROUPS[state.filter] : STATUS_ORDER);

    draft = {
      typeFilter: state.typeFilter,
      profileFilter: state.profileFilter,
      statuses: new Set(initialStatuses),
    };

    backdrop = h('div', 'hx-backdrop', '');
    backdrop.addEventListener('click', close);

    shell = h('div', 'hx-shell hx-shell-filters', '');
    shell.setAttribute('role', 'dialog');
    shell.setAttribute('aria-modal', 'true');
    shell.setAttribute('aria-labelledby', 'hx-filter-title');
    shell.tabIndex = -1;

    const head = h('div', 'hx-head', '');
    const headWrap = h('div', '', '');
    const title = h('h2', 'hx-head-title', 'Filtros');
    title.id = 'hx-filter-title';
    const sub = h('span', 'hx-head-sub', '');
    headWrap.append(title, sub);
    const closeBtn = btn('Fechar', '', close);
    head.append(headWrap, closeBtn);

    const body = h('div', 'hx-body', '');

    const typeGroup = h('div', 'hx-filter-group', '');
    typeGroup.appendChild(h('div', 'hx-filter-label', 'Tipo'));
    const typeChips = h('div', 'hx-filter-chips', '');
    const typeButtons = new Map();
    for (const [value, label] of TYPE_OPTIONS) {
      const button = btn(label, 'hx-chip', () => {
        draft.typeFilter = value;
        refresh();
      });
      typeButtons.set(value, button);
      typeChips.appendChild(button);
    }
    typeGroup.appendChild(typeChips);

    const profileGroup = h('div', 'hx-filter-group', '');
    profileGroup.appendChild(h('div', 'hx-filter-label', 'Perfil'));
    const profileSelect = h('select', 'hx-select');
    profileSelect.setAttribute('aria-label', 'Filtrar por perfil');
    const profileEntriesList = profileEntries();
    const allProfile = h('option', '', 'Todos os perfis');
    allProfile.value = 'all';
    profileSelect.appendChild(allProfile);
    for (const profile of profileEntriesList) {
      const option = h('option', '', profile.count ? `${profile.label} (${profile.count})` : profile.label);
      option.value = profile.value;
      profileSelect.appendChild(option);
    }
    profileSelect.disabled = !profileEntriesList.length;
    profileSelect.addEventListener('change', () => {
      draft.profileFilter = profileSelect.value;
      refresh();
    });
    profileGroup.appendChild(profileSelect);

    const statusGroup = h('div', 'hx-filter-group', '');
    const statusHead = h('div', 'hx-filter-status-head', '');
    statusHead.appendChild(h('div', 'hx-filter-label', 'Status'));
    const statusActions = h('div', 'hx-filter-status-actions', '');
    const allStatuses = btn('Todos', '', () => {
      draft.statuses = new Set(STATUS_ORDER);
      refresh();
    });
    const noStatuses = btn('Nenhum', '', () => {
      draft.statuses = new Set();
      refresh();
    });
    statusActions.append(allStatuses, noStatuses);
    statusHead.appendChild(statusActions);
    statusGroup.appendChild(statusHead);

    const statusGrid = h('div', 'hx-filter-grid', '');
    const statusInputs = new Map();
    const counts = statusCounts();
    for (const status of STATUS_ORDER) {
      const label = h('label', 'hx-check');
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.value = status;
      input.addEventListener('change', () => {
        if (input.checked) draft.statuses.add(status);
        else draft.statuses.delete(status);
        refresh();
      });
      statusInputs.set(status, input);
      const count = counts.get(status) || 0;
      const text = statusLabel(status);
      label.append(input, document.createTextNode(count ? `${text} (${count})` : text));
      statusGrid.appendChild(label);
    }
    statusGroup.appendChild(statusGrid);
    const note = h('div', 'hx-muted', 'Nenhum status marcado = todos.');
    note.style.fontSize = '11px';
    note.style.marginTop = '6px';
    statusGroup.appendChild(note);

    const actions = h('div', 'hx-filter-actions', '');
    const clear = btn('Limpar filtros', '', () => {
      draft = {
        typeFilter: 'all',
        profileFilter: 'all',
        statuses: new Set(STATUS_ORDER),
      };
      refresh();
    });
    const apply = btn('Aplicar', 'hx-btn-primary', () => {
      state.typeFilter = draft.typeFilter;
      state.profileFilter = draft.profileFilter;
      const keepHistoryChip = state.view === 'history'
        && (state.filter === 'archived' || state.filter === 'episodes');
      const selected = STATUS_ORDER.filter((status) => draft.statuses.has(status));
      if (!selected.length || selected.length === STATUS_ORDER.length) {
        state.statusFilter = [];
        if (!keepHistoryChip) {
          state.filter = 'all';
          if (dom.filterSelect) dom.filterSelect.value = 'all';
        }
      } else {
        const group = groupForStatuses(selected);
        if (group) {
          state.filter = group;
          state.statusFilter = [];
          if (dom.filterSelect) dom.filterSelect.value = group;
        } else {
          state.filter = 'all';
          state.statusFilter = selected;
          if (dom.filterSelect) dom.filterSelect.value = 'all';
        }
      }
      state.page = 1;
      updateButton();
      helpers.renderCurrent();
      close();
    });
    actions.append(clear, apply);

    body.append(typeGroup, profileGroup, statusGroup);
    if (state.view === 'history') {
      const historyNote = h('div', 'hx-muted', 'No Histórico, os filtros valem para os registros já carregados.');
      historyNote.style.fontSize = '11px';
      historyNote.style.marginTop = '2px';
      body.appendChild(historyNote);
    }
    body.appendChild(actions);
    shell.append(head, body);

    shell._keydown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== 'Tab') return;
      const focusable = [...shell.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
        .filter((element) => !element.disabled && element.getClientRects().length > 0);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !shell.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !shell.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', shell._keydown);

    function refresh() {
      for (const [value, button] of typeButtons) {
        button.setAttribute('aria-pressed', String(draft.typeFilter === value));
      }
      const knownProfile = profileEntriesList.some((profile) => profile.value === draft.profileFilter);
      if (!knownProfile) draft.profileFilter = 'all';
      profileSelect.value = draft.profileFilter;
      for (const [status, input] of statusInputs) {
        input.checked = draft.statuses.has(status);
      }
      const count = currentItems().filter((item) => {
        if (draft.typeFilter !== 'all' && typeOf(item) !== draft.typeFilter) return false;
        if (draft.profileFilter !== 'all' && norm(profileNameOf(item)) !== norm(draft.profileFilter)) return false;
        if (draft.statuses.size && !draft.statuses.has(statusOf(item))) return false;
        return true;
      }).length;
      const label = state.view === 'history'
        ? countLabel(count, 'registro', 'registros')
        : countLabel(count, 'pedido', 'pedidos');
      sub.textContent = `${label} correspondem`;
    }

    refresh();
    document.body.append(backdrop, shell);
    closeBtn.focus();
  }

  updateButton();

  return {
    open,
    close,
    matches,
    matchesType,
    matchesProfile,
    matchesStatus,
    sortItems,
    activeCount,
    updateButton,
    typeOf,
    itemDate,
  };
}
