import { REMOTE, SERVICE_HOST, norm, countLabel, h, btn, toast, fmtDate } from '../shared.js';
import {
  STATUS, statusOf, itemLabel, profileLabel, eventLabel,
  statusLabel, statusMessageFor, epLabel, historyLabel, ordersApi,
} from './common.js';

const EP_PAGE_SIZE = 3;

export function createActive(ctx) {
  const { state, dom, helpers } = ctx;
  const episodeUi = new Map();
  let openMenu = null;

  document.addEventListener('click', (event) => {
    if (!openMenu) return;
    if (openMenu.menu.contains(event.target) || openMenu.btn.contains(event.target)) return;
    closeMenu();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeMenu();
  });

  function closeMenu() {
    if (!openMenu) return;
    openMenu.menu.hidden = true;
    openMenu.btn.setAttribute('aria-expanded', 'false');
    openMenu = null;
  }

  function toggleMenu(trigger, menu) {
    const wasOpen = openMenu && openMenu.menu === menu && !menu.hidden;
    closeMenu();
    if (wasOpen) return;
    menu.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    openMenu = { btn: trigger, menu };
  }

  function countsFor(rows) {
    const c = { done: 0, active: 0, error: 0, missing: 0, seerr: 0 };
    for (const item of rows) {
      const s = statusOf(item);
      if (s === 'error' || s === 'request_declined' || s === 'request_failed') c.error++;
      else if (s === 'missing') c.missing++;
      else if (s === 'downloaded' || s === 'partial' || s === 'request_completed') c.done++;
      else if (s === 'request_pending' || s === 'request_approved') {
        c.active++;
        c.seerr++;
      } else c.active++;
    }
    return c;
  }

  function episodeCounts() {
    const c = { done: 0, active: 0, error: 0, missing: 0 };
    for (const item of state.episodeItems) {
      const s = statusOf(item);
      if (s === 'error' || s === 'request_declined' || s === 'request_failed') c.error++;
      else if (s === 'missing') c.missing++;
      else if (s === 'downloaded' || s === 'partial' || s === 'request_completed') c.done++;
      else c.active++;
    }
    return c;
  }

  function renderSummary(rows) {
    const c = countsFor(rows);
    const e = episodeCounts();
    const defs = [
      ['done', 'Baixados', c.done + e.done, '#4ade80'],
      ['active', 'Em andamento', c.active + e.active, '#60a5fa'],
      ['seerr', 'No Seerr', c.seerr, '#c084fc'],
      ['attention', 'Erros', c.error + e.error, '#f87171'],
      ['missing', 'Sem arquivo', c.missing + e.missing, '#a1a1aa'],
    ];
    dom.summary.innerHTML = '';
    for (const [key, label, count, color] of defs) {
      const chip = h('button', 'hx-chip', '');
      chip.type = 'button';
      chip.setAttribute('aria-pressed', state.filter === key ? 'true' : 'false');
      const dot = h('span', 'hx-dot', '');
      dot.style.background = color;
      chip.append(dot, h('span', '', label), h('b', '', String(count)));
      if (key === 'seerr') chip.title = 'Pedido aguardando aprovação no Seerr';
      chip.addEventListener('click', () => {
        state.filter = state.filter === key ? 'all' : key;
        state.statusFilter = [];
        state.page = 1;
        dom.filterSelect.value = state.filter;
        helpers.renderCurrent();
      });
      dom.summary.appendChild(chip);
    }
  }

  function episodesFor(item) {
    if (!item || item.kind !== 'series' || item.id == null) return [];
    return state.episodeItems
      .filter((ep) => String(ep.seriesId) === String(item.id))
      .sort((a, b) => (Number(a.season) - Number(b.season)) || (Number(a.episode) - Number(b.episode)));
  }

  function filtersActive() {
    return Boolean(norm(state.query))
      || state.typeFilter !== 'all'
      || state.profileFilter !== 'all'
      || (state.statusFilter && state.statusFilter.length > 0)
      || (state.filter && state.filter !== 'all');
  }

  function filteredEpisodes() {
    const q = norm(state.query);
    return state.episodeItems.filter((item) => {
      if (q && !norm(historyLabel(item)).includes(q)) return false;
      return ctx.filters ? ctx.filters.matches(item) : true;
    });
  }

  function orphanEpisodeCount() {
    const ids = new Set(
      state.items
        .filter((item) => item.kind === 'series' && item.id != null)
        .map((item) => String(item.id))
    );
    const titles = new Set(
      state.items
        .filter((item) => item.kind === 'series')
        .map((item) => norm(item.title))
    );
    let count = 0;
    for (const ep of state.episodeItems) {
      if (ids.has(String(ep.seriesId)) || titles.has(norm(ep.title))) continue;
      count++;
    }
    return count;
  }

  function filteredItems() {
    const q = norm(state.query);
    const rows = state.items.filter((item) => {
      const eps = item.kind === 'series' ? episodesFor(item) : [];
      const titleHit = !q || norm(itemLabel(item)).includes(q);
      const episodeHit = q && eps.some((ep) => norm(historyLabel(ep)).includes(q));
      if (q && !titleHit && !episodeHit) return false;
      if (ctx.filters.matches(item)) return true;
      return eps.some((ep) => ctx.filters.matches(ep));
    });
    return ctx.filters.sortItems(rows);
  }

  function progressOf(item) {
    if (item.queue && Number.isFinite(Number(item.queue.progress))) {
      return Math.max(0, Math.min(100, Math.round(Number(item.queue.progress))));
    }
    const s = statusOf(item);
    if (s === 'downloaded') return 100;
    if (s === 'partial' && item.episodeCount) {
      return Math.round(((item.episodeFileCount || 0) / item.episodeCount) * 100);
    }
    return 0;
  }

  function sonarrLink(item) {
    if (REMOTE || item.seerrOnly || !item.id) return null;
    if (item.kind !== 'movie' && item.kind !== 'series') return null;
    const label = item.kind === 'movie' ? 'Radarr' : 'Sonarr';
    const port = item.kind === 'movie' ? 7878 : 8989;
    const path = item.kind === 'movie' ? 'movie' : 'series';
    const link = h('a', 'hx-menu-item', '');
    link.href = `http://${SERVICE_HOST}:${port}/${path}/${item.id}`;
    link.target = '_blank';
    link.rel = 'noopener';
    link.setAttribute('role', 'menuitem');
    link.append(h('span', 'hx-menu-label', 'Abrir no ' + label), h('span', 'hx-menu-hint', 'Somente em LAN'));
    link.addEventListener('click', closeMenu);
    return link;
  }

  function menuItem(label, hint, onClick, cls) {
    const item = h('button', 'hx-menu-item' + (cls ? ' ' + cls : ''), '');
    item.type = 'button';
    item.setAttribute('role', 'menuitem');
    item.append(h('span', 'hx-menu-label', label));
    if (hint) item.appendChild(h('span', 'hx-menu-hint', hint));
    item.addEventListener('click', () => {
      closeMenu();
      onClick();
    });
    return item;
  }

  function archiveEpisode(item) {
    if (!item.key) return;
    if (!confirm(`Remover "${historyLabel(item)}" da lista? O histórico será mantido.`)) return;
    ordersApi('/requests/hide', 'POST', { keys: [item.key] })
      .then(() => {
        state.episodeItems = state.episodeItems.filter((row) => row.key !== item.key);
        toast('Removido da lista: ' + historyLabel(item));
        helpers.renderList();
        helpers.updateCount();
      })
      .catch((e) => toast('Erro ao remover: ' + e.message, false));
  }

  function episodeRow(item) {
    const statusKey = statusOf(item);
    const row = h('div', 'hx-episode-row', '');
    const main = h('div', 'hx-episode-main', '');
    main.appendChild(h('div', 'hx-episode-title', `${epLabel(item)} • ${item.episodeTitle || 'Episódio'}`));
    const bits = [];
    const msg = statusMessageFor(item);
    if (msg) bits.push(msg);
    if (item.requestedAt) bits.push((item.source === 'seerr' ? 'pedido em ' : 'adicionado em ') + fmtDate(item.requestedAt));
    if (item.meta && item.meta.lastEvent && item.meta.lastEvent.date) {
      bits.push('evento ' + eventLabel(item.meta.lastEvent) + ' ' + fmtDate(item.meta.lastEvent.date));
    }
    main.appendChild(h('div', 'hx-episode-sub', bits.filter(Boolean).join(' • ')));
    const side = h('div', 'hx-episode-side', '');
    side.appendChild(h('span', 'hx-status hx-status-' + statusKey, statusLabel(statusKey)));
    side.appendChild(btn('Remover', 'hx-ep-remove', () => archiveEpisode(item)));
    row.append(main, side);
    return row;
  }

  function renderEpisodePanel(eps, uiKey) {
    let ui = episodeUi.get(uiKey);
    if (!ui) {
      ui = { open: false, page: 1 };
      episodeUi.set(uiKey, ui);
    }
    const wrap = h('div', 'hx-ep-panel', '');
    const toggle = h('button', 'hx-ep-toggle', '');
    toggle.type = 'button';
    toggle.setAttribute('aria-expanded', String(ui.open));
    const label = h('span', 'hx-ep-toggle-label', `Episódios pedidos (${eps.length})`);
    const done = eps.filter((item) => statusOf(item) === 'downloaded').length;
    const errors = eps.filter((item) => ['error', 'request_declined', 'request_failed'].includes(statusOf(item))).length;
    const meta = h('span', 'hx-ep-toggle-meta', `${done} baixados${errors ? ` • ${errors} com erro` : ''}`);
    toggle.append(label, meta);
    const body = h('div', 'hx-ep-panel-body', '');
    body.hidden = !ui.open;
    wrap.append(toggle, body);

    function renderBody() {
      body.innerHTML = '';
      const pageCount = Math.max(1, Math.ceil(eps.length / EP_PAGE_SIZE));
      ui.page = Math.max(1, Math.min(ui.page, pageCount));
      const start = (ui.page - 1) * EP_PAGE_SIZE;
      for (const item of eps.slice(start, start + EP_PAGE_SIZE)) body.appendChild(episodeRow(item));
      if (pageCount > 1) {
        const pager = h('div', 'hx-ep-pager', '');
        const previous = btn('‹', 'hx-page', () => {
          ui.page = Math.max(1, ui.page - 1);
          renderBody();
        });
        previous.disabled = ui.page === 1;
        previous.setAttribute('aria-label', 'Episódios anteriores');
        const info = h('span', 'hx-page-info', `${start + 1}–${Math.min(start + EP_PAGE_SIZE, eps.length)} de ${eps.length}`);
        const next = btn('›', 'hx-page', () => {
          ui.page = Math.min(pageCount, ui.page + 1);
          renderBody();
        });
        next.disabled = ui.page === pageCount;
        next.setAttribute('aria-label', 'Próximos episódios');
        pager.append(previous, info, next);
        body.appendChild(pager);
      }
    }

    toggle.addEventListener('click', () => {
      ui.open = !ui.open;
      toggle.setAttribute('aria-expanded', String(ui.open));
      body.hidden = !ui.open;
      if (ui.open) renderBody();
    });
    if (ui.open) renderBody();
    return wrap;
  }

  function renderOrder(item) {
    const statusKey = statusOf(item);
    const meta = STATUS[statusKey] || STATUS.missing;
    const box = h('article', 'hx-order', '');
    box.dataset.status = statusKey;

    const top = h('div', 'hx-order-top', '');
    const titleWrap = h('div', 'hx-order-title', '');
    const kind = h('span', 'hx-kind', item.kind === 'movie' ? 'Filme' : 'Série');
    titleWrap.append(kind, document.createTextNode(itemLabel(item)));

    const side = h('div', 'hx-order-side', '');
    const badge = h('span', 'hx-status hx-status-' + statusKey, meta.label);
    side.appendChild(badge);

    const menu = h('div', 'hx-menu', '');
    menu.hidden = true;
    menu.setAttribute('role', 'menu');
    const kebab = btn('⋯', 'hx-kebab', () => toggleMenu(kebab, menu));
    kebab.setAttribute('aria-label', 'Mais ações');
    kebab.setAttribute('aria-haspopup', 'menu');
    kebab.setAttribute('aria-expanded', 'false');
    side.appendChild(kebab);
    side.appendChild(menu);
    top.append(titleWrap, side);
    box.appendChild(top);

    const ext = sonarrLink(item);
    if (ext) {
      menu.appendChild(ext);
      menu.appendChild(h('div', 'hx-menu-sep', ''));
    }
    if (item.key) {
      menu.appendChild(menuItem('Remover da lista', 'O histórico é mantido', () => archiveItem(item), 'hx-menu-item-danger'));
    }
    if (!menu.childNodes.length) {
      kebab.hidden = true;
      menu.remove();
    }

    const parts = [];
    if (item.kind === 'series' && item.episodeCount) {
      const files = item.episodeFileCount || 0;
      parts.push(`${files}/${countLabel(item.episodeCount, 'episódio', 'episódios')}`);
      if (item.seasonCount) parts.push(countLabel(item.seasonCount, 'temporada', 'temporadas'));
    }
    if (item.queue && item.queue.count) parts.push(`${item.queue.count} na fila`);
    if (item.queue && item.queue.timeleft) parts.push(item.queue.timeleft);
    if (item.searching) parts.push('busca ativa');
    if (parts.length) box.appendChild(h('div', 'hx-order-meta', parts.join(' • ')));
    if (!item.seerrOnly) {
      const profile = item.profileName
        ? profileLabel(item.profileName)
        : (item.profileId != null ? 'Perfil ' + item.profileId : '');
      if (profile) box.appendChild(h('div', 'hx-order-meta', 'perfil ' + profile));
    }

    const seerrInfo = item.seerr;
    if (seerrInfo && (item.seerrOnly || seerrInfo.status !== 5)) {
      const bits = [seerrInfo.statusLabel || ''];
      if (seerrInfo.profileName) bits.push('perfil ' + profileLabel(seerrInfo.profileName));
      if (seerrInfo.requestedBy) bits.push('por ' + seerrInfo.requestedBy);
      if (seerrInfo.updatedAt) bits.push('atualizado ' + fmtDate(seerrInfo.updatedAt));
      box.appendChild(h('div', 'hx-order-event', 'Seerr: ' + bits.filter(Boolean).join(' • ')));
    }

    const pct = progressOf(item);
    if (pct > 0 || statusKey === 'downloading') {
      const bar = h('div', 'hx-bar', '');
      bar.setAttribute('role', 'progressbar');
      bar.setAttribute('aria-label', 'Progresso do download');
      bar.setAttribute('aria-valuemin', '0');
      bar.setAttribute('aria-valuemax', '100');
      bar.setAttribute('aria-valuenow', String(pct));
      const fill = h('span', '', '');
      fill.style.width = pct + '%';
      if (statusKey === 'error') fill.style.background = '#f87171';
      else if (statusKey === 'downloading') fill.style.background = '#60a5fa';
      else if (statusKey === 'queued' || statusKey === 'searching') fill.style.background = '#fbbf24';
      else if (statusKey === 'partial') fill.style.background = '#2dd4bf';
      else fill.style.background = '#4ade80';
      bar.appendChild(fill);
      box.appendChild(bar);
    }

    const staleFailure = statusKey !== 'downloaded' && statusKey !== 'partial';
    const err = item.errorMessage
      || (item.queue && item.queue.error)
      || (staleFailure && item.lastEvent && item.lastEvent.failed ? (item.lastEvent.message || '') : '');
    if (err) box.appendChild(h('div', 'hx-error', err));

    if (item.lastEvent && item.lastEvent.eventType) {
      const when = item.lastEvent.date ? ' • ' + fmtDate(item.lastEvent.date) : '';
      const source = item.lastEvent.sourceTitle ? ' — ' + item.lastEvent.sourceTitle : '';
      box.appendChild(h('div', 'hx-order-event', 'Último evento: ' + eventLabel(item.lastEvent) + when + source));
    }

    if (item.seerrOnly) {
      const hints = {
        request_pending: 'Aguardando aprovação no Seerr.',
        request_approved: 'Aprovado no Seerr; ainda não encontrado no Radarr/Sonarr.',
        request_declined: 'Pedido recusado no Seerr; não foi enviado ao Radarr/Sonarr.',
        request_failed: 'Falha ao enviar ao Radarr/Sonarr; veja o detalhe acima.',
      };
      box.appendChild(h('div', 'hx-muted', hints[statusKey] || 'Pedido ainda não chegou ao Radarr/Sonarr.'));
    } else if (statusKey === 'missing') {
      box.appendChild(h('div', 'hx-muted', 'Sem arquivo: o Radarr/Sonarr ainda não encontrou uma release aceita.'));
    }

    if (item.kind === 'series') {
      const allEps = episodesFor(item);
      const q = norm(state.query);
      const eps = filtersActive()
        ? allEps.filter((ep) => (!q || norm(historyLabel(ep)).includes(q)) && ctx.filters.matches(ep))
        : allEps;
      if (eps.length) {
        box.appendChild(renderEpisodePanel(eps, 'series:' + (item.id != null ? item.id : item.key || item.title)));
      }
    }
    return box;
  }

  function archiveItem(item) {
    if (!item.key) return;
    if (!confirm(`Remover "${itemLabel(item)}" da lista? O histórico será mantido.`)) return;
    ordersApi('/requests/hide', 'POST', { keys: [item.key] })
      .then(() => {
        state.items = state.items.filter((row) => row.key !== item.key);
        toast('Removido da lista: ' + (item.title || item.key));
        helpers.renderList();
        helpers.updateCount();
      })
      .catch((e) => toast('Erro ao remover: ' + e.message, false));
  }

  return {
    countsFor, episodeCounts, renderSummary, filteredItems, filteredEpisodes,
    orphanEpisodeCount, progressOf, renderOrder, archiveItem,
  };
}
