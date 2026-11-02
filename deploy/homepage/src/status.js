import { MEDIA, h, toast } from './shared.js';

const REFRESH_MS = 5000;
const WARN_PERCENT = 75;
const CRITICAL_PERCENT = 90;
const WARN_TEMPERATURE = 70;
const CRITICAL_TEMPERATURE = 80;
const TONE_COLORS = {
  ok: '#4ade80',
  warning: '#fbbf24',
  critical: '#f87171',
  unknown: '#60a5fa',
};

function asNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function clampPercent(value) {
  return Math.max(0, Math.min(100, Number(value) || 0));
}

function toneForPercent(value) {
  const number = asNumber(value);
  if (number === null) return 'unknown';
  if (number >= CRITICAL_PERCENT) return 'critical';
  if (number >= WARN_PERCENT) return 'warning';
  return 'ok';
}

function toneForTemperature(value) {
  const number = asNumber(value);
  if (number === null) return 'unknown';
  if (number >= CRITICAL_TEMPERATURE) return 'critical';
  if (number >= WARN_TEMPERATURE) return 'warning';
  return 'ok';
}

function formatPercent(value) {
  const number = asNumber(value);
  return number === null ? '—' : `${Math.round(number)}%`;
}

function formatTemperature(value) {
  const number = asNumber(value);
  return number === null ? '—' : `${number.toFixed(1)} °C`;
}

function formatLoad(value) {
  const number = asNumber(value);
  return number === null ? '—' : number.toFixed(2);
}

function toneClass(tone) {
  return tone ? ` hx-pi-tone--${tone}` : '';
}

function metricCard(label, value, tone) {
  const card = h('div', 'hx-pi-metric', '');
  const head = h('div', 'hx-pi-metric-head', '');
  head.appendChild(h('div', 'hx-pi-metric-label', label));
  const valueEl = h('div', 'hx-pi-metric-value' + toneClass(tone), value);
  head.appendChild(valueEl);
  card.appendChild(head);
  return { card, valueEl };
}

function addBar(card, percent, tone) {
  const bar = h('div', 'hx-pi-bar', '');
  bar.setAttribute('role', 'progressbar');
  bar.setAttribute('aria-valuemin', '0');
  bar.setAttribute('aria-valuemax', '100');
  bar.setAttribute('aria-valuenow', String(Math.round(clampPercent(percent))));
  const fill = h('span', '', '');
  fill.style.width = clampPercent(percent) + '%';
  fill.style.background = TONE_COLORS[tone] || TONE_COLORS.unknown;
  bar.appendChild(fill);
  card.appendChild(bar);
  return bar;
}

function hasPendingEvents(voltage) {
  const flags = voltage.pendingFlags || {};
  return Boolean(
    flags.undervoltageOccurred
    || flags.throttledOccurred
    || flags.frequencyCappedOccurred
    || flags.softTempLimitOccurred
  );
}

function hasActiveEvents(voltage) {
  const flags = voltage.currentFlags || {};
  return Boolean(
    flags.undervoltage
    || flags.throttled
    || flags.frequencyCapped
    || flags.softTempLimit
  );
}

function describeVoltage(voltage) {
  if (!voltage.throttledHex && voltage.core == null) {
    return 'Instale o probe no host para medir voltagem';
  }
  const current = voltage.currentFlags || {};
  const pending = voltage.pendingFlags || {};
  const active = [];
  const occurred = [];
  if (current.undervoltage) active.push('subtensão agora');
  if (current.throttled) active.push('throttling agora');
  if (current.frequencyCapped) active.push('frequência limitada');
  if (current.softTempLimit) active.push('limite térmico');
  if (pending.undervoltageOccurred) occurred.push('subtensão');
  if (pending.throttledOccurred) occurred.push('throttling');
  if (pending.frequencyCappedOccurred) occurred.push('freq. limitada');
  if (pending.softTempLimitOccurred) occurred.push('limite térmico');
  const parts = [];
  if (active.length) parts.push('Agora: ' + active.join(', '));
  if (occurred.length) parts.push('Novas ocorrências: ' + occurred.join(', '));
  if (!active.length && !occurred.length) {
    if (voltage.historyHex && voltage.historyHex !== '0x0') {
      parts.push('Sem evento novo · histórico do boot ignorado');
    } else {
      parts.push('Sem evento atual');
    }
  }
  if (voltage.stale) parts.push('probe desatualizado');
  return parts.join(' · ');
}

