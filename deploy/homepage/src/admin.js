import { ADMIN, h, btn, toast } from './shared.js';

const KEY = 'admin_password';
const REFRESH_MS = 15000;

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function stateTone(service) {
  if (service.state === 'restarting' || service.state === 'paused') return 'warn';
  if (service.state !== 'running') return 'stopped';
  if (service.health === 'unhealthy') return 'bad';
  if (service.health === 'starting') return 'warn';
  return 'ok';
}

function stateLabel(service) {
  if (service.state === 'running') {
    if (service.health === 'healthy') return 'saudável';
    if (service.health === 'unhealthy') return 'problema';
    if (service.health === 'starting') return 'iniciando';
    return 'rodando';
  }
  const labels = {
    exited: 'parado',
    paused: 'pausado',
    restarting: 'reiniciando',
    created: 'criado',
    dead: 'morto',
    removing: 'removendo',
    unknown: 'desconhecido',
  };
  return labels[service.state] || service.state || 'desconhecido';
}

function servicesSummary(services) {
  const running = services.filter((service) => service.state === 'running').length;
  const stopped = services.filter((service) => service.state !== 'running').length;
  const unhealthy = services.filter(
    (service) => service.health === 'unhealthy' || service.state === 'restarting'
  ).length;
  return { running, stopped, unhealthy, total: services.length };
}

