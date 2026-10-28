import { norm, countLabel, h, btn, toast, fmtDate } from '../shared.js';
import { statusOf, epLabel, statusLabel, statusMessageFor, eventLabel, historyLabel, profileLabel, seriesTypeLabel, ordersApi } from './common.js';

export function createEpisodes(ctx) {
  const { state, dom, helpers } = ctx;
  let epShell = null;

  function filteredEpisodes() {
    const q = norm(state.query);
    return state.episodeItems.filter((item) => {
      if (q && !norm(historyLabel(item)).includes(q)) return false;
      if (ctx.filters && !ctx.filters.matches(item)) return false;
      return true;
    });
  }

  function archiveEpisode(item) {
    if (!item.key) return;
    if (!confirm(`Remover "${historyLabel(item)}" da lista? O histórico será mantido.`)) return;
    ordersApi('/requests/hide', 'POST', { keys: [item.key] })
      .then(() => {
        state.episodeItems = state.episodeItems.filter((row) => row.key !== item.key);
        toast('Removido da lista: ' + historyLabel(item));
        renderEpisodeRequests();
        helpers.renderList();
        helpers.updateCount();
      })
      .catch((e) => toast('Erro ao remover: ' + e.message, false));
  }

  function renderEpisodeRequests() {
    const rows = filteredEpisodes();
    dom.episodeList.innerHTML = '';
    dom.episodeTitle.textContent = `Episódios pedidos (${rows.length})`;
    dom.episodeSection.hidden = !rows.length || state.view !== 'active';
    if (!rows.length) return;
    const groups = new Map();
    for (const item of rows) {
      const key = item.seriesId || item.title || item.key;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(item);
    }
    for (const eps of [...groups.values()].sort((a, b) => {
      const da = Math.max(...a.map((x) => new Date(x.requestedAt || 0).getTime()));
      const db = Math.max(...b.map((x) => new Date(x.requestedAt || 0).getTime()));
      return db - da;
    })) {
      eps.sort((a, b) => (a.season - b.season) || (a.episode - b.episode));
      const title = eps[0].title || 'Série';
      const done = eps.filter((item) => statusOf(item) === 'downloaded').length;
      const box = h('article', 'hx-order', '');
      const top = h('div', 'hx-order-top', '');
      const titleWrap = h('div', 'hx-order-title', '');
      titleWrap.append(h('span', 'hx-kind', 'Série'), document.createTextNode(title));
      const badge = h('span', 'hx-status hx-status-partial', `${done}/${eps.length} baixados`);
      top.append(titleWrap, badge);
      box.appendChild(top);
      const profile = eps.find((item) => item.profileName)?.profileName;
      if (profile) box.appendChild(h('div', 'hx-order-meta', 'perfil ' + profileLabel(profile)));
      const body = h('div', 'hx-episode-rows', '');
      for (const item of eps) {
        const statusKey = statusOf(item);
        const row = h('div', 'hx-episode-row', '');
        const main = h('div', 'hx-episode-main', '');
        main.appendChild(h('div', 'hx-episode-title', `${epLabel(item)} • ${item.episodeTitle || 'Episódio'}`));
        const bits = [statusLabel(statusKey)];
        const msg = statusMessageFor(item);
        if (msg) bits.push(msg);
        if (item.requestedAt) bits.push((item.source === 'seerr' ? 'pedido em ' : 'adicionado em ') + fmtDate(item.requestedAt));
        if (item.meta && item.meta.lastEvent && item.meta.lastEvent.date) {
          bits.push('evento ' + eventLabel(item.meta.lastEvent) + ' ' + fmtDate(item.meta.lastEvent.date));
        }
        main.appendChild(h('div', 'hx-episode-sub', bits.filter(Boolean).join(' • ')));
        const side = h('div', 'hx-episode-side', '');
        side.appendChild(h('span', 'hx-status hx-status-' + statusKey, statusLabel(statusKey)));
        const remove = btn('Remover', 'hx-ep-remove', () => archiveEpisode(item));
        side.appendChild(remove);
        row.append(main, side);
        body.appendChild(row);
      }
      box.appendChild(body);
      dom.episodeList.appendChild(box);
    }
  }

  let previousFocus = null;

  function closeEpisodes() {
    if (!epShell) return;
    if (epShell._keydown) document.removeEventListener('keydown', epShell._keydown);
    epShell.remove();
    epShell = null;
    if (previousFocus && previousFocus.isConnected && typeof previousFocus.focus === 'function') {
      previousFocus.focus();
    }
    previousFocus = null;
  }

  function openEpisodes(seriesId, justAdded) {
    closeEpisodes();
    previousFocus = document.activeElement;
    const shell = h('div', 'hx-shell', '');
    epShell = shell;
    shell.setAttribute('role', 'dialog');
    shell.setAttribute('aria-modal', 'true');
    shell.setAttribute('aria-labelledby', 'hx-ep-title');
    shell.setAttribute('aria-describedby', 'hx-ep-sub');
    shell.tabIndex = -1;
    const head = h('div', 'hx-head', '');
    const headWrap = h('div', '', '');
    const title = h('h2', 'hx-head-title', 'Episódios');
    title.id = 'hx-ep-title';
    const sub = h('span', 'hx-head-sub', 'Carregando...');
    sub.id = 'hx-ep-sub';
    headWrap.append(title, sub);
    const closeBtn = btn('Fechar', '', () => closeEpisodes());
    head.append(headWrap, closeBtn);
    const body = h('div', 'hx-body', '');
    shell.append(head, body);
    shell._keydown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeEpisodes();
        return;
      }
      if (event.key !== 'Tab') return;
      const focusable = [...shell.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
        .filter((el) => !el.disabled && el.getClientRects().length > 0);
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
    document.body.appendChild(shell);
    closeBtn.focus();
    loadEpisodes(seriesId, justAdded, title, sub, body);
  }

  async function loadEpisodes(seriesId, justAdded, titleEl, subEl, body, attempt = 0) {
    body.innerHTML = '';
    body.appendChild(h('div', 'hx-muted', 'Carregando episódios...'));
    try {
      const [data, requests] = await Promise.all([
        ordersApi('/sonarr/episodes?seriesId=' + seriesId),
        ordersApi('/requests?view=history&kind=episode&seriesId=' + seriesId + '&pageSize=500').catch(() => ({ items: [] })),
      ]);
      const episodes = data.episodes || [];
      const trackedItems = (requests.items && requests.items.length)
        ? requests.items
        : state.episodeItems.filter((item) => String(item.seriesId) === String(seriesId));
      const tracked = new Set(trackedItems.map((item) => Number(item.episodeId ?? item.arrId)).filter(Boolean));
      if (data.refreshing && !episodes.length && attempt < 20) {
        titleEl.textContent = (data.series && data.series.title) || 'Episódios';
        subEl.textContent = 'Sonarr está buscando os episódios...';
        body.innerHTML = '';
        body.appendChild(h('div', 'hx-muted', 'Aguarde, o Sonarr está importando os dados da série...'));
        setTimeout(() => {
          if (epShell && epShell.contains(body)) {
            loadEpisodes(seriesId, justAdded, titleEl, subEl, body, attempt + 1);
          }
        }, 3000);
        return;
      }
      renderEpisodes(data, justAdded, titleEl, subEl, body, tracked);
    } catch (e) {
      body.innerHTML = '';
      body.appendChild(h('div', 'hx-error', 'Erro: ' + e.message));
    }
  }

  function renderEpisodes(data, justAdded, titleEl, subEl, body, tracked) {
    const series = data.series || {};
    const episodes = data.episodes || [];
    titleEl.textContent = series.title || 'Episódios';
    const profile = profileLabel(series.profileName) || ('perfil ' + series.profileId);
    const parts = [profile, seriesTypeLabel(series.seriesType)];
    if (series.rootFolderPath) parts.push(series.rootFolderPath);
    parts.push(episodes.filter((ep) => ep.hasFile).length + '/' + episodes.length + ' baixados');
    subEl.textContent = parts.join(' • ');
    body.innerHTML = '';

    if (series.profileId !== 9) {
      body.appendChild(h('div', 'hx-warn', 'Perfil atual: ' + profile + ' (não será alterado). Para dublado, adicione usando o perfil Séries - Dublado.'));
    }
    if (!episodes.length) {
      body.appendChild(h('div', 'hx-muted', 'Nenhum episódio encontrado no Sonarr.'));
      return;
    }

    const seasons = new Map();
    for (const ep of episodes) {
      if (!seasons.has(ep.seasonNumber)) seasons.set(ep.seasonNumber, []);
      seasons.get(ep.seasonNumber).push(ep);
    }
    const seasonList = [...seasons.keys()].sort((a, b) => a - b);
    const seasonName = (season) => season ? 'Temporada ' + season : 'Especiais';

    const controls = h('div', 'hx-toolbar', '');
    const seasonNav = h('select', 'hx-select');
    seasonNav.setAttribute('aria-label', 'Ir para temporada');
    const navAll = h('option', '', 'Ir para temporada');
    navAll.value = '';
    seasonNav.appendChild(navAll);
    for (const season of seasonList) {
      const opt = h('option', '', seasonName(season));
      opt.value = String(season);
      seasonNav.appendChild(opt);
    }

    const searchInput = h('input', 'hx-input');
    searchInput.type = 'search';
    searchInput.placeholder = 'Buscar episódio (número ou título)...';
    searchInput.setAttribute('aria-label', 'Buscar episódio por número ou título');

    const filterSel = h('select', 'hx-select');
    filterSel.setAttribute('aria-label', 'Filtrar episódios');
    for (const [value, label] of [['all', 'Todos os episódios'], ['monitored', 'Somente monitorados'], ['missing', 'Somente sem arquivo']]) {
      const opt = h('option', '', label);
      opt.value = value;
      filterSel.appendChild(opt);
    }

    const scopeSel = h('select', 'hx-select');
    scopeSel.setAttribute('aria-label', 'Escopo do marcar não baixados');
    scopeSel.title = "Escopo usado por 'Marcar não baixados'";
    const scopeAll = h('option', '', 'Escopo: todas as temporadas');
    scopeAll.value = '';
    scopeSel.appendChild(scopeAll);
    for (const season of seasonList) {
      const opt = h('option', '', 'Escopo: ' + seasonName(season));
      opt.value = String(season);
      scopeSel.appendChild(opt);
    }

    const mark = btn('Marcar não baixados', '', () => {
      const scope = scopeSel.value;
      const targets = episodes.filter((ep) => !ep.hasFile && (scope === '' || String(ep.seasonNumber) === scope));
      if (!targets.length) {
        toast('Nenhum episódio sem arquivo nesse escopo', false);
        return;
      }
      const scopeLabel = scope === '' ? 'todas as temporadas' : seasonName(Number(scope));
      if (!confirm(`Selecionar ${countLabel(targets.length, 'episódio sem arquivo', 'episódios sem arquivo')} em ${scopeLabel}?`)) return;
      const ids = new Set(targets.map((ep) => Number(ep.id)));
      body.querySelectorAll('input[data-ep]').forEach((cb) => {
        cb.checked = ids.has(Number(cb.dataset.ep));
        cb.dispatchEvent(new Event('change', { bubbles: true }));
      });
    });
    mark.title = 'Seleciona os episódios sem arquivo no escopo escolhido, com confirmação';

    const clear = btn('Limpar', '', () => {
      body.querySelectorAll('input[data-ep]').forEach((cb) => {
        cb.checked = false;
        cb.dispatchEvent(new Event('change', { bubbles: true }));
      });
    });

    controls.append(seasonNav, searchInput, filterSel, scopeSel, mark, clear);
    body.appendChild(controls);

    const sections = new Map();
    for (const season of seasonList) {
      const eps = seasons.get(season);
      const section = h('details', 'hx-season', '');
      section.dataset.season = String(season);
      const head = h('summary', 'hx-season-head', '');
      const seasonCheck = document.createElement('input');
      seasonCheck.type = 'checkbox';
      seasonCheck.className = 'hx-season-check';
      seasonCheck.addEventListener('click', (event) => event.stopPropagation());
      const seasonLabel = h('span', '', `${seasonName(season)} • ${eps.filter((ep) => ep.hasFile).length}/${eps.length} baixados`);
      head.append(seasonCheck, seasonLabel);
      section.appendChild(head);

      const epList = h('div', '', '');
      for (const ep of eps) {
        const row = h('label', 'hx-ep-row', '');
        const check = document.createElement('input');
        check.type = 'checkbox';
        check.dataset.ep = String(ep.id);
        check.checked = !!ep.monitored;
        let label;
        if (series.seriesType === 'anime' && ep.absoluteEpisodeNumber) {
          label = '#' + ep.absoluteEpisodeNumber;
        } else {
          label = 'S' + String(ep.seasonNumber).padStart(2, '0') + 'E' + String(ep.episodeNumber).padStart(2, '0');
        }
        row.dataset.search = norm(`${label} ${ep.title || ''} ${ep.absoluteEpisodeNumber || ''} ${ep.episodeNumber || ''}`);
        row.dataset.monitored = ep.monitored ? '1' : '0';
        row.dataset.hasfile = ep.hasFile ? '1' : '0';
        row.append(check, h('span', 'hx-ep-num', label), h('span', 'hx-ep-name', ep.title || ''));
        if (ep.hasFile) row.appendChild(h('span', 'hx-ep-tag', 'Baixado'));
        if (tracked.has(Number(ep.id))) row.appendChild(h('span', 'hx-ep-tag hx-ep-tag-request', 'Pedido'));
        epList.appendChild(row);
      }
      const syncSeason = () => {
        const boxes = [...epList.querySelectorAll('input[data-ep]')];
        seasonCheck.checked = boxes.length > 0 && boxes.every((cb) => cb.checked);
        seasonCheck.indeterminate = boxes.some((cb) => cb.checked) && !seasonCheck.checked;
      };
      seasonCheck.addEventListener('change', () => {
        epList.querySelectorAll('input[data-ep]').forEach((cb) => { cb.checked = seasonCheck.checked; });
        seasonCheck.indeterminate = false;
      });
      epList.addEventListener('change', syncSeason);
      syncSeason();
      section.appendChild(epList);
      sections.set(String(season), section);
      body.appendChild(section);
    }

    function applyEpisodeFilters() {
      const q = norm(searchInput.value);
      const mode = filterSel.value;
      for (const section of sections.values()) {
        let visible = 0;
        section.querySelectorAll('.hx-ep-row').forEach((row) => {
          const matchQuery = !q || row.dataset.search.includes(q);
          const matchMode = mode === 'monitored' ? row.dataset.monitored === '1'
            : mode === 'missing' ? row.dataset.hasfile !== '1'
            : true;
          const show = matchQuery && matchMode;
          row.hidden = !show;
          if (show) visible++;
        });
        section.hidden = visible === 0;
        if (visible > 0 && (q || mode !== 'all')) section.open = true;
      }
    }
    searchInput.addEventListener('input', applyEpisodeFilters);
    filterSel.addEventListener('change', applyEpisodeFilters);
    seasonNav.addEventListener('change', () => {
      const season = seasonNav.value;
      if (!season) return;
      searchInput.value = '';
      filterSel.value = 'all';
      applyEpisodeFilters();
      const section = sections.get(season);
      if (section) {
        section.open = true;
        section.scrollIntoView({ block: 'start', behavior: 'smooth' });
      }
    });

    const foot = h('div', 'hx-ep-foot', '');
    const onlyBox = document.createElement('input');
    onlyBox.type = 'checkbox';
    onlyBox.checked = !!justAdded;
    const onlyLabel = h('label', 'hx-check', '');
    onlyLabel.append(onlyBox, h('span', '', 'Desmarcar os demais episódios'));
    const searchAfter = document.createElement('input');
    searchAfter.type = 'checkbox';
    searchAfter.checked = true;
    const searchLabel = h('label', 'hx-check', '');
    searchLabel.append(searchAfter, h('span', '', 'Buscar agora'));
    const apply = btn('Aplicar aos selecionados', 'hx-btn-primary', async () => {
      const ids = [...body.querySelectorAll('input[data-ep]')]
        .filter((cb) => cb.checked)
        .map((cb) => Number(cb.dataset.ep));
      if (!ids.length) {
        toast('Selecione ao menos um episódio', false);
        return;
      }
      if (ids.length > 20) {
        const extra = onlyBox.checked ? ' Os demais serão desmarcados.' : '';
        if (!confirm(`Monitorar${searchAfter.checked ? ' e buscar' : ''} ${countLabel(ids.length, 'episódio', 'episódios')}?${extra}`)) return;
      }
      apply.disabled = true;
      try {
        const result = await ordersApi('/sonarr/episodes/monitor', 'POST', {
          seriesId: series.id,
          episodeIds: ids,
          monitored: true,
          unmonitorOthers: onlyBox.checked,
          search: searchAfter.checked,
        });
        toast(countLabel(Number(result.monitored) || 0, 'episódio monitorado', 'episódios monitorados')
          + (result.unmonitored ? ', ' + countLabel(Number(result.unmonitored) || 0, 'desmarcado', 'desmarcados') : '')
          + (searchAfter.checked ? '; busca iniciada' : ''));
        closeEpisodes();
        if (series.profileId === 9) helpers.load(true);
      } catch (e) {
        toast('Erro: ' + e.message, false);
      } finally {
        apply.disabled = false;
      }
    });
    foot.append(onlyLabel, searchLabel, apply);
    body.appendChild(foot);
  }

  return { filteredEpisodes, archiveEpisode, renderEpisodeRequests, openEpisodes, closeEpisodes };
}
