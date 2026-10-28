import { MEDIA, h } from './shared.js';

export function initStorage() {
  const panel = h('section', '', '');
  panel.id = 'hx-storage';

  const head = h('div', 'hx-storage-head', '');
  const title = h('div', 'hx-storage-title', 'Armazenamento');
  const meta = h('div', 'hx-storage-meta', '');
  const updated = h('span', 'hx-storage-updated', 'carregando...');
  const refresh = h('button', 'hx-storage-refresh', 'Atualizar');
  refresh.type = 'button';
  refresh.title = 'Atualiza o uso de armazenamento do host';
  refresh.addEventListener('click', () => load(true));
  meta.append(updated, refresh);
  head.append(title, meta);
  const body = h('div', '', '');
  panel.append(head, body);

  let loading = false;

  function renderItem(item) {
    const pct = Math.max(0, Math.min(100, Math.round(Number(item.percent) || 0)));
    const row = h('div', 'hx-storage-row', '');
    const line = h('div', 'hx-storage-line', '');
    const label = h('div', 'hx-storage-label', '');
    label.appendChild(document.createTextNode(item.label || 'Armazenamento'));
    if (item.kind) label.appendChild(h('span', 'hx-storage-kind', item.kind));
    const value = h('div', 'hx-storage-value', `${item.usedLabel || '—'} / ${item.totalLabel || '—'} · ${pct}%`);
    line.append(label, value);

    const parts = Array.isArray(item.parts) ? item.parts : [];
    const risk = Math.max(pct, ...parts.map((part) => Math.max(0, Math.min(100, Math.round(Number(part.percent) || 0)))));
    const bar = h('div', 'hx-storage-bar', '');
    bar.setAttribute('role', 'progressbar');
    bar.setAttribute('aria-label', `Uso de ${item.label || 'armazenamento'}`);
    bar.setAttribute('aria-valuemin', '0');
    bar.setAttribute('aria-valuemax', '100');
    bar.setAttribute('aria-valuenow', String(pct));
    const fill = h('span', '', '');
    fill.style.width = pct + '%';
    fill.style.background = risk >= 90 ? '#f87171' : risk >= 75 ? '#fbbf24' : '#4ade80';
    bar.appendChild(fill);

    const bits = [];
    if (parts.length > 1) {
      for (const part of parts) {
        const partPct = Math.max(0, Math.min(100, Math.round(Number(part.percent) || 0)));
        bits.push(`${part.label} ${part.usedLabel}/${part.totalLabel} (${partPct}%)`);
      }
    } else {
      bits.push(`${item.freeLabel || '—'} livres`);
    }
    const sub = h('div', 'hx-storage-sub', bits.join(' • '));
    row.append(line, bar, sub);
    return row;
  }

  function render(items) {
    body.innerHTML = '';
    if (!items.length) {
      body.appendChild(h('div', 'hx-storage-empty', 'Nenhum armazenamento configurado.'));
      return;
    }
    for (const item of items) body.appendChild(renderItem(item));
  }

  async function load(force) {
    if (loading) return;
    loading = true;
    if (force) {
      refresh.disabled = true;
      refresh.textContent = 'Atualizando...';
      updated.textContent = 'carregando...';
    }
    try {
      const res = await fetch(MEDIA + '/storage', { cache: 'no-store' });
      let payload = null;
      try { payload = await res.json(); } catch (e) { payload = null; }
      if (!res.ok || !payload || payload.ok === false) {
        throw new Error((payload && payload.error) || `GET /storage -> ${res.status}`);
      }
      render(payload.items || []);
      updated.textContent = 'atualizado ' + new Date().toLocaleTimeString();
    } catch (e) {
      body.innerHTML = '';
      body.appendChild(h('div', 'hx-storage-empty', 'Não foi possível ler o armazenamento: ' + e.message));
      updated.textContent = 'erro';
    } finally {
      loading = false;
      if (force) {
        refresh.disabled = false;
        refresh.textContent = 'Atualizar';
      }
    }
  }

  function ensure() {
    const container = document.querySelector('#inner_wrapper > .container') || document.querySelector('.container');
    if (!container) return;
    const widgets = container.querySelector('#information-widgets');
    if (widgets) {
      if (panel.parentElement !== container || panel.previousElementSibling !== widgets) {
        widgets.parentNode.insertBefore(panel, widgets.nextSibling);
      }
      return;
    }
    const layout = container.querySelector('#layout-groups');
    if (layout) {
      if (panel.parentElement !== container || panel.nextElementSibling !== layout) {
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
    if (document.visibilityState === 'visible' && !document.body.classList.contains('hx-tab-active')) load(false);
  }, 60000);

  return {
    refresh() { return load(false); },
  };
}
