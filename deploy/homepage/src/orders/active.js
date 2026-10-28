import { REMOTE, SERVICE_HOST, norm, countLabel, h, btn, toast, fmtDate } from '../shared.js';
import { STATUS, statusOf, itemLabel, profileLabel, eventLabel, ordersApi } from './common.js';

export function createActive(ctx) {
  const { state, dom, helpers } = ctx;

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

  function filteredItems() {
    const q = norm(state.query);
    const rows = state.items.filter((item) => {
      if (q && !norm(itemLabel(item)).includes(q)) return false;
      return ctx.filters.matches(item);
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

  function externalLink(item) {
    if (REMOTE || item.seerrOnly || !item.id) return null;
    if (item.kind !== 'movie' && item.kind !== 'series') return null;
    const label = item.kind === 'movie' ? 'Radarr' : 'Sonarr';
    const port = item.kind === 'movie' ? 7878 : 8989;
    const path = item.kind === 'movie' ? 'movie' : 'series';
    const link = h('a', 'hx-ext-link', label + ' ↗');
    link.href = `http://${SERVICE_HOST}:${port}/${path}/${item.id}`;
    link.target = '_blank';
    link.rel = 'noopener';
    link.title = `Abrir no ${label} (LAN)`;
    return link;
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
    const badge = h('span', 'hx-status hx-status-' + statusKey, meta.label);
    top.append(titleWrap, badge);
    box.appendChild(top);

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
    if (item.kind === 'series') {
      const eps = state.episodeItems.filter((ep) => ep.seriesId === item.id);
      if (eps.length) {
        const done = eps.filter((ep) => statusOf(ep) === 'downloaded').length;
        box.appendChild(h('div', 'hx-order-event', `${countLabel(eps.length, 'episódio pedido', 'episódios pedidos')}: ${countLabel(done, 'baixado', 'baixados')}`));
      }
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
      box.appendChild(h('div', 'hx-muted', 'Sem arquivo: use "Verificar PT-BR" para ver se há releases aceitas.'));
    }

    const removeBtn = item.key ? btn('Remover', '', () => archiveItem(item)) : null;
    if (!item.seerrOnly) {
      const actions = h('div', 'hx-order-actions', '');
      const dynamic = h('div', 'hx-order-actions', '');
      dynamic.style.marginTop = '0';
      const result = h('div', 'hx-order-result', '');
      const check = btn('Verificar PT-BR', '', null);
      check.title = 'Consulta os indexadores para ver se há releases aceitas em PT-BR';
      check.setAttribute('aria-label', 'Verificar se há releases em PT-BR nos indexadores');

      check.addEventListener('click', async () => {
        if (state.busy) return;
        state.busy = true;
        check.disabled = true;
        check.textContent = 'Verificando...';
        dynamic.innerHTML = '';
        result.textContent = 'Consultando indexadores...';
        result.style.color = '#9aa0a6';
        try {
          const data = await ordersApi('/arr/check', 'POST', { kind: item.kind, id: item.id });
          if (data.accepted > 0) {
            result.textContent = `${countLabel(data.accepted, 'release PT-BR aceito', 'releases PT-BR aceitos')} (de ${data.total}).`;
            result.style.color = '#4ade80';
            const search = btn('Buscar PT-BR', 'hx-btn-primary', async () => {
              if (state.busy) return;
              state.busy = true;
              search.disabled = true;
              try {
                await ordersApi('/arr/search', 'POST', { kind: item.kind, id: item.id });
                toast('Busca PT-BR iniciada: ' + item.title);
                result.textContent = 'Busca PT-BR iniciada.';
                result.style.color = '#4ade80';
                setTimeout(() => { state.busy = false; helpers.load(true); }, 8000);
              } catch (e) {
                state.busy = false;
                toast('Erro na busca: ' + e.message, false);
                result.textContent = 'Erro: ' + e.message;
                result.style.color = '#f87171';
                search.disabled = false;
              }
            });
            dynamic.appendChild(search);
          } else {
            result.textContent = `Nenhum PT-BR aceito (${countLabel(data.total, 'release analisado', 'releases analisados')}).`;
            result.style.color = '#f59e0b';
              const original = btn('Buscar original', 'hx-btn-ok', async () => {
                if (state.busy) return;
                if (!confirm('Mudar o item para o perfil Original e iniciar a busca? Ele sairá dos perfis dublados.')) return;
                state.busy = true;
              original.disabled = true;
              original.textContent = 'Trocando...';
              try {
                await ordersApi('/arr/switch', 'POST', { kind: item.kind, id: item.id });
                toast('Perfil Original + busca iniciada: ' + item.title);
                result.textContent = 'Perfil trocado para Original e busca iniciada.';
                result.style.color = '#4ade80';
                original.textContent = 'Original';
                helpers.updateCount();
                setTimeout(() => { state.busy = false; helpers.load(true); }, 8000);
              } catch (e) {
                state.busy = false;
                toast('Erro ao trocar perfil: ' + e.message, false);
                result.textContent = 'Erro: ' + e.message;
                result.style.color = '#f87171';
                original.disabled = false;
                original.textContent = 'Buscar original';
              }
            });
            original.title = 'Muda o item para o perfil Original e inicia a busca; ele sai dos perfis dublados';
            dynamic.appendChild(original);
          }
        } catch (e) {
          result.textContent = 'Erro: ' + e.message;
          result.style.color = '#f87171';
        }
        state.busy = false;
        check.disabled = false;
        check.textContent = 'Verificar PT-BR';
      });

      actions.appendChild(check);
      if (removeBtn) actions.appendChild(removeBtn);
      const ext = externalLink(item);
      if (ext) actions.appendChild(ext);
      box.append(actions, dynamic, result);
    }
    if (removeBtn && item.seerrOnly) {
      const footer = h('div', 'hx-order-actions', '');
      footer.appendChild(removeBtn);
      box.appendChild(footer);
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

  return { countsFor, episodeCounts, renderSummary, filteredItems, progressOf, renderOrder, archiveItem };
}
