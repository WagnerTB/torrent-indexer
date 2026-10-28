import { h, registerTabCount } from './shared.js';
import { injectStyles } from './styles.js';
import { initOrders } from './orders/index.js';
import { initSubs } from './subs.js';
import { initStorage } from './storage.js';

export function initNav() {
  injectStyles();

  const baseTitle = document.title || 'Casa';
  const tabs = [
    { name: 'home', label: 'Início', href: './' },
    { name: 'pedidos', label: 'Pedidos', href: '?tab=pedidos' },
    { name: 'legendas', label: 'Legendas', href: '?tab=legendas' },
  ];

  const nav = h('nav', '', '');
  nav.id = 'hx-nav';
  nav.setAttribute('aria-label', 'Seções do painel');
  const navInner = h('div', '', '');
  navInner.id = 'hx-nav-inner';
  navInner.setAttribute('role', 'tablist');
  nav.appendChild(navInner);

  const tabButtons = {};
  const tabCounts = {};
  for (const def of tabs) {
    const a = h('a', 'hx-nav-tab', '');
    a.id = 'hx-nav-' + def.name;
    a.href = def.href;
    a.dataset.tab = def.name;
    a.setAttribute('role', 'tab');
    a.setAttribute('aria-selected', 'false');
    if (def.name !== 'home') a.setAttribute('aria-controls', 'hx-pane-' + def.name);
    a.appendChild(h('span', '', def.label));
    if (def.name !== 'home') {
      const count = h('span', 'hx-nav-count', '');
      count.hidden = true;
      a.appendChild(count);
      tabCounts[def.name] = count;
    }
    tabButtons[def.name] = a;
    navInner.appendChild(a);
  }

  const view = h('div', '', '');
  view.id = 'hx-view';
  view.hidden = true;
  const panes = {};
  for (const name of ['pedidos', 'legendas']) {
    const pane = h('section', 'hx-pane', '');
    pane.id = 'hx-pane-' + name;
    pane.setAttribute('role', 'tabpanel');
    pane.setAttribute('aria-labelledby', 'hx-nav-' + name);
    pane.hidden = true;
    panes[name] = pane;
    view.appendChild(pane);
  }

  registerTabCount((name, value) => {
    const el = tabCounts[name];
    if (!el) return;
    const count = Number(value) || 0;
    el.textContent = String(count);
    el.hidden = count <= 0;
  });

  const orders = initOrders(panes.pedidos);
  const legendas = initSubs(panes.legendas);
  const storage = initStorage();
  const instances = { pedidos: orders, legendas };

  let active = 'home';
  let mounted = false;

  function readTab() {
    try {
      const value = new URLSearchParams(location.search).get('tab');
      return value === 'pedidos' || value === 'legendas' ? value : 'home';
    } catch (e) {
      return 'home';
    }
  }

  function urlFor(name) {
    const url = new URL(location.href);
    if (name === 'home') url.searchParams.delete('tab');
    else url.searchParams.set('tab', name);
    return url.pathname + url.search + url.hash;
  }

  function findContainer() {
    return document.querySelector('#inner_wrapper > .container') || document.querySelector('.container');
  }

  function applyVisibility() {
    const isHome = active === 'home';
    view.hidden = isHome;
    panes.pedidos.hidden = active !== 'pedidos';
    panes.legendas.hidden = active !== 'legendas';
    document.body.classList.toggle('hx-tab-active', !isHome);
    for (const def of tabs) {
      const selected = def.name === active;
      tabButtons[def.name].setAttribute('aria-selected', selected ? 'true' : 'false');
      tabButtons[def.name].tabIndex = selected ? 0 : -1;
    }
    const label = (tabs.find((t) => t.name === active) || tabs[0]).label;
    document.title = isHome ? baseTitle : `${label} — ${baseTitle}`;
  }

  function activate(name, push, focus) {
    if (name !== 'home' && !instances[name]) name = 'home';
    active = name;
    applyVisibility();
    const wrapper = document.querySelector('#inner_wrapper');
    if (wrapper) wrapper.scrollTop = 0;
    if (push) {
      const target = urlFor(name);
      const current = location.pathname + location.search + location.hash;
      if (target !== current) history.pushState({ tab: name }, '', target);
    }
    if (focus && tabButtons[name]) tabButtons[name].focus();
    if (instances[name]) instances[name].activate();
    if (name === 'home') storage.refresh();
  }

  function ensureMounted() {
    const container = findContainer();
    if (!container) {
      if (document.body.contains(nav)) nav.remove();
      document.body.classList.remove('hx-has-nav');
      return false;
    }
    if (!document.body.contains(nav)) document.body.appendChild(nav);
    if (view.parentElement !== container) container.appendChild(view);
    const rect = container.getBoundingClientRect();
    if (rect.width > 0) {
      navInner.style.width = Math.round(rect.width) + 'px';
      navInner.style.maxWidth = 'none';
      navInner.style.marginLeft = Math.round(rect.left) + 'px';
      navInner.style.marginRight = '0';
    }
    document.body.classList.add('hx-has-nav');
    if (!mounted) {
      mounted = true;
      activate(active, false, false);
    } else {
      applyVisibility();
    }
    return true;
  }

  for (const def of tabs) {
    const a = tabButtons[def.name];
    a.addEventListener('click', (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      activate(def.name, true, false);
    });
  }

  navInner.addEventListener('keydown', (event) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const names = tabs.map((t) => t.name);
    const current = names.indexOf(active);
    const next = event.key === 'ArrowRight'
      ? (current + 1) % names.length
      : (current - 1 + names.length) % names.length;
    activate(names[next], true, true);
  });

  window.addEventListener('popstate', () => {
    const next = readTab();
    if (next !== active) activate(next, false, false);
  });

  active = readTab();
  applyVisibility();
  ensureMounted();
  orders.updateCount();
  setInterval(() => {
    if (document.visibilityState === 'visible') orders.updateCount();
  }, 300000);
  setInterval(() => {
    if (active === 'pedidos' && document.visibilityState === 'visible') orders.refreshSilent();
  }, 60000);

  let scheduled = false;
  const observer = new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      ensureMounted();
    });
  });
  observer.observe(document.body, { childList: true, subtree: true });
  window.addEventListener('resize', () => requestAnimationFrame(() => ensureMounted()));

  const retry = setInterval(() => {
    if (ensureMounted()) clearInterval(retry);
  }, 800);
}