export function initStatus() {
  const panel = h('section', '', '');
  panel.id = 'hx-pi-status';
  panel.setAttribute('aria-label', 'Status Raspberry');

  const head = h('div', 'hx-pi-head', '');
  const titleWrap = h('div', 'hx-pi-title-wrap', '');
  titleWrap.appendChild(h('div', 'hx-pi-title', 'Status Raspberry'));
  titleWrap.appendChild(h('div', 'hx-pi-sub', 'CPU, memória, temperatura, voltagem e armazenamento'));

  const meta = h('div', 'hx-pi-meta', '');
  const updated = h('span', 'hx-pi-updated', 'carregando...');
  const refresh = h('button', 'hx-pi-refresh', 'Atualizar');
  refresh.type = 'button';
  refresh.title = 'Atualiza o status do Raspberry';
  const toggle = h('button', 'hx-pi-toggle', 'Abrir');
  toggle.type = 'button';
  toggle.setAttribute('aria-expanded', 'false');
  toggle.setAttribute('aria-controls', 'hx-pi-body');
  toggle.title = 'Expandir detalhes';
  meta.append(updated, refresh, toggle);
  head.append(titleWrap, meta);

  const summary = h('div', 'hx-pi-summary', '');
  const summaryRefs = {};
  const summaryItems = [
    ['cpu', 'CPU'],
    ['memory', 'RAM'],
    ['temperature', 'Temp'],
    ['voltage', 'Voltagem'],
  ];
  for (const [key, label] of summaryItems) {
    const item = h('div', 'hx-pi-summary-item', '');
    item.appendChild(h('span', 'hx-pi-summary-label', label));
    const value = h('span', 'hx-pi-summary-value', '—');
    item.appendChild(value);
    summary.appendChild(item);
    summaryRefs[key] = { item, value };
  }

  const body = h('div', 'hx-pi-body', '');
  body.id = 'hx-pi-body';
  body.hidden = true;
  const metrics = h('div', 'hx-pi-metrics', '');
  const storageTitle = h('div', 'hx-pi-section-title', 'Armazenamento');
  const storageBody = h('div', '', '');
  body.append(metrics, storageTitle, storageBody);

  panel.append(head, summary, body);

  let loading = false;
  let rendered = false;
  let clearing = false;

  function setOpen(open) {
    body.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.textContent = open ? 'Fechar' : 'Abrir';
    toggle.title = open ? 'Recolher detalhes' : 'Expandir detalhes';
  }
  setOpen(false);
  toggle.addEventListener('click', () => setOpen(body.hidden));
  refresh.addEventListener('click', () => load(true));

  function setSummary(key, value, tone, title) {
    const ref = summaryRefs[key];
    if (!ref) return;
    ref.value.textContent = value;
    ref.value.className = 'hx-pi-summary-value' + toneClass(tone);
    ref.item.title = title || '';
  }

  function clearSummary() {
    setSummary('cpu', '—', 'unknown', '');
    setSummary('memory', '—', 'unknown', '');
    setSummary('temperature', '—', 'unknown', '');
    setSummary('voltage', 'N/D', 'unknown', '');
  }

  function renderSummary(data) {
    const cpu = data.cpu || {};
    const memory = data.memory || {};
    const temperature = data.temperature || {};
    const voltage = data.voltage || {};

    setSummary(
      'cpu',
      formatPercent(cpu.percent),
      toneForPercent(cpu.percent),
      `CPU: ${formatPercent(cpu.percent)} · load ${formatLoad(cpu.load1)} / ${formatLoad(cpu.load5)} / ${formatLoad(cpu.load15)}`
    );
    setSummary(
      'memory',
      formatPercent(memory.percent),
      toneForPercent(memory.percent),
      `RAM: ${memory.usedLabel || '—'} de ${memory.totalLabel || '—'} · ${memory.availableLabel || '—'} disponíveis`
    );
    setSummary(
      'temperature',
      formatTemperature(temperature.celsius),
      temperature.status || toneForTemperature(temperature.celsius),
      `Temperatura: ${formatTemperature(temperature.celsius)} · crítico em ${CRITICAL_TEMPERATURE} °C`
    );
    setSummary(
      'voltage',
      voltage.statusLabel || 'N/D',
      voltage.status || 'unknown',
      describeVoltage(voltage)
    );
  }

  function renderCpu(cpu) {
    const percent = asNumber(cpu.percent);
    const tone = toneForPercent(percent);
    const card = metricCard('CPU', formatPercent(percent), tone);
    if (percent !== null) addBar(card.card, percent, tone);
    const parts = [];
    if (cpu.cores) parts.push(`${cpu.cores} núcleos`);
    if (asNumber(cpu.load1) !== null) {
      parts.push(`load ${formatLoad(cpu.load1)} / ${formatLoad(cpu.load5)} / ${formatLoad(cpu.load15)}`);
    }
    card.card.appendChild(h('div', 'hx-pi-metric-sub', parts.join(' · ') || '—'));
    return card.card;
  }

  function renderMemory(memory) {
    const percent = asNumber(memory.percent);
    const tone = toneForPercent(percent);
    const value = memory.total
      ? `${memory.usedLabel || '—'} / ${memory.totalLabel || '—'} (${formatPercent(percent)})`
      : formatPercent(percent);
    const card = metricCard('Memória RAM', value, tone);
    if (percent !== null) addBar(card.card, percent, tone);
    const parts = [`${memory.availableLabel || '—'} disponíveis`];
    if (memory.swapTotal) {
      parts.push(`swap ${memory.swapUsedLabel || '—'} / ${memory.swapTotalLabel || '—'} (${formatPercent(memory.swapPercent)})`);
    }
    card.card.appendChild(h('div', 'hx-pi-metric-sub', parts.join(' · ')));
    return card.card;
  }

  function renderTemperature(temperature) {
    const celsius = asNumber(temperature.celsius);
    const tone = temperature.status || toneForTemperature(celsius);
    const card = metricCard('Temperatura', formatTemperature(celsius), tone);
    if (celsius !== null) addBar(card.card, Math.min(100, celsius), tone);
    const source = temperature.source ? `fonte ${temperature.source}` : '';
    const limit = `crítico em ${CRITICAL_TEMPERATURE} °C`;
    card.card.appendChild(h('div', 'hx-pi-metric-sub', [source, limit].filter(Boolean).join(' · ')));
    return card.card;
  }

  async function clearThrottleNotice() {
    if (clearing) return;
    clearing = true;
    try {
      const response = await fetch(MEDIA + '/status/clear-throttle', { method: 'POST', cache: 'no-store' });
      let payload = null;
      try { payload = await response.json(); } catch (error) { payload = null; }
      if (!response.ok || !payload || payload.ok === false) {
        throw new Error((payload && payload.error) || `POST /status/clear-throttle -> ${response.status}`);
      }
      render(payload);
      if (payload.cleared) {
        updated.textContent = 'aviso limpo ' + new Date().toLocaleTimeString();
        updated.title = payload.generatedAt ? 'Gerado em ' + payload.generatedAt : '';
        toast('Aviso de throttling limpo', true);
      } else {
        toast(payload.error || 'Limpeza solicitada; aguarde o probe', false);
      }
    } catch (error) {
      toast('Não foi possível limpar: ' + error.message, false);
    } finally {
      clearing = false;
    }
  }

  function renderVoltage(voltage) {
    const tone = voltage.status || 'unknown';
    const card = metricCard('Voltagem / throttling', voltage.statusLabel || 'N/D', tone);
    const parts = [];
    if (voltage.coreLabel && voltage.coreLabel !== '—') parts.push(`core ${voltage.coreLabel}`);
    if (voltage.pendingHex && voltage.pendingHex !== '0x0') parts.push(`pendente ${voltage.pendingHex}`);
    if (voltage.historyHex && voltage.historyHex !== '0x0') parts.push(`histórico ${voltage.historyHex}`);
    card.card.appendChild(h('div', 'hx-pi-metric-sub', parts.join(' · ') || 'sem leitura do probe'));
    card.card.appendChild(h('div', 'hx-pi-metric-sub', describeVoltage(voltage)));
    if (hasPendingEvents(voltage) && !hasActiveEvents(voltage)) {
      const clear = h('button', 'hx-pi-clear', 'Limpar aviso');
      clear.type = 'button';
      clear.title = 'Limpa o aviso atual; se ocorrer de novo, volta a aparecer';
      clear.addEventListener('click', async () => {
        clear.disabled = true;
        clear.textContent = 'Limpando...';
        await clearThrottleNotice();
        if (clear.isConnected) {
          clear.disabled = false;
          clear.textContent = 'Limpar aviso';
        }
      });
      card.card.appendChild(clear);
    }
    return card.card;
  }

  function renderUptime(uptime, host) {
    const card = metricCard('Uptime', (uptime && uptime.label) || '—', '');
    const parts = [];
    if (host && host.hostname) parts.push(host.hostname);
    if (host && host.model) parts.push(host.model);
    if (host && host.kernel) parts.push(`kernel ${host.kernel}`);
    card.card.appendChild(h('div', 'hx-pi-metric-sub', parts.join(' · ') || '—'));
    return card.card;
  }

  function renderStorageItem(item) {
    const percent = clampPercent(item.percent);
    const tone = toneForPercent(percent);
    const row = h('div', 'hx-storage-row', '');
    const line = h('div', 'hx-storage-line', '');
    const label = h('div', 'hx-storage-label', '');
    label.appendChild(document.createTextNode(item.label || 'Armazenamento'));
    if (item.kind) label.appendChild(h('span', 'hx-storage-kind', item.kind));
    const value = h('div', 'hx-storage-value', `${item.usedLabel || '—'} / ${item.totalLabel || '—'} · ${Math.round(percent)}%`);
    line.append(label, value);

    const parts = Array.isArray(item.parts) ? item.parts : [];
    const risk = Math.max(percent, ...parts.map((part) => clampPercent(part.percent)));
    const bar = h('div', 'hx-storage-bar', '');
    bar.setAttribute('role', 'progressbar');
    bar.setAttribute('aria-label', `Uso de ${item.label || 'armazenamento'}`);
    bar.setAttribute('aria-valuemin', '0');
    bar.setAttribute('aria-valuemax', '100');
    bar.setAttribute('aria-valuenow', String(Math.round(percent)));
    const fill = h('span', '', '');
    fill.style.width = percent + '%';
    fill.style.background = TONE_COLORS[toneForPercent(risk)];
    bar.appendChild(fill);

    const bits = [];
    if (parts.length > 1) {
      for (const part of parts) {
        const partPercent = clampPercent(part.percent);
        bits.push(`${part.label} ${part.usedLabel || '—'}/${part.totalLabel || '—'} (${Math.round(partPercent)}%)`);
      }
    } else {
      bits.push(`${item.freeLabel || '—'} livres`);
    }
    const sub = h('div', 'hx-storage-sub', bits.join(' • '));
    row.append(line, bar, sub);
    return row;
  }

  function renderStorage(items) {
    storageBody.innerHTML = '';
    if (!Array.isArray(items) || !items.length) {
      storageBody.appendChild(h('div', 'hx-storage-empty', 'Nenhum armazenamento configurado.'));
      return;
    }
    for (const item of items) storageBody.appendChild(renderStorageItem(item));
  }

  function renderDetails(data) {
    metrics.innerHTML = '';
    metrics.appendChild(renderCpu(data.cpu || {}));
    metrics.appendChild(renderMemory(data.memory || {}));
    metrics.appendChild(renderTemperature(data.temperature || {}));
    metrics.appendChild(renderVoltage(data.voltage || {}));
    metrics.appendChild(renderUptime(data.uptime || {}, data.host || {}));
    renderStorage(data.storage && data.storage.items);
  }

  function render(data) {
    renderSummary(data);
    renderDetails(data);
    rendered = true;
  }

  function renderError(message) {
    if (!rendered) {
      clearSummary();
      metrics.innerHTML = '';
      metrics.appendChild(h('div', 'hx-storage-empty', 'Não foi possível ler o status: ' + message));
      storageBody.innerHTML = '';
      storageBody.appendChild(h('div', 'hx-storage-empty', 'Não foi possível ler o armazenamento: ' + message));
    }
  }

  async function load(force) {
    if (loading) return;
    loading = true;
    if (force) {
      refresh.disabled = true;
      refresh.textContent = 'Atualizando...';
    }
    try {
      const response = await fetch(MEDIA + '/status', { cache: 'no-store' });
      let payload = null;
      try { payload = await response.json(); } catch (error) { payload = null; }
      if (!response.ok || !payload || payload.ok === false) {
        throw new Error((payload && payload.error) || `GET /status -> ${response.status}`);
      }
      render(payload);
      updated.textContent = 'atualizado ' + new Date().toLocaleTimeString();
      updated.title = payload.generatedAt ? 'Gerado em ' + payload.generatedAt : '';
    } catch (error) {
      renderError(error.message);
      updated.textContent = 'erro';
      updated.title = error.message;
    } finally {
      loading = false;
      refresh.disabled = false;
      refresh.textContent = 'Atualizar';
    }
  }

  function ensure() {
    const container = document.querySelector('#inner_wrapper > .container') || document.querySelector('.container');
    if (!container) return;
    const widgets = container.querySelector('#information-widgets');
    if (widgets && widgets.parentNode) {
      if (panel.parentElement !== widgets.parentNode || panel.nextElementSibling !== widgets) {
        widgets.parentNode.insertBefore(panel, widgets);
      }
      return;
    }
    const layout = container.querySelector('#layout-groups');
    if (layout && layout.parentNode) {
      if (panel.parentElement !== layout.parentNode || panel.nextElementSibling !== layout) {
        layout.parentNode.insertBefore(panel, layout);
      }
      return;
    }
    if (panel.parentElement !== container) container.appendChild(panel);
  }

  let scheduled = false;
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; ensure(); });
  };
  if (document.body) {
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true });
  }
  ensure();
  load(false);
  setInterval(() => {
    if (document.visibilityState === 'visible' && !document.body.classList.contains('hx-tab-active')) {
      load(false);
    }
  }, REFRESH_MS);

  return {
    refresh() { return load(false); },
  };
}
