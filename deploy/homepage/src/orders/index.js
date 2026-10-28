import { SERVICE_HOST, countLabel, h, btn, setTabCount, helpBox } from '../shared.js';
import { ordersApi } from './common.js';
import { createActive } from './active.js';
import { createHistory } from './history.js';
import { createEpisodes } from './episodes.js';
import { createAddSeries } from './add-series.js';

export function initOrders(root) {
  const state = {
    items: [],
    episodeItems: [],
    historyItems: [],
    historyTotal: 0,
    historyCounts: {},
    hiddenCount: 0,
    historyPage: 1,
    historyLoading: false,
    lastHistoryLoaded: 0,
    view: 'active',
    filter: 'all',
    originFilter: 'all',
    query: '',
    loading: false,
    busy: false,
    lastLoaded: 0,
  };

  const searchInput = h('input', 'hx-input hx-search');
  searchInput.type = 'search';
  searchInput.placeholder = 'Filtrar pedidos por título...';
  searchInput.setAttribute('aria-label', 'Filtrar pedidos por título');

  const filterSelect = h('select', 'hx-select');
  filterSelect.setAttribute('aria-label', 'Filtrar pedidos por status');
  const ACTIVE_FILTERS = [
    ['all', 'Todos'],
    ['active', 'Em andamento'],
    ['done', 'Baixados'],
    ['attention', 'Precisam de atenção'],
    ['missing', 'Sem arquivo'],
    ['seerr', 'No Seerr'],
  ];
  const HISTORY_FILTERS = [
    ['all', 'Todos'],
    ['done', 'Baixados'],
    ['active', 'Em andamento'],
    ['attention', 'Erros'],
    ['missing', 'Sem arquivo'],
    ['episodes', 'Episódios'],
    ['archived', 'Arquivados'],
  ];

  const originSelect = h('select', 'hx-select hx-origin');
  originSelect.setAttribute('aria-label', 'Filtrar histórico por origem');
  for (const [value, label] of [['all', 'Origem: todas'], ['seerr', 'Origem: Seerr'], ['manual', 'Origem: Manual'], ['backfill', 'Origem: Importado do Sonarr'], ['arr', 'Origem: Radarr/Sonarr']]) {
    const opt = h('option', '', label);
    opt.value = value;
    originSelect.appendChild(opt);
  }
  originSelect.hidden = true;

  const refreshBtn = btn('Atualizar', 'hx-refresh', () => (state.view === 'history' ? history.loadHistory(true) : load(false)));
  const toolbar = h('div', 'hx-toolbar', '');
  toolbar.append(searchInput, filterSelect, originSelect, refreshBtn);

  function updateFilterOptions() {
    const options = state.view === 'history' ? HISTORY_FILTERS : ACTIVE_FILTERS;
    filterSelect.innerHTML = '';
    for (const [value, label] of options) {
      const opt = h('option', '', label);
      opt.value = value;
      filterSelect.appendChild(opt);
    }
    if (!options.some(([value]) => value === state.filter)) state.filter = 'all';
    filterSelect.value = state.filter;
  }

  const summary = h('div', 'hx-summary', '');
  const status = h('div', 'hx-muted', '');
  const statusText = h('span', '', 'Carregando pedidos...');
  status.appendChild(statusText);
  status.style.marginBottom = '10px';
  const list = h('div', '', '');

  const activeBtn = btn('Ativos', '', () => setView('active'));
  const historyBtn = btn('Histórico', '', () => setView('history'));
  const segments = h('div', 'hx-seg', '');
  segments.append(activeBtn, historyBtn);

  const archivedLink = h('button', 'hx-btn hx-btn-link', '');
  archivedLink.type = 'button';
  archivedLink.hidden = true;
  archivedLink.addEventListener('click', () => {
    state.filter = 'archived';
    setView('history');
  });

  const seerrLink = h('a', 'hx-btn hx-btn-primary', 'Abrir Seerr');
  seerrLink.href = `http://${SERVICE_HOST}:5055`;
  seerrLink.target = '_blank';
  seerrLink.rel = 'noopener';
  seerrLink.title = 'Abrir o Seerr para pedir filmes e séries';

  archivedLink.style.marginLeft = '8px';
  status.appendChild(archivedLink);
  const viewBar = h('div', 'hx-viewbar', '');
  viewBar.appendChild(segments);

  const episodeSection = h('div', 'hx-episode-section', '');
  const episodeHead = h('div', 'hx-group-head', '');
  const episodeTitle = h('div', 'hx-group-title', 'Episódios pedidos');
  episodeHead.appendChild(episodeTitle);
  const episodeNote = h('div', 'hx-muted hx-episode-note', 'Séries fora dos perfis dublados (ex.: Bleach) também aparecem aqui; o perfil é mostrado no modal de episódios.');
  episodeNote.style.fontSize = '11px';
  episodeNote.style.margin = '0 0 6px';
  const episodeList = h('div', '', '');
  episodeSection.append(episodeHead, episodeNote, episodeList);

  const historySection = h('div', 'hx-history-section', '');
  const historySummary = h('div', 'hx-summary', '');
  const historyActions = h('div', 'hx-order-actions', '');
  historyActions.style.marginBottom = '10px';
  const historyList = h('div', '', '');
  const historyMore = btn('Carregar mais', '', () => {
    state.historyPage += 1;
    history.loadHistory(false);
  });
  historyMore.hidden = true;
  historySection.append(historySummary, historyActions, historyList, historyMore);

  const help = helpBox([
    'Ativos mostra os perfis dublados do Radarr/Sonarr e os pedidos do Seerr.',
    '“Adicionar série/anime” usa o Sonarr. Filmes e pedidos gerais são feitos no Seerr (busca do topo ou “Abrir Seerr”).',
    'Ciclo: Pendente → Aprovado → Procurando → Baixando → Baixado.',
    'Pedidos (vídeo) e Legendas (legenda) são fluxos separados.',
    'O Histórico guarda tudo que já passou; arquivar não apaga. Ele começa na implementação e pedidos antigos só aparecem se foram importados.',
    'Itens não monitorados ou fora dos perfis 8/9 podem sair do Ativos; o Histórico mantém.',
    'No modo remoto (Tailscale), os cards de gestão ficam ocultos; use Pedidos e Legendas.',
    'Para ligar o PC no modo remoto, use a senha definida no servidor.',
  ]);

  const dom = {
    searchInput,
    filterSelect,
    originSelect,
    refreshBtn,
    toolbar,
    summary,
    status,
    list,
    activeBtn,
    historyBtn,
    segments,
    viewBar,
    archivedLink,
    seerrLink,
    episodeSection,
    episodeHead,
    episodeTitle,
    episodeList,
    historySection,
    historySummary,
    historyActions,
    historyList,
    historyMore,
  };

  const ctx = { state, dom, helpers: {} };
  const active = createActive(ctx);
  const history = createHistory(ctx);
  const episodes = createEpisodes(ctx);
  const add = createAddSeries(ctx);
  add.bar.appendChild(seerrLink);

  root.append(help, viewBar, add.bar, add.body, toolbar, summary, status, list, episodeSection, historySection);

  function setStatus(text, color) {
    statusText.textContent = text;
    dom.status.style.color = color || '#9aa0a6';
  }

  function publish(rows, episodeTotal = 0) {
    setTabCount('pedidos', rows.length + episodeTotal);
  }

  function updateArchivedLink() {
    dom.archivedLink.hidden = state.view !== 'active' || state.hiddenCount <= 0;
    dom.archivedLink.textContent = `${countLabel(state.hiddenCount, 'arquivado', 'arquivados')} — ver no Histórico`;
  }

  async function updateCount() {
    try {
      const [payload, episodePayload, historyPayload] = await Promise.all([
        ordersApi('/arr/pending'),
        ordersApi('/requests?view=active&kind=episode&pageSize=1').catch(() => ({ total: 0 })),
        ordersApi('/requests?view=history&page=1&pageSize=1').catch(() => ({ hiddenCount: 0 })),
      ]);
      state.hiddenCount = historyPayload.hiddenCount || 0;
      updateArchivedLink();
      publish(payload.items || [], episodePayload.total || 0);
    } catch (e) {
      state.hiddenCount = 0;
      updateArchivedLink();
      publish([]);
    }
  }

  function renderList() {
    active.renderSummary(state.items);
    const rows = active.filteredItems();
    dom.list.innerHTML = '';
    if (!rows.length) {
      const hasEpisodes = episodes.filteredEpisodes().length > 0;
      if (state.items.length) {
        dom.list.appendChild(h('div', 'hx-empty', 'Nenhum pedido corresponde ao filtro.'));
        return;
      }
      if (hasEpisodes) {
        dom.list.appendChild(h('div', 'hx-empty', 'Nenhum filme/série dublado no momento.'));
        return;
      }
      const empty = h('div', 'hx-empty', 'Nada por aqui. Adicione uma série/anime ou peça um filme no Seerr.');
      const actions = h('div', 'hx-toolbar', '');
      actions.style.justifyContent = 'center';
      actions.appendChild(btn('Adicionar série/anime', 'hx-btn-primary', () => add.show()));
      const seerr = h('a', 'hx-btn hx-btn-primary', 'Abrir Seerr');
      seerr.href = seerrLink.href;
      seerr.target = '_blank';
      seerr.rel = 'noopener';
      actions.appendChild(seerr);
      empty.appendChild(actions);
      dom.list.appendChild(empty);
      return;
    }
    for (const item of rows) dom.list.appendChild(active.renderOrder(item));
  }

  function renderCurrent() {
    if (state.view === 'history') {
      history.renderHistory();
    } else {
      renderList();
      episodes.renderEpisodeRequests();
    }
  }

  function updatedSuffix() {
    return window.matchMedia('(max-width:700px)').matches ? '' : ` • atualizado ${new Date().toLocaleTimeString()}`;
  }

  function activeStatusText() {
    const itemsPart = state.items.length
      ? `${countLabel(state.items.length, 'item', 'itens')} nos perfis dublados`
      : 'Nenhum filme/série dublado no momento';
    const episodesPart = state.episodeItems.length
      ? countLabel(state.episodeItems.length, 'episódio pedido', 'episódios pedidos')
      : 'Nenhum episódio pedido';
    return `${itemsPart} • ${episodesPart}`;
  }

  function setView(next) {
    state.view = next;
    dom.originSelect.hidden = state.view !== 'history';
    dom.originSelect.value = state.originFilter;
    updateFilterOptions();
    updateArchivedLink();
    dom.activeBtn.setAttribute('aria-selected', state.view === 'active' ? 'true' : 'false');
    dom.historyBtn.setAttribute('aria-selected', state.view === 'history' ? 'true' : 'false');
    add.setActive(state.view === 'active');
    dom.summary.hidden = state.view !== 'active';
    dom.list.hidden = state.view !== 'active';
    dom.episodeSection.hidden = state.view !== 'active' || !episodes.filteredEpisodes().length;
    dom.historySection.hidden = state.view !== 'history';
    if (state.view === 'history') {
      history.loadHistory(true);
    } else {
      renderCurrent();
      if (Date.now() - state.lastLoaded > 20000) {
        load(false);
      } else {
        setStatus(`${activeStatusText()}${updatedSuffix()}`);
      }
    }
  }

  async function load(silent) {
    if (state.loading || state.busy) return;
    state.loading = true;
    if (!silent) {
      dom.refreshBtn.disabled = true;
      dom.refreshBtn.textContent = 'Carregando...';
      setStatus('Carregando pedidos...');
    }
    try {
      const [payload, episodePayload] = await Promise.all([
        ordersApi('/arr/pending?status=1'),
        ordersApi('/requests?view=active&kind=episode&pageSize=500').catch(() => ({ items: [], total: 0 })),
      ]);
      state.items = payload.items || [];
      state.episodeItems = episodePayload.items || [];
      state.lastLoaded = Date.now();
      publish(state.items, state.episodeItems.length);
      renderList();
      episodes.renderEpisodeRequests();
      const warning = payload.seerrError ? ` • Seerr indisponível: ${payload.seerrError}` : '';
      setStatus(`${activeStatusText()}${warning}${updatedSuffix()}`, payload.seerrError ? '#f59e0b' : '#9aa0a6');
    } catch (e) {
      setStatus('Erro ao carregar: ' + e.message, '#f87171');
    } finally {
      state.loading = false;
      dom.refreshBtn.disabled = false;
      dom.refreshBtn.textContent = 'Atualizar';
    }
  }

  const helpers = ctx.helpers;
  helpers.setStatus = setStatus;
  helpers.publish = publish;
  helpers.updateCount = updateCount;
  helpers.renderCurrent = renderCurrent;
  helpers.renderList = renderList;
  helpers.load = load;
  helpers.openEpisodes = episodes.openEpisodes;
  helpers.renderEpisodeRequests = episodes.renderEpisodeRequests;
  helpers.loadHistory = history.loadHistory;

  searchInput.addEventListener('input', () => { state.query = searchInput.value; renderCurrent(); });
  filterSelect.addEventListener('change', () => { state.filter = filterSelect.value; renderCurrent(); });
  originSelect.addEventListener('change', () => { state.originFilter = originSelect.value; renderCurrent(); });

  setView('active');

  let lastActivated = 0;
  return {
    activate() {
      if (Date.now() - lastActivated < 15000) return;
      lastActivated = Date.now();
      if (state.view === 'history') {
        if (!state.historyItems.length || Date.now() - state.lastHistoryLoaded > 20000) history.loadHistory(true);
      } else if (Date.now() - state.lastLoaded > 20000) {
        load(false);
      }
    },
    refresh() {
      lastActivated = Date.now();
      return state.view === 'history' ? history.loadHistory(true) : load(false);
    },
    refreshSilent() {
      if (state.loading || state.busy || state.historyLoading) return;
      if (state.view === 'history') return;
      if (state.lastLoaded && Date.now() - state.lastLoaded > 45000) {
        load(true);
      }
    },
    updateCount,
  };
}
