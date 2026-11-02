import { MEDIA, sleep, api, data, sleepSafe, norm, countLabel, langLabel, h, btn, toast, fmtDate, setTabCount, helpBox } from './shared.js';

const QKEY = 'subs_queue_v1';
const AUTO_LOCK = 'subs_queue_auto_v1';
const AUTO_COOLDOWN = 30 * 60 * 1000;
const SAFE_CAP = 5;

export function initSubs(root) {
  let subsRows = [];
  let seriesRows = [];
  let seriesTs = 0;
  let filter = '';
  let seriesId = '';
  let langFilter = '';
  let loading = false;
  let syncing = false;
  let reloading = false;
  let batch = null;
  const subUi = new Map();

  const quotaEl = h('div', 'hx-quota', '');
  const quotaLine = h('div', 'hx-quota-line', 'OpenSubtitles: verificando quota...');
  const quotaBar = h('div', 'hx-bar', '');
  quotaBar.setAttribute('role', 'progressbar');
  quotaBar.setAttribute('aria-label', 'Quota restante do OpenSubtitles');
  quotaBar.setAttribute('aria-valuemin', '0');
  quotaBar.setAttribute('aria-valuemax', '0');
  quotaBar.setAttribute('aria-valuenow', '0');
  const quotaFill = h('span', '', '');
  quotaBar.appendChild(quotaFill);
  quotaEl.append(quotaLine, quotaBar);

  const status = h('div', 'hx-muted', '');
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const diag = h('div', 'hx-warn', '');
  diag.setAttribute('role', 'status');
  diag.setAttribute('aria-live', 'polite');
  const queueEl = h('div', '', '');

  const searchInput = h('input', 'hx-input hx-search');
  searchInput.type = 'search';
  searchInput.placeholder = 'Filtrar por série ou episódio...';
  searchInput.setAttribute('aria-label', 'Filtrar legendas por série ou episódio');

  const seriesSelect = h('select', 'hx-select hx-compact');
  seriesSelect.setAttribute('aria-label', 'Filtrar por série');
  const allOption = h('option', '', 'Todas as séries');
  allOption.value = '';
  seriesSelect.appendChild(allOption);

  const langSelect = h('select', 'hx-select hx-compact');
  langSelect.setAttribute('aria-label', 'Filtrar legendas por idioma');
  langSelect.title = 'Mostra só episódios com esse idioma pendente';
  const langAll = h('option', '', 'Idioma: todos');
  langAll.value = '';
  langSelect.appendChild(langAll);

  const bAll = btn('Buscar pendentes', 'hx-btn-primary', async () => {
    const wanted = await getWanted();
    await runBatch(wanted, 'todas pendentes');
  });
  bAll.title = 'Busca todos os episódios pendentes; usa PT-BR quando disponível';
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
  toolbar.append(searchInput, seriesSelect, langSelect, bAll, bSync, bReload);

  const list = h('div', '', '');

  const help = helpBox([
    'Esta aba lista os episódios sem legenda detectados pelo Bazarr.',
    'A quota é o limite diário do OpenSubtitles; a renovação é diária e o horário exato não é informado.',
    'A fila é salva neste navegador e roda automaticamente quando a renovação chega, com esta aba aberta e visível. Não acompanha outro dispositivo.',
    '“Sincronizar existentes” reprocessa as legendas que já estão no Bazarr e pode levar alguns minutos.',
    'Pedidos (vídeo) e Legendas são fluxos separados.',
  ]);

  root.append(help, quotaEl, status, diag, queueEl, toolbar, list);

  function updateBusy() {
    const on = loading || syncing || reloading;
    bAll.disabled = on;
    bSync.disabled = on;
    bReload.disabled = on;
    bAll.textContent = loading ? 'Buscando...' : (subsRows.length ? `Buscar pendentes (${subsRows.length})` : 'Buscar pendentes');
    bSync.textContent = syncing ? 'Sincronizando...' : 'Sincronizar existentes';
    bReload.textContent = reloading ? 'Atualizando...' : 'Atualizar';
    list.querySelectorAll('.hx-sub-action, .hx-sub-batch, .hx-ep-actions button').forEach((b) => { b.disabled = on; });
    queueEl.querySelectorAll('button').forEach((b) => { b.disabled = on; });
  }

  const pad2 = (value) => String(Number(value) || 0).padStart(2, '0');

  const episodeLabel = (e) => {
    const m = String(e.episode_number || '').match(/(\d+)\s*x\s*(\d+)/i);
    if (m) return `${e.seriesTitle || 'Item'} S${m[1].padStart(2, '0')}E${m[2].padStart(2, '0')}`;
    return `${e.seriesTitle || 'Item'} S${pad2(e.season)}E${pad2(e.episode)}`;
  };

  function seriesKey(item) {
    return item.sonarrSeriesId != null ? String(item.sonarrSeriesId) : (item.seriesTitle || 'outros');
  }

  function startBatch(items, label) {
    const groups = new Map();
    for (const item of items) {
      const key = seriesKey(item);
      if (!groups.has(key)) groups.set(key, { total: 0, done: 0 });
      groups.get(key).total++;
    }
    batch = { label, groups, currentKey: '' };
  }

  const PT_CODES = new Set(['pb', 'pt-br', 'pt']);

  function languageKey(code) {
    const value = String(code || '').toLowerCase();
    if (!value) return '';
    return PT_CODES.has(value) ? 'pt' : value;
  }

  function pickMissing(list) {
    const missings = (list || []).filter((miss) => miss && miss.code2);
    for (const code of ['pb', 'pt-br', 'pt']) {
      const hit = missings.find((miss) => String(miss.code2).toLowerCase() === code);
      if (hit) return hit;
    }
    return missings[0] || {};
  }

  function missingFor(list, language) {
    const missings = (list || []).filter((miss) => miss && miss.code2);
    const target = languageKey(language);
    if (!target) return pickMissing(missings);
    if (target === 'pt') {
      for (const code of ['pb', 'pt-br', 'pt']) {
        const hit = missings.find((miss) => String(miss.code2).toLowerCase() === code);
        if (hit) return hit;
      }
      return pickMissing(missings);
    }
    return missings.find((miss) => languageKey(miss.code2) === target) || pickMissing(missings);
  }

  function matchesLanguage(item, language) {
    if (!language) return true;
    const target = languageKey(language);
    return (item.missing_subtitles || []).some((miss) => miss && miss.code2 && languageKey(miss.code2) === target);
  }

  function languageCodes(items) {
    const map = new Map();
    for (const item of items) {
      for (const miss of (item.missing_subtitles || [])) {
        if (!miss || !miss.code2) continue;
        const key = languageKey(miss.code2);
        if (!map.has(key)) map.set(key, langLabel(miss.code2));
      }
    }
    return [...map.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }

  function languageSummary(items, language) {
    if (language) return [langLabel(language)];
    const labels = new Set();
    for (const item of items) {
      for (const miss of (item.missing_subtitles || [])) {
        if (miss && miss.code2) labels.add(langLabel(miss.code2));
      }
    }
    return [...labels];
  }
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
      quotaBar.setAttribute('aria-valuemax', '0');
      quotaBar.setAttribute('aria-valuenow', '0');
      quotaBar.setAttribute('aria-label', 'Quota do OpenSubtitles indisponível');
      return;
    }
    const left = Number(q.remaining_downloads) || 0;
    const allowed = Number(q.allowed_downloads) || 0;
    quotaLine.textContent = `OpenSubtitles: ${left}/${allowed} restantes • renovação diária`;
    quotaLine.style.color = left > 0 ? '#c9ccd1' : '#f87171';
    quotaFill.style.width = allowed > 0 ? `${Math.max(0, Math.min(100, (left / allowed) * 100))}%` : '0%';
    quotaFill.style.background = left > 0 ? '#4ade80' : '#f87171';
    quotaBar.setAttribute('aria-valuemax', String(allowed));
    quotaBar.setAttribute('aria-valuenow', String(left));
    quotaBar.setAttribute('aria-label', `Quota restante do OpenSubtitles: ${left} de ${allowed}`);
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
  function queueAdd(ep, dueAt, language) {
    const q = loadQueue();
    if (!q.some((x) => x.sonarrEpisodeId === ep.sonarrEpisodeId)) {
      const miss = missingFor(ep.missing_subtitles, language);
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
    const now = Date.now();
    const due = q.filter((x) => (x.dueAt || 0) <= now);
    const box = h('details', 'hx-help hx-queue', '');
    box.open = due.length > 0;
    const summary = h('summary', 'hx-queue-head', '');
    summary.append(
      h('span', '', `Fila de legendas${q.length ? ` (${q.length})` : ''}`),
      h('span', 'hx-queue-note', q.length
        ? (due.length ? `${countLabel(due.length, 'pronto', 'prontos')} para executar` : 'aguardando a renovação diária')
        : 'vazia • salva neste navegador'),
    );
    box.appendChild(summary);
    const body = h('div', 'hx-queue-body', '');
    body.appendChild(h('div', 'hx-muted', q.length
      ? (due.length ? 'A fila é salva neste navegador e roda automaticamente quando a renovação chega.' : 'A fila é salva neste navegador; aguardando a renovação diária.')
      : 'A fila é salva neste navegador e não acompanha outro dispositivo.'));
    if (q.length) {
      const items = q.slice().sort((a, b) => (a.title || '').localeCompare(b.title || '', 'pt-BR', { numeric: true })
        || (Number(a.season) - Number(b.season))
        || (Number(a.episode) - Number(b.episode)));
      const queueList = h('div', 'hx-queue-list', '');
      for (const item of items.slice(0, 8)) {
        const ready = (item.dueAt || 0) <= now;
        const queueItem = h('div', 'hx-queue-item', '');
        queueItem.append(
          h('span', 'hx-queue-item-title', `${item.title || 'Série'} S${pad2(item.season)}E${pad2(item.episode)}`),
          h('span', 'hx-queue-item-meta', `${langLabel(item.language)} • ${ready ? 'pronto' : fmtDate(item.dueAt)}`),
        );
        queueList.appendChild(queueItem);
      }
      if (items.length > 8) queueList.appendChild(h('div', 'hx-queue-more', `e mais ${items.length - 8}`));
      body.appendChild(queueList);
    }
    const row = h('div', 'hx-toolbar', '');
    if (due.length) row.appendChild(btn(`Executar fila agora (${due.length})`, 'hx-btn-primary', () => runQueue()));
    if (q.length) row.appendChild(btn('Limpar fila', '', () => { saveQueue([]); renderQueue(); }));
    body.appendChild(row);
    box.appendChild(body);
    queueEl.appendChild(box);
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

  async function runBatch(items, label, language = '') {
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
      list.forEach((e) => queueAdd(e, due, language));
      renderQueue();
      status.textContent = `Limite diário atingido (${quota ? quota.downloads_count : '?'}/${quota ? quota.allowed_downloads : '?'}). ${countLabel(list.length, 'episódio', 'episódios')} na fila para a próxima renovação diária.`;
      status.style.color = '#f59e0b';
      toast('Limite diário atingido; fila agendada', false);
      loading = false;
      updateBusy();
      return;
    }

    startBatch(list, label);
    let used = 0;
    let ok = 0;
    let fail = 0;
    let idx = 0;
    const max = Math.min(list.length, remaining);
    for (; idx < list.length && used < remaining; idx++) {
      const ep = list[idx];
      const key = seriesKey(ep);
      const miss = missingFor(ep.missing_subtitles, language);
      if (batch) {
        batch.currentKey = key;
        renderList();
      }
      status.textContent = `Buscando ${Math.min(idx + 1, max)}/${max}: ${episodeLabel(ep)}...`;
      status.style.color = '#9aa0a6';
      const result = await searchOne(ep, miss);
      if (batch) {
        const group = batch.groups.get(key);
        if (group) group.done = Math.min(group.total, group.done + 1);
      }
      if (result.ok) { ok++; used++; } else { fail++; }
      await loadList(true);
      if (result.quota) break;
    }
    batch = null;
    loading = false;
    updateBusy();

    const rest = list.slice(idx);
    const quota2 = await getQuota();
    const due = parseReset(quota2);
    rest.forEach((e) => queueAdd(e, due, language));
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
    if (loading || syncing || reloading) return;
    const due = queueDue();
    if (!due.length) { toast('Nada na fila para agora', false); return; }
    try { localStorage.setItem(AUTO_LOCK, String(Date.now())); } catch (e) { /* ignore */ }
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

  function episodeCode(e) {
    const m = String(e.episode_number || '').match(/(\d+)\s*x\s*(\d+)/i);
    const season = m ? m[1] : String(e.season || 0);
    const episode = m ? m[2] : String(e.episode || 0);
    return `S${season.padStart(2, '0')}E${episode.padStart(2, '0')}`;
  }

  function renderList() {
    list.innerHTML = '';
    const q = norm(filter);
    const sid = String(seriesId || '');
    const rows = subsRows.filter((e) => {
      if (sid && String(e.sonarrSeriesId || '') !== sid) return false;
      if (!matchesLanguage(e, langFilter)) return false;
      if (q && !norm(`${e.seriesTitle || ''} ${e.title || ''} ${episodeLabel(e)}`).includes(q)) return false;
      return true;
    });

    if (!rows.length) {
      const empty = h('div', 'hx-empty', subsRows.length ? 'Nenhum episódio corresponde ao filtro.' : 'Nenhum episódio pendente.');
      if (subsRows.length) {
        empty.appendChild(btn('Limpar filtro', '', () => {
          filter = '';
          seriesId = '';
          langFilter = '';
          searchInput.value = '';
          seriesSelect.value = '';
          langSelect.value = '';
          subUi.clear();
          renderList();
        }));
      }
      list.appendChild(empty);
      updateBusy();
      return;
    }

    const groups = new Map();
    for (const e of rows) {
      const key = e.sonarrSeriesId != null ? String(e.sonarrSeriesId) : (e.seriesTitle || 'outros');
      if (!groups.has(key)) groups.set(key, { key, title: e.seriesTitle || 'Série ' + key, items: [] });
      groups.get(key).items.push(e);
    }

    const sorted = [...groups.values()].sort((a, b) => a.title.localeCompare(b.title));
    const hasFilter = Boolean(q) || Boolean(sid) || Boolean(langFilter);
    const defaultOpen = hasFilter || sorted.length === 1;

    const summary = h('div', 'hx-sub-summary', '');
    summary.appendChild(h('span', 'hx-muted', `${countLabel(sorted.length, 'série', 'séries')} • ${countLabel(rows.length, 'episódio', 'episódios')}${hasFilter ? ' no filtro' : ''}`));
    const summaryActions = h('div', 'hx-sub-summary-actions', '');
    if (hasFilter) {
      summaryActions.appendChild(btn(`Buscar no filtro (${rows.length})`, 'hx-sub-batch', () => runBatch(rows, 'filtro', langFilter)));
    }
    if (sorted.length > 1) {
      summaryActions.appendChild(btn('Expandir tudo', 'hx-sub-all', () => {
        sorted.forEach((group) => subUi.set(group.key, true));
        renderList();
      }));
      summaryActions.appendChild(btn('Recolher tudo', 'hx-sub-all', () => {
        sorted.forEach((group) => subUi.set(group.key, false));
        renderList();
      }));
    }
    if (summaryActions.childNodes.length) summary.appendChild(summaryActions);
    list.appendChild(summary);

    for (const group of sorted) {
      if (!subUi.has(group.key)) subUi.set(group.key, defaultOpen);
      const open = subUi.get(group.key) === true;
      const langs = languageSummary(group.items, langFilter);
      const meta = `${countLabel(group.items.length, 'pendente', 'pendentes')}${langs.length ? ' • ' + langs.join(' • ') : ''}`;

      const box = h('article', 'hx-order hx-sub-card', '');
      const head = h('div', 'hx-sub-head', '');
      const toggle = h('button', 'hx-sub-toggle', '');
      toggle.type = 'button';
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', `${group.title}: ${open ? 'recolher' : 'expandir'} episódios`);
      const text = h('span', 'hx-sub-text', '');
      text.append(h('span', 'hx-sub-title', `${group.title} (${group.items.length})`), h('span', 'hx-sub-meta', meta));
      toggle.appendChild(text);

      const searchGroup = btn(`Buscar ${group.items.length}`, 'hx-sub-action', () => runBatch(group.items, 'série ' + group.title, langFilter));
      searchGroup.title = `Buscar legenda para ${countLabel(group.items.length, 'episódio', 'episódios')} desta série`;
      head.append(toggle, searchGroup);

      const body = h('div', 'hx-sub-body', '');
      body.hidden = !open;
      for (const e of group.items) {
        const miss = missingFor(e.missing_subtitles, langFilter);
        const row = h('div', 'hx-ep hx-sub-row', '');
        const main = h('div', 'hx-sub-main', '');
        const line = h('div', 'hx-sub-line', '');
        line.appendChild(h('span', 'hx-sub-code', episodeCode(e)));
        if (e.title) line.appendChild(h('span', 'hx-sub-name', e.title));
        if (miss.code2) {
          const lang = h('span', 'hx-sub-lang', langLabel(miss.code2));
          lang.title = 'Idioma usado na busca';
          line.appendChild(lang);
        }
        main.appendChild(line);
        const actions = h('div', 'hx-ep-actions', '');
        actions.appendChild(btn('Buscar', '', () => runBatch([e], episodeLabel(e), langFilter)));
        row.append(main, actions);
        body.appendChild(row);
      }

      toggle.addEventListener('click', () => {
        const next = !(subUi.get(group.key) === true);
        subUi.set(group.key, next);
        toggle.setAttribute('aria-expanded', String(next));
        toggle.setAttribute('aria-label', `${group.title}: ${next ? 'recolher' : 'expandir'} episódios`);
        body.hidden = !next;
      });

      box.appendChild(head);
      const progress = batch && batch.groups.get(group.key);
      if (progress) {
        const active = batch.currentKey === group.key;
        const pct = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;
        const line = h('div', 'hx-sub-progress', '');
        line.appendChild(h('span', 'hx-sub-progress-label', active
          ? `Buscando ${Math.min(progress.done + 1, progress.total)}/${progress.total}`
          : `${progress.done}/${progress.total} concluídos`));
        const bar = h('div', 'hx-sub-progress-bar', '');
        const fill = h('span', '', '');
        fill.style.width = pct + '%';
        bar.appendChild(fill);
        line.appendChild(bar);
        box.appendChild(line);
      }
      box.appendChild(body);
      list.appendChild(box);
    }
    updateBusy();
  }

  function renderLanguageOptions() {
    const current = langFilter;
    langSelect.innerHTML = '';
    const all = h('option', '', 'Idioma: todos');
    all.value = '';
    langSelect.appendChild(all);
    const codes = languageCodes(subsRows);
    for (const [code, label] of codes) {
      const option = h('option', '', label);
      option.value = code;
      langSelect.appendChild(option);
    }
    if (current && codes.some(([code]) => code === current)) {
      langSelect.value = current;
    } else {
      langSelect.value = '';
      langFilter = '';
    }
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
      const seriesCount = new Set(subsRows.map((e) => e.sonarrSeriesId != null ? String(e.sonarrSeriesId) : (e.seriesTitle || 'outros'))).size;
      status.textContent = subsRows.length
        ? `${countLabel(subsRows.length, 'episódio', 'episódios')} sem legenda em ${countLabel(seriesCount, 'série', 'séries')}`
        : 'Nenhum episódio pendente.';
      status.style.color = subsRows.length ? '#9aa0a6' : '#4ade80';
    }
    setTabCount('legendas', subsRows.length);
    renderLanguageOptions();
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
    maybeAutoQueue();
  }

  function maybeAutoQueue() {
    if (loading || syncing || reloading) return;
    if (document.visibilityState !== 'visible') return;
    const due = queueDue();
    if (!due.length) return;
    let locked = 0;
    try { locked = Number(localStorage.getItem(AUTO_LOCK) || 0); } catch (e) { locked = 0; }
    if (locked && Date.now() - locked < AUTO_COOLDOWN) return;
    try { localStorage.setItem(AUTO_LOCK, String(Date.now())); } catch (e) { /* ignore */ }
    toast(`Fila automática: ${countLabel(due.length, 'episódio', 'episódios')}`);
    runQueue();
  }

  searchInput.addEventListener('input', () => { filter = searchInput.value; subUi.clear(); renderList(); });
  seriesSelect.addEventListener('change', () => { seriesId = seriesSelect.value; subUi.clear(); renderList(); });
  langSelect.addEventListener('change', () => { langFilter = langSelect.value; subUi.clear(); renderList(); });
  window.setInterval(maybeAutoQueue, 60000);

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
