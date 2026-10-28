import { MEDIA, sleep, api, data, sleepSafe, norm, countLabel, langLabel, h, btn, toast, fmtDate, setTabCount, helpBox } from './shared.js';

const QKEY = 'subs_queue_v1';
const SAFE_CAP = 5;

export function initSubs(root) {
  let subsRows = [];
  let seriesRows = [];
  let seriesTs = 0;
  let filter = '';
  let seriesId = '';
  let loading = false;
  let syncing = false;
  let reloading = false;

  const quotaEl = h('div', 'hx-quota', '');
  const quotaLine = h('div', 'hx-quota-line', 'OpenSubtitles: verificando quota...');
  const quotaBar = h('div', 'hx-bar', '');
  const quotaFill = h('span', '', '');
  quotaBar.appendChild(quotaFill);
  quotaEl.append(quotaLine, quotaBar);

  const status = h('div', 'hx-muted', '');
  const diag = h('div', 'hx-warn', '');
  const queueEl = h('div', '', '');

  const searchInput = h('input', 'hx-input hx-search');
  searchInput.type = 'search';
  searchInput.placeholder = 'Filtrar por série ou episódio...';
  searchInput.setAttribute('aria-label', 'Filtrar legendas por série ou episódio');

  const seriesSelect = h('select', 'hx-select');
  seriesSelect.setAttribute('aria-label', 'Filtrar por série');
  const allOption = h('option', '', 'Todas as séries');
  allOption.value = '';
  seriesSelect.appendChild(allOption);

  const bAll = btn('Buscar todas pendentes', 'hx-btn-primary', async () => {
    const wanted = await getWanted();
    await runBatch(wanted, 'todas pendentes');
  });
  bAll.title = 'Busca legendas para todos os episódios pendentes, respeitando o limite diário';
  const bSync = btn('Sincronizar existentes', '', async () => {
    if (syncing) return;
    syncing = true;
    updateBusy();
    status.textContent = 'Sincronizando legendas existentes...';
    status.style.color = '#9aa0a6';
    try {
      await syncAll();
    } catch (e) {
      status.textContent = 'Erro: ' + e.message;
      status.style.color = '#f87171';
      toast('Erro: ' + e.message, false);
    } finally {
      syncing = false;
      updateBusy();
    }
  });
  bSync.title = 'Reprocessa as legendas já existentes no Bazarr; pode levar alguns minutos';
  const bReload = btn('Atualizar', 'hx-refresh', async () => {
    if (reloading) return;
    reloading = true;
    updateBusy();
    try { await refreshAll(); } finally { reloading = false; updateBusy(); }
  });
  bReload.title = 'Recarrega quota, fila e lista de pendências';

  const toolbar = h('div', 'hx-toolbar', '');
  toolbar.append(searchInput, seriesSelect, bAll, bSync, bReload);

  const list = h('div', '', '');

  const help = helpBox([
    'Esta aba lista os episódios sem legenda detectados pelo Bazarr.',
    'A quota é o limite diário do OpenSubtitles; a renovação é diária e o horário exato não é informado.',
    'A fila é salva neste navegador e não acompanha outro dispositivo.',
    '“Sincronizar existentes” reprocessa as legendas que já estão no Bazarr e pode levar alguns minutos.',
    'Pedidos (vídeo) e Legendas são fluxos separados.',
  ]);

  root.append(help, quotaEl, status, diag, queueEl, toolbar, list);

  function updateBusy() {
    const on = loading || syncing || reloading;
    bAll.disabled = on;
    bSync.disabled = on;
    bReload.disabled = on;
    bAll.textContent = loading ? 'Buscando...' : 'Buscar todas pendentes';
    bSync.textContent = syncing ? 'Sincronizando...' : 'Sincronizar existentes';
    bReload.textContent = reloading ? 'Atualizando...' : 'Atualizar';
    list.querySelectorAll('button').forEach((b) => { b.disabled = on; });
    queueEl.querySelectorAll('button').forEach((b) => { b.disabled = on; });
  }

  const episodeLabel = (e) => {
    const m = String(e.episode_number || '').match(/(\d+)\s*x\s*(\d+)/i);
    if (m) return `${e.seriesTitle || 'Item'} S${m[1].padStart(2, '0')}E${m[2].padStart(2, '0')}`;
    return `${e.seriesTitle || 'Item'} S${String(e.season || 0).padStart(2, '0')}E${String(e.episode || 0).padStart(2, '0')}`;
  };
  const getWanted = async () => data(await api('/api/episodes/wanted'));
  const getJobs = async () => data(await sleepSafe(() => api('/api/system/jobs'), []));

  async function getQuota() {
    try {
      const res = await fetch(MEDIA + '/subs/quota', { cache: 'no-store' });
      const d = await res.json();
      return d && d.ok ? d.data : null;
    } catch (e) {
      return null;
    }
  }

  function renderQuota(q) {
    if (!q) {
      quotaLine.textContent = `OpenSubtitles: quota indisponível (limite de segurança: ${SAFE_CAP}/dia)`;
      quotaLine.style.color = '#f59e0b';
      quotaFill.style.width = '0%';
      return;
    }
    const left = Number(q.remaining_downloads) || 0;
    const allowed = Number(q.allowed_downloads) || 0;
    quotaLine.textContent = `OpenSubtitles: ${left}/${allowed} restantes • renovação diária`;
    quotaLine.style.color = left > 0 ? '#c9ccd1' : '#f87171';
    quotaFill.style.width = allowed > 0 ? `${Math.max(0, Math.min(100, (left / allowed) * 100))}%` : '0%';
    quotaFill.style.background = left > 0 ? '#4ade80' : '#f87171';
  }

  async function refreshQuota() {
    const q = await getQuota();
    renderQuota(q);
    return q;
  }

  function parseReset(q) {
    if (q && q.reset_time_utc) {
      const t = Date.parse(q.reset_time_utc);
      if (!Number.isNaN(t)) return t;
    }
    return Date.now() + 24 * 3600 * 1000;
  }

  function loadQueue() {
    try { return JSON.parse(localStorage.getItem(QKEY) || '[]'); } catch (e) { return []; }
  }
  function saveQueue(q) { localStorage.setItem(QKEY, JSON.stringify(q)); }
  function queueAdd(ep, dueAt) {
    const q = loadQueue();
    if (!q.some((x) => x.sonarrEpisodeId === ep.sonarrEpisodeId)) {
      const miss = (ep.missing_subtitles || [])[0] || {};
      const m = String(ep.episode_number || '').match(/(\d+)\s*x\s*(\d+)/i);
      q.push({
        sonarrEpisodeId: ep.sonarrEpisodeId,
        sonarrSeriesId: ep.sonarrSeriesId,
        title: ep.seriesTitle || ep.title || '',
        season: m ? Number(m[1]) : (ep.season || 0),
        episode: m ? Number(m[2]) : (ep.episode || 0),
        language: miss.code2 || ep.language || 'pb',
        dueAt,
      });
    }
    saveQueue(q);
  }
  function queueRemove(ids) {
    saveQueue(loadQueue().filter((x) => !ids.includes(x.sonarrEpisodeId)));
  }
  function queueDue() {
    const now = Date.now();
    return loadQueue().filter((x) => (x.dueAt || 0) <= now);
  }

  function renderQueue() {
    const q = loadQueue();
    queueEl.innerHTML = '';
    if (!q.length) {
      queueEl.appendChild(h('div', 'hx-muted', 'Fila vazia • a fila é salva neste navegador'));
      return;
    }
    const now = Date.now();
    const due = q.filter((x) => (x.dueAt || 0) <= now);
    const label = due.length
      ? `Fila: ${countLabel(q.length, 'episódio', 'episódios')} • ${countLabel(due.length, 'pronto', 'prontos')} para executar`
      : `Fila: ${countLabel(q.length, 'episódio', 'episódios')} • aguardando a renovação diária`;
    queueEl.appendChild(h('div', 'hx-muted', label + ' • salva neste navegador'));
    const row = h('div', 'hx-toolbar', '');
    if (due.length) {
      row.appendChild(btn(`Executar fila agora (${due.length})`, 'hx-btn-primary', () => runQueue()));
    }
    row.appendChild(btn('Limpar fila', '', () => { saveQueue([]); renderQueue(); }));
    queueEl.appendChild(row);
    updateBusy();
  }

  async function newestLogMarker() {
    const rows = data(await sleepSafe(() => api('/api/system/logs'), []));
    let max = '';
    for (const r of rows) if (r.timestamp && r.timestamp > max) max = r.timestamp;
    return max;
  }

  async function providerIssueAfter(marker) {
    const rows = data(await sleepSafe(() => api('/api/system/logs'), []));
    const recent = rows.filter((r) => r.timestamp && r.timestamp > marker);
    recent.sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1));
    let firstIssue = null;
    let finalSeen = false;
    for (const r of recent) {
      const msg = `${r.message || ''} ${r.exception || ''}`.replace(/\s+/g, ' ').trim();
      if (!msg) continue;
      if (/no subtitles were found for this file/i.test(msg)) finalSeen = true;
      if (!firstIssue && (/throttl/i.test(msg) || /authenticationerror|configurationerror|login failed|downloadlimitexceeded|limit exceeded/i.test(msg))) {
        firstIssue = msg.slice(0, 220);
      }
    }
    if (finalSeen) {
      return { final: true, msg: firstIssue ? 'Nenhuma legenda encontrada. Detalhe: ' + firstIssue : 'Nenhuma legenda encontrada nos provedores' };
    }
    return firstIssue ? { final: false, msg: firstIssue } : null;
  }

  async function lastProviderIssue() {
    const rows = data(await sleepSafe(() => api('/api/system/logs'), []));
    rows.sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1));
    for (const r of rows) {
      const when = Date.parse((r.timestamp || '').replace(' ', 'T'));
      if (!when || Date.now() - when > 30 * 60 * 1000) continue;
      const msg = `${r.message || ''} ${r.exception || ''}`.replace(/\s+/g, ' ').trim();
      if (!msg) continue;
      if (/throttl/i.test(msg) || /authenticationerror|configurationerror|login failed|downloadlimitexceeded|limit exceeded/i.test(msg)) return msg.slice(0, 200);
    }
    return null;
  }

  async function refreshDiag() {
    const issue = await lastProviderIssue();
    diag.textContent = issue ? 'Último aviso de provedor: ' + issue : '';
  }

  async function waitEpisode(episodeId, sxxeyy, knownJobs) {
    const started = Date.now();
    while (Date.now() - started < 65000) {
      await sleep(3500);
      let wanted = [];
      try { wanted = await getWanted(); } catch (e) { continue; }
      if (!wanted.some((e) => e.sonarrEpisodeId === episodeId)) return { ok: true };
      const jobs = await getJobs();
      if (sxxeyy && jobs.some((j) => !knownJobs.has(j.job_id) && j.status === 'completed' && (j.job_name || '').includes(sxxeyy))) return { ok: false };
    }
    return { ok: false, timeout: true };
  }

  async function searchOne(ep, miss) {
    const label = episodeLabel(ep);
    const sxxeyy = (label.match(/S\d{2}E\d{2}/) || [])[0];
    const marker = await newestLogMarker();
    const knownJobs = new Set((await getJobs()).map((j) => j.job_id));
    const params = new URLSearchParams({
      seriesid: String(ep.sonarrSeriesId),
      episodeid: String(ep.sonarrEpisodeId),
      language: (miss && miss.code2) || 'pb',
      forced: miss && miss.forced ? 'True' : 'False',
      hi: miss && miss.hi ? 'True' : 'False',
    });
    try {
      await api('/api/episodes/subtitles?' + params.toString(), 'PATCH');
    } catch (e) {
      return { ok: false, label, msg: 'Erro ao iniciar: ' + e.message };
    }
    const result = await waitEpisode(ep.sonarrEpisodeId, sxxeyy, knownJobs);
    if (result.ok) {
      toast('Legenda baixada: ' + label);
      return { ok: true, label };
    }
    const issue = await providerIssueAfter(marker);
    const msg = issue ? issue.msg : (result.timeout ? 'Busca demorou; continua pendente' : 'Não encontrada (continua pendente)');
    toast('Não encontrada: ' + label, false);
    return { ok: false, label, msg, quota: /downloadlimiteexceeded|limit exceeded/i.test(msg) };
  }

  async function runBatch(items, label) {
    if (loading) return;
    loading = true;
    updateBusy();
    let wanted = [];
    try { wanted = await getWanted(); } catch (e) { status.textContent = 'Erro: ' + e.message; status.style.color = '#f87171'; loading = false; updateBusy(); return; }
    const wantedIds = new Set(wanted.map((e) => e.sonarrEpisodeId));
    const list = items.filter((e) => wantedIds.has(e.sonarrEpisodeId));
    if (!list.length) { status.textContent = 'Nada pendente para ' + label; status.style.color = '#9aa0a6'; loading = false; updateBusy(); return; }

    const quota = await refreshQuota();
    let remaining = quota ? Number(quota.remaining_downloads) : SAFE_CAP;
    if (!Number.isFinite(remaining) || remaining < 0) remaining = 0;
    if (remaining <= 0) {
      const due = parseReset(quota);
      list.forEach((e) => queueAdd(e, due));
      renderQueue();
      status.textContent = `Limite diário atingido (${quota ? quota.downloads_count : '?'}/${quota ? quota.allowed_downloads : '?'}). ${countLabel(list.length, 'episódio', 'episódios')} na fila para a próxima renovação diária.`;
      status.style.color = '#f59e0b';
      toast('Limite diário atingido; fila agendada', false);
      loading = false;
      updateBusy();
      return;
    }

    let used = 0;
    let ok = 0;
    let fail = 0;
    let idx = 0;
    const max = Math.min(list.length, remaining);
    for (; idx < list.length && used < remaining; idx++) {
      const ep = list[idx];
      const miss = (ep.missing_subtitles || [])[0] || {};
      status.textContent = `Buscando ${Math.min(idx + 1, max)}/${max}: ${episodeLabel(ep)}...`;
      status.style.color = '#9aa0a6';
      const result = await searchOne(ep, miss);
      if (result.ok) { ok++; used++; } else { fail++; }
      await loadList(true);
      if (result.quota) break;
    }
    loading = false;
    updateBusy();

    const rest = list.slice(idx);
    const quota2 = await getQuota();
    const due = parseReset(quota2);
    rest.forEach((e) => queueAdd(e, due));
    await refreshQuota();
    await loadList(true);
    renderQueue();

    if (rest.length) {
      status.textContent = `Concluído: ${countLabel(ok, 'baixada', 'baixadas')}, ${countLabel(fail, 'falha', 'falhas')}. ${rest.length} na fila para a próxima renovação diária.`;
      status.style.color = '#9aa0a6';
      toast(`${countLabel(ok, 'baixada', 'baixadas')}; ${countLabel(rest.length, 'agendada', 'agendadas')}`);
    } else {
      status.textContent = `Concluído: ${countLabel(ok, 'baixada', 'baixadas')}, ${countLabel(fail, 'falha', 'falhas')}. Restam ${quota2 ? quota2.remaining_downloads : '?'} hoje.`;
      status.style.color = '#9aa0a6';
      toast(`${countLabel(ok, 'baixada', 'baixadas')}, ${countLabel(fail, 'falha', 'falhas')}`);
    }
  }

  async function runQueue() {
    const due = queueDue();
    if (!due.length) { toast('Nada na fila para agora', false); return; }
    queueRemove(due.map((x) => x.sonarrEpisodeId));
    renderQueue();
    const eps = due.map((x) => ({
      sonarrEpisodeId: x.sonarrEpisodeId,
      sonarrSeriesId: x.sonarrSeriesId,
      seriesTitle: x.title,
      season: x.season,
      episode: x.episode,
      missing_subtitles: [{ code2: x.language }],
    }));
    await runBatch(eps, 'fila');
    renderQueue();
  }

  function renderList() {
    list.innerHTML = '';
    const q = norm(filter);
    const sid = String(seriesId || '');
    const rows = subsRows.filter((e) => {
      if (sid && String(e.sonarrSeriesId || '') !== sid) return false;
      if (q && !norm(`${e.seriesTitle || ''} ${e.title || ''} ${episodeLabel(e)}`).includes(q)) return false;
      return true;
    });

    if (!rows.length) {
      const empty = h('div', 'hx-empty', subsRows.length ? 'Nenhum episódio corresponde ao filtro.' : 'Nenhum episódio pendente.');
      list.appendChild(empty);
      updateBusy();
      return;
    }

    const groups = new Map();
    for (const e of rows) {
      const key = e.sonarrSeriesId != null ? String(e.sonarrSeriesId) : (e.seriesTitle || 'outros');
      if (!groups.has(key)) groups.set(key, { title: e.seriesTitle || 'Série ' + key, items: [] });
      groups.get(key).items.push(e);
    }

    const sorted = [...groups.values()].sort((a, b) => a.title.localeCompare(b.title));
    for (const group of sorted) {
      const box = h('div', 'hx-group', '');
      const head = h('div', 'hx-group-head', '');
      head.appendChild(h('div', 'hx-group-title', `${group.title} (${group.items.length})`));
      head.appendChild(btn(`Buscar ${group.items.length}`, '', () => runBatch(group.items, 'série ' + group.title)));
      box.appendChild(head);
      for (const e of group.items) {
        const miss = (e.missing_subtitles || [])[0] || {};
        const row = h('div', 'hx-ep', '');
        row.appendChild(h('div', 'hx-ep-label', episodeLabel(e) + (miss.code2 ? ' • ' + langLabel(miss.code2) : '')));
        const actions = h('div', 'hx-ep-actions', '');
        actions.appendChild(btn('Buscar', '', () => runBatch([e], episodeLabel(e))));
        row.appendChild(actions);
        box.appendChild(row);
      }
      list.appendChild(box);
    }
    updateBusy();
  }

  async function loadList(keepStatus) {
    if (!keepStatus) { status.textContent = 'Carregando pendências...'; status.style.color = '#9aa0a6'; }
    try {
      subsRows = await getWanted();
    } catch (e) {
      status.textContent = 'Erro ao carregar: ' + e.message;
      status.style.color = '#f87171';
      return;
    }
    if (!keepStatus) {
      status.textContent = subsRows.length ? `${countLabel(subsRows.length, 'episódio', 'episódios')} sem legenda` : 'Nenhum episódio pendente.';
      status.style.color = subsRows.length ? '#9aa0a6' : '#4ade80';
    }
    setTabCount('legendas', subsRows.length);
    renderList();
  }

  async function loadSeries() {
    if (Date.now() - seriesTs < 60000 && seriesRows.length) return;
    const rows = data(await sleepSafe(() => api('/api/series'), []));
    seriesRows = rows;
    seriesTs = Date.now();
    const current = seriesSelect.value;
    seriesSelect.innerHTML = '';
    const all = h('option', '', 'Todas as séries');
    all.value = '';
    seriesSelect.appendChild(all);
    for (const s of rows) {
      const opt = h('option', '', s.title || ('Série ' + s.sonarrSeriesId));
      opt.value = String(s.sonarrSeriesId);
      seriesSelect.appendChild(opt);
    }
    if (current && rows.some((s) => String(s.sonarrSeriesId) === current)) seriesSelect.value = current;
    else { seriesSelect.value = ''; seriesId = ''; }
  }

  async function syncAll() {
    const srows = data(await api('/api/series'));
    let ok = 0;
    let fail = 0;
    for (const s of srows) {
      const erows = data(await api('/api/episodes?seriesid[]=' + s.sonarrSeriesId));
      for (const e of erows) {
        for (const sub of (e.subtitles || [])) {
          try {
            const params = new URLSearchParams({
              action: 'sync',
              language: sub.language,
              path: sub.path,
              type: 'episode',
              id: String(e.sonarrEpisodeId),
              forced: sub.forced ? 'True' : 'False',
              hi: sub.hi ? 'True' : 'False',
            });
            await api('/api/subtitles?' + params.toString(), 'PATCH');
            ok++;
          } catch (err) { fail++; }
          await sleep(250);
        }
      }
    }
    status.textContent = `Sincronização concluída: ${countLabel(ok, 'legenda sincronizada', 'legendas sincronizadas')}, ${countLabel(fail, 'falha', 'falhas')}`;
    status.style.color = fail ? '#f59e0b' : '#4ade80';
    toast(`Sincronização: ${ok} ok, ${countLabel(fail, 'falha', 'falhas')}`);
  }

  async function refreshAll() {
    await refreshQuota();
    await refreshDiag();
    await loadSeries();
    renderQueue();
    await loadList();
  }

  searchInput.addEventListener('input', () => { filter = searchInput.value; renderList(); });
  seriesSelect.addEventListener('change', () => { seriesId = seriesSelect.value; renderList(); });

  let lastRefresh = 0;
  return {
    activate() {
      if (Date.now() - lastRefresh < 15000) return;
      lastRefresh = Date.now();
      // fire-and-forget; the pane shows its own loading state
      refreshAll();
    },
    refresh() { lastRefresh = Date.now(); return refreshAll(); },
  };
}
