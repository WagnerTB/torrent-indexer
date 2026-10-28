export const GAMING = 'http://192.168.1.10:8099';
const LOCAL_HOSTS = ['192.168.1.10', 'localhost', '127.0.0.1'];
export const REMOTE = !LOCAL_HOSTS.includes(location.hostname);
export const SERVICE_HOST = REMOTE ? location.hostname : '192.168.1.10';
export const MEDIA = 'http://' + SERVICE_HOST + ':8097';
const REMOTE_CARDS = {
  Jellyfin: [8096, '/'],
  Seerr: [5055, '/'],
  Stremio: [11470, '/'],
};
const HIDDEN_CARDS = ['Radarr', 'Sonarr', 'Bazarr', 'Prowlarr', 'qBittorrent'];
let modeScheduled = false;
let tabCountImpl = () => {};

export const setTabCount = (name, value) => tabCountImpl(name, value);
export function registerTabCount(fn) {
  tabCountImpl = fn;
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function api(path, method = 'GET') {
  const res = await fetch(MEDIA + '/bazarr?path=' + encodeURIComponent(path), { method, cache: 'no-store' });
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}`);
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

export const data = (res) => (res && res.data ? res.data : res) || [];

export const sleepSafe = async (fn, fallback = null) => {
  try { return await fn(); } catch (e) { return fallback; }
};

export const norm = (value) =>
  String(value || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');

export const countLabel = (n, singular, plural) => `${n} ${n === 1 ? singular : plural}`;

const LANG_LABELS = { pb: 'PT-BR', 'pt-br': 'PT-BR', pt: 'PT-BR', en: 'Inglês', es: 'Espanhol' };
export const langLabel = (code) => LANG_LABELS[String(code || '').toLowerCase()] || String(code || '').toUpperCase();

function localizeChrome() {
  document.querySelectorAll('input[placeholder^="Search"]').forEach((input) => {
    input.placeholder = 'Buscar no Seerr...';
    input.setAttribute('aria-label', 'Buscar no Seerr');
  });
}

export function applyMode() {
  document.querySelectorAll('li.service').forEach((li) => {
    const name = li.dataset.name || '';
    li.style.display = REMOTE && HIDDEN_CARDS.includes(name) ? 'none' : '';
    if (REMOTE_CARDS[name]) {
      const [port, suffix] = REMOTE_CARDS[name];
      const href = `http://${SERVICE_HOST}:${port}${suffix}`;
      li.querySelectorAll('a[href]').forEach((a) => { a.href = href; });
    }
    if (REMOTE && name === 'PC Casa') {
      li.querySelectorAll('a[href]').forEach((a) => {
        a.href = '#';
        a.onclick = (event) => event.preventDefault();
      });
    }
  });
  document.querySelectorAll('a[href*=":8096"]').forEach((a) => {
    a.href = `http://${SERVICE_HOST}:8096`;
  });
  document.querySelectorAll('.services-group, .bookmark-group').forEach((group) => {
    const heading = group.querySelector('.service-group-name, .bookmark-group-name');
    const name = (heading ? heading.textContent : '').trim();
    const hiddenGroup = name === 'Atalhos' || name === 'Media Services Status';
    group.style.display = REMOTE && hiddenGroup ? 'none' : '';
  });
  localizeChrome();
}

export function scheduleMode() {
  if (modeScheduled) return;
  modeScheduled = true;
  requestAnimationFrame(() => {
    modeScheduled = false;
    applyMode();
  });
}

export function mk(tag, css, text) {
  const n = document.createElement(tag);
  if (css) n.style.cssText = css;
  if (text != null) n.textContent = text;
  return n;
}

export function h(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

export function btn(text, cls, onClick) {
  const b = h('button', 'hx-btn' + (cls ? ' ' + cls : ''), text);
  b.type = 'button';
  if (onClick) b.addEventListener('click', onClick);
  return b;
}

export function toast(msg, ok = true) {
  let el = document.getElementById('extras-toast');
  if (!el) {
    el = mk('div', 'position:fixed;right:20px;bottom:24px;z-index:100001;padding:10px 14px;border-radius:8px;font:13px system-ui;color:#fff;box-shadow:0 4px 20px rgba(0,0,0,.4);transition:opacity .3s;max-width:340px', '');
    el.id = 'extras-toast';
    document.body.appendChild(el);
  }
  el.style.background = ok ? '#1f7a3d' : '#8b1e1e';
  el.style.opacity = '1';
  el.textContent = msg;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.opacity = '0'; }, 4500);
}

export function fmtDate(value) {
  if (!value) return '';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

export function helpBox(lines) {
  const details = h('details', 'hx-help');
  details.appendChild(h('summary', '', 'Como funciona'));
  const ul = h('ul', '', '');
  for (const line of lines) ul.appendChild(h('li', '', line));
  details.appendChild(ul);
  return details;
}