function formatTime(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function accessError(error) {
  const message = String((error && error.message) || error || 'erro');
  if (/fetch|network|load failed/i.test(message)) {
    return 'Não foi possível falar com o admin-agent. Confirme que você está na LAN e que o serviço está no ar.';
  }
  return message;
}

export function initAdmin(pane) {
  let unlocked = false;
  let loading = false;
  let busyService = '';
  let services = [];
  let auditItems = [];
  let query = '';
  let filter = 'all';
  let updatedAt = '';
  let lastError = '';
  let refs = null;

  async function request(path, options = {}, password = null) {
    const pass = password === null ? (sessionStorage.getItem(KEY) || '') : password;
    const headers = Object.assign({ 'X-Admin-Password': pass }, options.headers || {});
    const response = await fetch(ADMIN + path, {
      cache: 'no-store',
      ...options,
      headers,
    });
    let payload = null;
    try { payload = await response.json(); } catch (error) { payload = null; }
    return { response, payload };
  }

  async function api(path, options) {
    const { response, payload } = await request(path, options);
    if (response.status === 401) {
      sessionStorage.removeItem(KEY);
      unlocked = false;
      renderLock('Senha inválida ou sessão expirada.');
      throw new Error('senha inválida');
    }
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error((payload && payload.error) || `HTTP ${response.status}`);
    }
    return payload;
  }

  function lockScreen(message) {
    const wrap = h('div', 'hx-admin-lock', '');
    const card = h('div', 'hx-admin-lock-card', '');
    const icon = h('div', 'hx-admin-lock-icon', '🔒');
    icon.setAttribute('aria-hidden', 'true');
    const title = h('h2', 'hx-admin-lock-title', 'Administração');
    const sub = h('p', 'hx-admin-lock-sub', 'Acesso restrito à LAN. Informe a senha dedicada do admin-agent.');
    const input = document.createElement('input');
    input.type = 'password';
    input.className = 'hx-input hx-admin-password';
    input.placeholder = 'Senha do admin-agent';
    input.autocomplete = 'current-password';
    input.setAttribute('aria-label', 'Senha do admin-agent');
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        enter();
      }
    });
    const error = h('div', 'hx-error', message || '');
    const submit = btn('Entrar', 'hx-btn-primary hx-admin-enter', () => enter());
    const hint = h(
      'p',
      'hx-admin-hint',
      'A senha fica apenas nesta aba (sessionStorage) e é enviada no header para a Pi.'
    );
    const row = h('div', 'hx-admin-lock-form', '');
    row.append(input, submit);
    card.append(icon, title, sub, row, error, hint);
    wrap.appendChild(card);
    clear(pane);
    pane.appendChild(wrap);
    input.focus();

    async function enter() {
      const pass = input.value.trim();
      if (!pass) {
        error.textContent = 'Informe a senha.';
        input.focus();
        return;
      }
      submit.disabled = true;
      submit.textContent = 'Verificando...';
      error.textContent = '';
      try {
        const { response, payload } = await request('/admin/ping', {}, pass);
        if (!response.ok || !payload || payload.ok === false) {
          throw new Error((payload && payload.error) || 'senha inválida');
        }
        sessionStorage.setItem(KEY, pass);
        unlocked = true;
        renderMain();
        await load(true);
      } catch (err) {
        sessionStorage.removeItem(KEY);
        unlocked = false;
        error.textContent = accessError(err);
        submit.disabled = false;
        submit.textContent = 'Entrar';
        input.select();
      }
    }
  }

  function renderLock(message) {
    refs = null;
    lockScreen(message);
  }

  function renderMain() {
    refs = null;
    clear(pane);
    const root = h('div', 'hx-admin', '');
    const head = h('div', 'hx-admin-head', '');
    const heading = h('div', 'hx-admin-heading', '');
    heading.append(
      h('h2', 'hx-admin-title', 'Administração'),
      h('div', 'hx-admin-sub', 'Containers Docker do Pi · acesso pela LAN')
    );
    const actions = h('div', 'hx-admin-head-actions', '');
    const refresh = btn('Atualizar', '', () => load(true));
    const logout = btn('Sair', '', () => {
      sessionStorage.removeItem(KEY);
      unlocked = false;
      renderLock('Sessão encerrada.');
    });
    actions.append(refresh, logout);
    head.append(heading, actions);

    const summary = h('div', 'hx-admin-summary', '');
    const toolbar = h('div', 'hx-admin-toolbar', '');
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'hx-input hx-admin-search';
    search.placeholder = 'Buscar serviço, imagem...';
    search.setAttribute('aria-label', 'Buscar serviço');
    search.addEventListener('input', () => {
      query = search.value.trim().toLowerCase();
      renderList();
    });
    const select = document.createElement('select');
    select.className = 'hx-select hx-admin-filter';
    select.setAttribute('aria-label', 'Filtrar serviços');
    for (const [value, label] of [
      ['all', 'Todos'],
      ['running', 'Rodando'],
      ['stopped', 'Parados'],
      ['problem', 'Com problema'],
    ]) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      select.appendChild(option);
    }
    select.addEventListener('change', () => {
      filter = select.value;
      renderList();
    });
    const updated = h('span', 'hx-admin-updated', 'carregando...');
    toolbar.append(search, select, updated);

    const error = h('div', 'hx-admin-error', '');
    error.hidden = true;
    const list = h('div', 'hx-admin-list', '');
    const auditTitle = h('h3', 'hx-admin-section-title', 'Ações recentes');
    const audit = h('div', 'hx-admin-audit', '');
    root.append(head, summary, toolbar, error, list, auditTitle, audit);
    pane.appendChild(root);

    refs = { root, summary, toolbar, search, select, updated, error, list, audit, refresh };
    load(false);
  }

  function filteredServices() {
    return services.filter((service) => {
      if (filter === 'running' && service.state !== 'running') return false;
      if (filter === 'stopped' && service.state === 'running') return false;
      if (filter === 'problem' && !(service.health === 'unhealthy' || service.state === 'restarting')) return false;
      if (!query) return true;
      const text = [service.name, service.service, service.image, service.status, service.state]
        .join(' ')
        .toLowerCase();
      return text.includes(query);
    });
  }

  function renderSummary() {
    if (!refs) return;
    const counts = servicesSummary(services);
    clear(refs.summary);
    for (const [tone, label, value] of [
      ['ok', 'Rodando', counts.running],
      ['stopped', 'Parados', counts.stopped],
      ['bad', 'Com problema', counts.unhealthy],
      ['neutral', 'Total', counts.total],
    ]) {
      const item = h('div', 'hx-admin-stat', '');
      item.append(
        h('span', 'hx-admin-stat-value hx-admin-tone--' + tone, String(value)),
        h('span', 'hx-admin-stat-label', label)
      );
      refs.summary.appendChild(item);
    }
  }

  function renderList() {
    if (!refs) return;
    clear(refs.list);
    const items = filteredServices();
    if (!items.length) {
      refs.list.appendChild(h('div', 'hx-admin-empty', 'Nenhum serviço encontrado.'));
      return;
    }
    for (const service of items) {
      const row = h('div', 'hx-admin-row', '');
      const main = h('div', 'hx-admin-main', '');
      const nameLine = h('div', 'hx-admin-name', '');
      const dot = h('span', 'hx-admin-dot hx-admin-tone--' + stateTone(service), '');
      dot.setAttribute('aria-hidden', 'true');
      nameLine.appendChild(dot);
      nameLine.appendChild(h('span', '', service.name));
      if (service.critical) nameLine.appendChild(h('span', 'hx-admin-badge', 'crítico'));
      if (service.protected) nameLine.appendChild(h('span', 'hx-admin-badge hx-admin-badge--lock', 'protegido'));
      const meta = h('div', 'hx-admin-meta', '');
      meta.append(
        h('span', '', service.service),
        h('span', 'hx-admin-sep', '·'),
        h('span', 'hx-admin-tone--' + stateTone(service), stateLabel(service)),
        h('span', 'hx-admin-sep', '·'),
        h('span', '', service.status || 'sem status')
      );
      const detail = h('div', 'hx-admin-meta hx-admin-meta--muted', '');
      detail.append(h('span', '', service.image || 'imagem desconhecida'));
      if (service.ports && service.ports.length) {
        detail.append(h('span', 'hx-admin-sep', '·'));
        detail.append(h('span', '', service.ports.join(', ')));
      }
      main.append(nameLine, meta, detail);

      const actions = h('div', 'hx-admin-actions', '');
      const busy = busyService === service.service;
      if (service.can_start) {
        const start = btn('Iniciar', 'hx-admin-ok', () => confirmAction(service, 'start'));
        start.disabled = busy;
        actions.appendChild(start);
      }
      if (service.can_stop) {
        const stop = btn('Parar', 'hx-admin-danger', () => confirmAction(service, 'stop'));
        stop.disabled = busy;
        actions.appendChild(stop);
      }
      if (service.can_restart) {
        const restart = btn('Reiniciar', '', () => confirmAction(service, 'restart'));
        restart.disabled = busy;
        actions.appendChild(restart);
      }
      if (busy) actions.appendChild(h('span', 'hx-admin-busy', 'aguarde...'));
      if (!actions.childNodes.length) actions.appendChild(h('span', 'hx-admin-busy', 'sem ações'));
      row.append(main, actions);
      refs.list.appendChild(row);
    }
  }

  function renderAudit() {
    if (!refs) return;
    clear(refs.audit);
    if (!auditItems.length) {
      refs.audit.appendChild(h('div', 'hx-admin-empty', 'Nenhuma ação registrada.'));
      return;
    }
    for (const item of auditItems) {
      const row = h('div', 'hx-admin-audit-row', '');
      const when = h('span', 'hx-admin-audit-time', formatTime(item.ts));
      let text = '';
      if (item.event === 'auth_failed') {
        text = 'Senha inválida';
      } else if (item.event === 'action') {
        const labels = { start: 'Iniciar', stop: 'Parar', restart: 'Reiniciar' };
        text = `${labels[item.action] || item.action} ${item.service}`;
      } else {
        text = item.event || 'evento';
      }
      const result = h(
        'span',
        'hx-admin-audit-result ' + (item.result === 'error' ? 'hx-admin-tone--bad' : 'hx-admin-tone--ok'),
        item.result === 'error' ? 'falhou' : (item.result ? 'ok' : '')
      );
      row.append(when, h('span', 'hx-admin-audit-text', text), result);
      refs.audit.appendChild(row);
    }
  }

  function renderError(message) {
    if (!refs) return;
    lastError = message || '';
    refs.error.hidden = !lastError;
    refs.error.textContent = lastError;
  }

  function renderData() {
    if (!refs) return;
    renderSummary();
    renderList();
    renderAudit();
    refs.updated.textContent = updatedAt
      ? 'atualizado ' + new Date(updatedAt).toLocaleTimeString()
      : 'atualizando...';
    refs.updated.title = updatedAt || '';
  }

  async function load(force) {
    if (loading || !unlocked) return;
    loading = true;
    if (force && refs && refs.refresh) {
      refs.refresh.disabled = true;
      refs.refresh.textContent = 'Atualizando...';
    }
    try {
      const [servicesPayload, auditPayload] = await Promise.all([
        api('/admin/services'),
        api('/admin/audit?limit=8'),
      ]);
      services = servicesPayload.services || [];
      auditItems = auditPayload.items || [];
      updatedAt = servicesPayload.generated_at || new Date().toISOString();
      renderError('');
      renderData();
    } catch (error) {
      if (unlocked) renderError(accessError(error));
    } finally {
      loading = false;
      if (refs && refs.refresh) {
        refs.refresh.disabled = false;
        refs.refresh.textContent = 'Atualizar';
      }
    }
  }

  async function askConfirm(service, action) {
    const labels = { start: 'Iniciar', stop: 'Parar', restart: 'Reiniciar' };
    const label = labels[action] || action;
    const critical = !!service.critical;
    return new Promise((resolve) => {
      const backdrop = h('div', 'hx-backdrop', '');
      const shell = h('div', 'hx-shell hx-admin-dialog', '');
      shell.setAttribute('role', 'dialog');
      shell.setAttribute('aria-modal', 'true');
      shell.setAttribute('aria-labelledby', 'hx-admin-dialog-title');
      shell.tabIndex = -1;

      const head = h('div', 'hx-head', '');
      const title = h('h2', 'hx-head-title', `${label} ${service.name}`);
      title.id = 'hx-admin-dialog-title';
      const close = btn('Fechar', '', () => finish(false));
      head.append(title, close);

      const body = h('div', 'hx-body', '');
      const message = h(
        'p',
        'hx-admin-dialog-text',
        action === 'stop'
          ? 'O container será parado. Ele pode ficar indisponível até você iniciá-lo novamente.'
          : action === 'restart'
            ? 'O container será reiniciado. Haverá uma breve indisponibilidade.'
            : 'O container será iniciado.'
      );
      body.appendChild(message);
      if (critical) {
        body.appendChild(h(
          'div',
          'hx-admin-dialog-warn',
          'Serviço crítico: outros serviços ou a própria dashboard podem depender dele.'
        ));
      }
      let input = null;
      if (critical) {
        const field = h('div', 'hx-admin-dialog-field', '');
        field.appendChild(h('label', '', `Digite ${service.service} para confirmar`));
        input = document.createElement('input');
        input.type = 'text';
        input.className = 'hx-input';
        input.autocomplete = 'off';
        input.placeholder = service.service;
        field.appendChild(input);
        body.appendChild(field);
      }
      const error = h('div', 'hx-error', '');
      body.appendChild(error);

      const actions = h('div', 'hx-admin-dialog-actions', '');
      const cancel = btn('Cancelar', '', () => finish(false));
      const confirm = btn(label, action === 'stop' ? 'hx-admin-danger' : 'hx-btn-primary', () => {
        if (critical && input.value.trim() !== service.service) {
          error.textContent = `Digite exatamente "${service.service}".`;
          input.focus();
          return;
        }
        finish(true);
      });
      actions.append(cancel, confirm);
      shell.append(head, body, actions);
      document.body.append(backdrop, shell);

      const previous = document.activeElement;
      const onKey = (event) => {
        if (event.key === 'Escape') {
          event.preventDefault();
          finish(false);
        }
      };
      document.addEventListener('keydown', onKey);
      backdrop.addEventListener('click', () => finish(false));
      if (input) input.focus();
      else confirm.focus();

      function finish(value) {
        document.removeEventListener('keydown', onKey);
        backdrop.remove();
        shell.remove();
        if (previous && previous.isConnected && typeof previous.focus === 'function') {
          previous.focus();
        }
        resolve(value);
      }
    });
  }

  async function performAction(service, action) {
    const ok = await askConfirm(service, action);
    if (!ok) return;
    busyService = service.service;
    renderList();
    try {
      await api(
        '/admin/services/' + encodeURIComponent(service.service) + '/' + action,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ confirm: service.service }),
        }
      );
      const labels = { start: 'iniciado', stop: 'parado', restart: 'reiniciado' };
      toast(`${service.name} ${labels[action] || action}.`);
      await new Promise((resolve) => setTimeout(resolve, 800));
      await load(true);
      setTimeout(() => { if (unlocked) load(true); }, 3500);
    } catch (error) {
      toast('Falha: ' + accessError(error), false);
      await load(true);
    } finally {
      busyService = '';
      renderList();
    }
  }

  function confirmAction(service, action) {
    performAction(service, action);
  }

  function activate() {
    if (unlocked) {
      load(false);
      return;
    }
    const stored = sessionStorage.getItem(KEY);
    if (stored) {
      (async () => {
        try {
          const { response, payload } = await request('/admin/ping', {}, stored);
          if (!response.ok || !payload || payload.ok === false) {
            throw new Error((payload && payload.error) || 'senha inválida');
          }
          unlocked = true;
          renderMain();
          await load(true);
        } catch (error) {
          sessionStorage.removeItem(KEY);
          unlocked = false;
          renderLock(accessError(error));
        }
      })();
      return;
    }
    renderLock('');
  }

  renderLock('');
  setInterval(() => {
    if (!pane.hidden && unlocked && !loading && document.visibilityState === 'visible') {
      load(false);
    }
  }, REFRESH_MS);

  return { activate };
}
