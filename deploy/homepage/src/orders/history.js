import { norm, countLabel, h, btn, toast, fmtDate } from '../shared.js';
import { statusOf, historyLabel, statusLabel, statusMessageFor, displayMessage, messageMatchesStatus, profileLabel, SOURCE_LABELS, ordersApi } from './common.js';

export function createHistory(ctx) {
  const { state, dom, helpers } = ctx;

  function filteredHistory() {
    const q = norm(state.query);
    return state.historyItems.filter((item) => {
      if (q && !norm(historyLabel(item)).includes(q)) return false;
      if (state.originFilter !== 'all' && item.source !== state.originFilter) return false;
      const s = statusOf(item);
      if (state.filter === 'all') return true;
      if (state.filter === 'archived') return item.hidden;
      if (state.filter === 'episodes') return item.kind === 'episode';
      if (state.filter === 'active') return s === 'downloading' || s === 'queued' || s === 'searching' || s === 'requested' || s === 'request_pending' || s === 'request_approved';
      if (state.filter === 'seerr') return s === 'request_pending' || s === 'request_approved' || s === 'request_completed';
      if (state.filter === 'attention') return s === 'error' || s === 'request_declined' || s === 'request_failed';
      if (state.filter === 'done') return s === 'downloaded' || s === 'partial' || s === 'request_completed';
      if (state.filter === 'missing') return s === 'missing';
      return true;
    });
  }

  async function loadHistory(reset) {
    if (state.historyLoading) return;
    state.historyLoading = true;
    dom.refreshBtn.disabled = true;
    dom.refreshBtn.textContent = 'Carregando...';
    if (reset) {
      state.historyPage = 1;
      state.historyItems = [];
    }
    if (state.view === 'history') helpers.setStatus('Carregando histórico...');
    try {
      const payload = await ordersApi(`/requests?view=history&page=${state.historyPage}&pageSize=100&events=1`);
      state.historyItems = reset ? (payload.items || []) : state.historyItems.concat(payload.items || []);
      state.historyTotal = payload.total || 0;
      state.historyCounts = payload.counts || {};
      state.hiddenCount = payload.hiddenCount || 0;
      state.lastHistoryLoaded = Date.now();
      renderHistory();
      const c = state.historyCounts;
      const done = (c.downloaded || 0) + (c.partial || 0) + (c.request_completed || 0);
      const activeCount = (c.request_pending || 0) + (c.request_approved || 0) + (c.downloading || 0) + (c.queued || 0) + (c.searching || 0) + (c.requested || 0);
      const errors = (c.error || 0) + (c.request_failed || 0) + (c.request_declined || 0);
      helpers.setStatus(`${countLabel(state.historyTotal, 'registro', 'registros')} no histórico • ${countLabel(done, 'baixado', 'baixados')}, ${activeCount} em andamento, ${errors} com erro • atualizado ${new Date().toLocaleTimeString()}`, errors ? '#f59e0b' : '#9aa0a6');
    } catch (e) {
      helpers.setStatus('Erro ao carregar histórico: ' + e.message, '#f87171');
    } finally {
      state.historyLoading = false;
      dom.refreshBtn.disabled = false;
      dom.refreshBtn.textContent = 'Atualizar';
    }
  }

  function historyChip(label, key, count, color) {
    const chip = h('button', 'hx-chip', '');
    chip.type = 'button';
    chip.setAttribute('aria-pressed', state.filter === key ? 'true' : 'false');
    const dot = h('span', 'hx-dot', '');
    dot.style.background = color;
    chip.append(dot, h('span', '', label), h('b', '', String(count)));
    chip.addEventListener('click', () => {
      state.filter = state.filter === key ? 'all' : key;
      dom.filterSelect.value = state.filter;
      helpers.renderCurrent();
    });
    return chip;
  }

  function renderHistory() {
    const c = state.historyCounts || {};
    const done = (c.downloaded || 0) + (c.partial || 0) + (c.request_completed || 0);
    const activeCount = (c.request_pending || 0) + (c.request_approved || 0) + (c.downloading || 0) + (c.queued || 0) + (c.searching || 0) + (c.requested || 0);
    const errors = (c.error || 0) + (c.request_failed || 0) + (c.request_declined || 0);
    const episodesCount = state.historyItems.filter((item) => item.kind === 'episode').length;
    dom.historySummary.innerHTML = '';
    dom.historySummary.append(
      historyChip('Todos', 'all', state.historyTotal, '#9aa0a6'),
      historyChip('Baixados', 'done', done, '#4ade80'),
      historyChip('Em andamento', 'active', activeCount, '#60a5fa'),
      historyChip('Erros', 'attention', errors, '#f87171'),
      historyChip('Sem arquivo', 'missing', c.missing || 0, '#a1a1aa'),
      historyChip('Episódios', 'episodes', episodesCount, '#38bdf8'),
      historyChip('Arquivados', 'archived', state.hiddenCount, '#c084fc'),
    );

    dom.historyActions.innerHTML = '';
    const archivedKeys = state.historyItems.filter((item) => item.hidden).map((item) => item.key);
    const clear = btn('Apagar arquivados carregados', '', async () => {
      if (clear.disabled) return;
      if (!archivedKeys.length) {
        toast('Nenhum arquivado carregado', false);
        return;
      }
      if (!confirm(`Apagar ${countLabel(archivedKeys.length, 'registro arquivado', 'registros arquivados')} definitivamente?`)) return;
      clear.disabled = true;
      clear.textContent = 'Apagando...';
      try {
        await ordersApi('/requests/delete', 'POST', { keys: archivedKeys, confirm: true });
        toast('Arquivados apagados');
        await loadHistory(true);
        helpers.updateCount();
      } catch (e) {
        toast('Erro ao apagar: ' + e.message, false);
      } finally {
        if (clear.isConnected) {
          clear.disabled = !archivedKeys.length;
          clear.textContent = 'Apagar arquivados carregados';
        }
      }
    });
    clear.disabled = !archivedKeys.length;
    clear.title = 'Apaga somente os arquivados carregados nesta lista (página atual)';
    dom.historyActions.appendChild(clear);

    const rows = filteredHistory();
    dom.historyList.innerHTML = '';
    if (!rows.length) {
      dom.historyList.appendChild(h('div', 'hx-empty', state.historyItems.length ? 'Nenhum registro corresponde ao filtro.' : 'Histórico vazio.'));
    } else {
      for (const item of rows) dom.historyList.appendChild(renderHistoryItem(item));
    }
    dom.historyMore.hidden = state.historyItems.length >= state.historyTotal;
    dom.historyMore.textContent = `Carregar mais (${Math.max(0, state.historyTotal - state.historyItems.length)})`;
  }

  function dateParts(value) {
    if (!value) return { date: 'sem data', time: '' };
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return { date: String(value), time: '' };
    return { date: d.toLocaleDateString(), time: d.toLocaleTimeString() };
  }

  function renderHistoryItem(item) {
    const statusKey = statusOf(item);
    const box = h('article', 'hx-hist', '');
    const dateValue = item.requestedAt || item.completedAt;
    const parts = dateParts(dateValue);
    const dateWrap = h('div', 'hx-hist-date', '');
    dateWrap.appendChild(h('span', 'hx-hist-date-label', item.requestedAt ? (item.source === 'seerr' ? 'pedido' : 'adicionado') : 'concluído'));
    dateWrap.appendChild(h('span', '', parts.date));
    if (parts.time) dateWrap.appendChild(h('span', 'hx-hist-time', parts.time));

    const main = h('div', 'hx-hist-main', '');
    const titleWrap = h('div', 'hx-hist-title', '');
    const kind = item.kind === 'movie' ? 'Filme' : item.kind === 'series' ? 'Série' : 'Episódio';
    titleWrap.append(h('span', 'hx-kind', kind), document.createTextNode(historyLabel(item)));
    main.appendChild(titleWrap);

    const bits = [];
    if (item.source) bits.push(SOURCE_LABELS[item.source] || item.source);
    if (item.profileName) bits.push('perfil ' + profileLabel(item.profileName));
    if (item.requestedBy) bits.push('por ' + item.requestedBy);
    const seerrDone = item.source === 'seerr' && statusKey === 'request_completed';
    if (seerrDone) {
      bits.push(item.completedAt ? 'concluído em ' + fmtDate(item.completedAt) + ' (aprox.)' : 'concluído sem data');
    } else if (item.completedAt) {
      bits.push('concluído em ' + fmtDate(item.completedAt));
    }
    if (bits.length) main.appendChild(h('div', 'hx-hist-meta', bits.join(' • ')));

    const msg = statusMessageFor(item);
    const showMsg = msg && !((statusKey === 'downloaded' || statusKey === 'partial') && /^arquivo presente/i.test(msg));
    if (showMsg) main.appendChild(h('div', 'hx-hist-event', msg));

    const events = (item.events || []).filter((event) => event.status === statusKey);
    if (events.length) {
      const last = events[events.length - 1];
      const lastMessage = displayMessage(last.message);
      const meaningful = lastMessage && lastMessage !== msg && messageMatchesStatus(lastMessage, last.status) && !/^arquivo presente/i.test(lastMessage);
      const showEvent = ['error', 'missing', 'request_failed', 'request_declined'].includes(statusKey) || meaningful;
      if (showEvent) {
        const when = last.at ? ' • ' + fmtDate(last.at) : '';
        main.appendChild(h('div', 'hx-hist-event', 'Último evento: ' + (statusLabel(last.status) || 'evento') + when + (meaningful ? ' — ' + lastMessage : '')));
      }
    }

    const side = h('div', 'hx-hist-side', '');
    const badges = h('div', 'hx-hist-badges', '');
    badges.appendChild(h('span', 'hx-status hx-status-' + statusKey, statusLabel(statusKey)));
    badges.appendChild(h('span', 'hx-hist-badge ' + (item.hidden ? 'hx-hist-badge-archived' : 'hx-hist-badge-active'), item.hidden ? 'Arquivado' : 'Ativo'));
    side.appendChild(badges);

    const actions = h('div', 'hx-hist-actions', '');
    const runAction = async (button, busyLabel, fn) => {
      if (button.disabled) return;
      const previous = button.textContent;
      button.disabled = true;
      button.textContent = busyLabel;
      try { await fn(); } finally {
        if (button.isConnected) {
          button.disabled = false;
          button.textContent = previous;
        }
      }
    };
    if (item.hidden) {
      const restore = btn('Restaurar', '', null);
      restore.addEventListener('click', () => runAction(restore, 'Restaurando...', async () => {
        try {
          await ordersApi('/requests/restore', 'POST', { keys: [item.key] });
          toast('Restaurado: ' + historyLabel(item));
          await loadHistory(true);
          helpers.updateCount();
        } catch (e) {
          toast('Erro ao restaurar: ' + e.message, false);
        }
      }));
      actions.appendChild(restore);
      const erase = btn('Apagar', '', null);
      erase.addEventListener('click', () => runAction(erase, 'Apagando...', async () => {
        if (!confirm(`Apagar definitivamente "${historyLabel(item)}" do histórico?`)) return;
        try {
          await ordersApi('/requests/delete', 'POST', { keys: [item.key], confirm: true });
          toast('Apagado do histórico: ' + historyLabel(item));
          await loadHistory(true);
          helpers.updateCount();
        } catch (e) {
          toast('Erro ao apagar: ' + e.message, false);
        }
      }));
      actions.appendChild(erase);
    } else {
      const archive = btn('Arquivar', '', null);
      archive.addEventListener('click', () => runAction(archive, 'Arquivando...', async () => {
        try {
          await ordersApi('/requests/hide', 'POST', { keys: [item.key] });
          toast('Arquivado: ' + historyLabel(item));
          await loadHistory(true);
          helpers.updateCount();
        } catch (e) {
          toast('Erro ao arquivar: ' + e.message, false);
        }
      }));
      actions.appendChild(archive);
    }
    side.appendChild(actions);
    box.append(dateWrap, main, side);
    return box;
  }

  return { loadHistory, renderHistory };
}
