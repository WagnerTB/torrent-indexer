import { MEDIA } from '../shared.js';

export const STATUS = {
  error: { label: 'Erro', color: '#f87171' },
  downloading: { label: 'Baixando', color: '#60a5fa' },
  queued: { label: 'Na fila', color: '#fbbf24' },
  searching: { label: 'Procurando', color: '#c084fc' },
  request_pending: { label: 'Pendente no Seerr', color: '#fbbf24' },
  request_approved: { label: 'Aprovado no Seerr', color: '#60a5fa' },
  request_declined: { label: 'Recusado no Seerr', color: '#f87171' },
  request_failed: { label: 'Falhou no Seerr', color: '#f87171' },
  request_completed: { label: 'Concluído no Seerr', color: '#4ade80' },
  requested: { label: 'Pedido', color: '#fbbf24' },
  downloaded: { label: 'Baixado', color: '#4ade80' },
  partial: { label: 'Parcial', color: '#2dd4bf' },
  missing: { label: 'Sem arquivo', color: '#a1a1aa' },
  removed: { label: 'Removido', color: '#a1a1aa' },
  archived: { label: 'Arquivado', color: '#c084fc' },
  restored: { label: 'Restaurado', color: '#60a5fa' },
};

export const SOURCE_LABELS = {
  seerr: 'Seerr',
  manual: 'Manual',
  backfill: 'Importado do Sonarr',
  arr: 'Radarr/Sonarr',
};

export function displayMessage(value) {
  return String(value || '')
    .replace(/\bconcluido\b/gi, 'concluído')
    .replace(/\bnao\b/gi, 'não')
    .trim();
}

export function profileLabel(value) {
  return displayMessage(value)
    .replace(/Anima\?\?o/g, 'Animação')
    .replace(/S\?ries/g, 'Séries')
    .replace(/Japon\?s/g, 'Japonês');
}

export function messageMatchesStatus(msg, status) {
  if (!msg) return false;
  if (/^pedido conclu/i.test(msg)) return status === 'request_completed';
  if (/^pedido recusado/i.test(msg)) return status === 'request_declined';
  if (/^falha ao enviar/i.test(msg)) return status === 'request_failed';
  return true;
}

export function statusMessageFor(item) {
  const msg = displayMessage(item.statusMessage);
  return msg && messageMatchesStatus(msg, statusOf(item)) ? msg : '';
}

export const EVENT_LABELS = {
  grabbed: 'Busca iniciada',
  downloadfolderimported: 'Importado',
  downloadfailed: 'Download falhou',
  importfailed: 'Importação falhou',
  moviefiledeleted: 'Arquivo removido',
  episodefiledeleted: 'Arquivo removido',
  renamed: 'Renomeado',
};

export async function ordersApi(path, method = 'GET', body) {
  const res = await fetch(MEDIA + path, {
    method,
    cache: 'no-store',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let payload = null;
  try { payload = await res.json(); } catch (e) { payload = null; }
  if (!res.ok || !payload || payload.ok === false) {
    throw new Error((payload && payload.error) || `${method} ${path} -> ${res.status}`);
  }
  return payload;
}

export function itemLabel(item) {
  const year = item.year ? ` (${item.year})` : '';
  return `${item.title || 'Sem título'}${year}`;
}

export const pad2 = (value) => String(Number(value) || 0).padStart(2, '0');

export function epLabel(item) {
  const se = 'S' + pad2(item.season) + 'E' + pad2(item.episode);
  return item.absoluteEpisode ? `${se} • #${item.absoluteEpisode}` : se;
}

export function statusLabel(key) {
  return (STATUS[key] && STATUS[key].label) || key || '';
}

export function historyLabel(item) {
  if (item.kind === 'episode') {
    return `${item.title || 'Série'} ${epLabel(item)} ${item.episodeTitle || ''}`.trim();
  }
  return itemLabel(item);
}

export function statusOf(item) {
  const raw = String(item.status || '').toLowerCase();
  if (STATUS[raw]) return raw;
  return item.hasFile ? 'downloaded' : 'missing';
}

export function eventLabel(event) {
  if (!event || !event.eventType) return '';
  const key = String(event.eventType).toLowerCase();
  return EVENT_LABELS[key] || event.eventType;
}

export function seriesTypeLabel(type) {
  if (type === 'anime') return 'Anime';
  if (type === 'daily') return 'Diário';
  return 'Padrão';
}
