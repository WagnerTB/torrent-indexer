import { GAMING, REMOTE, SERVICE_HOST, mk, toast, sleep } from './shared.js';

export function initWakeCard() {
  const WAKE_SEL = 'li.service[data-name="PC Casa"]';
  const WAKE_BASE = REMOTE ? `http://${SERVICE_HOST}:8098` : GAMING;
  const STATUS_URL = REMOTE ? WAKE_BASE + '/gaming/status' : GAMING + '/status';
  const WAKE_URL = REMOTE ? WAKE_BASE + '/gaming/wake' : GAMING + '/wake';
  let alive = false;
  let reachable = false;
  let busy = false;
  let box = null;
  let btnEl = null;
  let scheduled = false;

  function ensureButton() {
    const card = document.querySelector(WAKE_SEL);
    if (!card) return;
    const container = card.querySelector('.service-container');
    if (!container) return;
    if (!container.querySelector('[data-wol-box]')) {
      box = mk('div', 'bg-theme-200/50 dark:bg-theme-900/20 rounded-sm m-1 flex items-center justify-center p-1', '');
      box.setAttribute('data-wol-box', '1');
      btnEl = mk('button', 'cursor:pointer;border:0;border-radius:6px;padding:8px 10px;background:#7b2ff7;color:#fff;font:600 12px system-ui;width:100%;min-height:32px', 'Ligar PC');
      btnEl.type = 'button';
      btnEl.onclick = doWake;
        box.appendChild(btnEl);
        if (REMOTE) {
          box.style.flexDirection = 'column';
          box.style.gap = '4px';
          box.appendChild(mk('div', 'color:#9aa0a6;font:11px system-ui;text-align:center', 'Senha definida no servidor'));
        }
        container.appendChild(box);
    } else {
      box = container.querySelector('[data-wol-box]');
      btnEl = box.querySelector('button');
    }
    updateButton();
  }

  function scheduleEnsure() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      ensureButton();
    });
  }

  function updateButton() {
    if (!box || !btnEl) return;
    const show = alive ? 'none' : '';
    const disabled = busy || !reachable;
    const label = busy ? 'Ligando...' : (reachable ? 'Ligar PC' : 'Agente offline');
    const opacity = disabled ? '0.55' : '1';
      const titleText = reachable ? (REMOTE ? 'Use a senha definida no servidor' : 'Enviar Wake-on-LAN') : 'gaming-agent sem resposta';
    if (box.style.display !== show) box.style.display = show;
    if (btnEl.disabled !== disabled) btnEl.disabled = disabled;
    if (btnEl.style.opacity !== opacity) btnEl.style.opacity = opacity;
    if (btnEl.textContent !== label) btnEl.textContent = label;
    if (btnEl.title !== titleText) btnEl.title = titleText;
  }

  async function refresh() {
    try {
      const res = await fetch(STATUS_URL, { cache: 'no-store' });
      const d = await res.json();
      alive = !!d.online;
      reachable = true;
    } catch (e) {
      alive = false;
      reachable = false;
    }
    updateButton();
  }

  async function doWake() {
    if (busy || !reachable) return;
    let password = '';
    if (REMOTE) {
        password = sessionStorage.getItem('gaming_password') || window.prompt('Senha para ligar o PC:');
      if (!password) return;
    }
    busy = true;
    updateButton();
    try {
      const res = await fetch(WAKE_URL, {
        method: 'POST',
        headers: REMOTE ? { 'X-Gaming-Password': password } : undefined,
      });
      const d = await res.json().catch(() => ({}));
      if (res.status === 401 || res.status === 403) {
        sessionStorage.removeItem('gaming_password');
        throw new Error('senha inválida');
      }
      if (!res.ok || !d.ok) throw new Error(d.error || 'falha ao enviar o WOL');
      if (REMOTE) sessionStorage.setItem('gaming_password', password);
      toast('Pacote WOL enviado. Aguardando o PC...');
    } catch (e) {
      busy = false;
      updateButton();
      toast('Erro ao ligar o PC: ' + (e.message || e), false);
      return;
    }
    const started = Date.now();
    while (Date.now() - started < 90000) {
      await sleep(3000);
      await refresh();
      if (alive) {
        toast('PC da casa está online');
        break;
      }
    }
    if (!alive) toast('O PC ainda não respondeu; tente novamente', false);
    busy = false;
    updateButton();
  }

  const observer = new MutationObserver(scheduleEnsure);
  observer.observe(document.body, { childList: true, subtree: true });
  ensureButton();
  refresh();
  setInterval(refresh, 15000);
}
