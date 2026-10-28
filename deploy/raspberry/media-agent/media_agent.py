#!/usr/bin/env python3
import ipaddress
import json
import os
import shutil
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN_PORT = int(os.getenv("LISTEN_PORT", "8097"))
LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")
ALLOWED_NETWORKS = [
    ipaddress.ip_network(value.strip())
    for value in os.getenv(
        "ALLOWED_NETWORKS",
        "127.0.0.0/8,::1/128",
    ).split(",")
    if value.strip()
]

OS_API_KEY = os.getenv("OS_API_KEY", "")
BAZARR_CONFIG = os.getenv("BAZARR_CONFIG", "/bazarr/config.yaml")
BAZARR_URL = os.getenv("BAZARR_URL", "http://127.0.0.1:6767").rstrip("/")
BAZARR_KEY_FILE = os.getenv("BAZARR_KEY_FILE", "/app/.bazarr_key")

RADARR_URL = os.getenv("RADARR_URL", "http://127.0.0.1:7878").rstrip("/")
SONARR_URL = os.getenv("SONARR_URL", "http://127.0.0.1:8989").rstrip("/")
RADARR_CONFIG = os.getenv("RADARR_CONFIG", "/radarr/config.xml")
SONARR_CONFIG = os.getenv("SONARR_CONFIG", "/sonarr/config.xml")
RADARR_DUBBED_PROFILE = int(os.getenv("RADARR_DUBBED_PROFILE", "8"))
SONARR_DUBBED_PROFILE = int(os.getenv("SONARR_DUBBED_PROFILE", "9"))
RADARR_ORIGINAL_PROFILE = int(os.getenv("RADARR_ORIGINAL_PROFILE", "7"))
SONARR_ORIGINAL_PROFILE = int(os.getenv("SONARR_ORIGINAL_PROFILE", "7"))

SEERR_URL = os.getenv("SEERR_URL", "http://127.0.0.1:5055").rstrip("/")
SEERR_CONFIG = os.getenv("SEERR_CONFIG", "/seerr/settings.json")
SEERR_TIMEOUT = int(os.getenv("SEERR_TIMEOUT_SECONDS", "15"))

STATE_DIR = os.getenv("STATE_DIR", "/state")
STATE_DB = os.path.join(STATE_DIR, "requests.db")
STORAGE_CONFIG = os.getenv("STORAGE_CONFIG", "").strip()

_os_token = None
_os_token_ts = 0.0


def os_credentials():
    user = password = None
    section = False
    try:
        with open(BAZARR_CONFIG, encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("opensubtitlescom:"):
                    section = True
                    continue
                if section and line and not line.startswith(" "):
                    break
                if section and line.startswith("  username:"):
                    user = line.split(":", 1)[1].strip().strip("'\"")
                if section and line.startswith("  password:"):
                    password = line.split(":", 1)[1].strip().strip("'\"")
    except OSError:
        return None, None
    return user, password


def os_request(url, data=None, token=None):
    headers = {
        "Api-Key": OS_API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "Bazarr/1.5.6",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    body = json.dumps(data).encode() if data is not None else None
    method = "POST" if data is not None else "GET"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def os_login(force=False):
    global _os_token, _os_token_ts
    if not force and _os_token and (time.time() - _os_token_ts) < 3000:
        return _os_token
    user, password = os_credentials()
    if not user or not password:
        raise RuntimeError("credenciais do OpenSubtitles não encontradas no config do Bazarr")
    payload = os_request(
        "https://api.opensubtitles.com/api/v1/login",
        {"username": user, "password": password},
    )
    token = payload.get("token")
    if not token:
        raise RuntimeError("login do OpenSubtitles sem token")
    _os_token = token
    _os_token_ts = time.time()
    return token


def os_quota():
    try:
        token = os_login()
        try:
            payload = os_request("https://api.opensubtitles.com/api/v1/infos/user", token=token)
        except urllib.error.HTTPError as error:
            if error.code != 401:
                raise
            token = os_login(force=True)
            payload = os_request("https://api.opensubtitles.com/api/v1/infos/user", token=token)
        return {"ok": True, "data": payload.get("data", payload)}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def arr_key(path):
    try:
        root = ET.parse(path).getroot()
        return (root.findtext("ApiKey") or "").strip()
    except Exception:
        return ""


def bazarr_api_key():
    try:
        with open(BAZARR_KEY_FILE, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def bazarr_proxy(path, method="GET"):
    if not path.startswith("/api/"):
        return 400, "application/json", b'{"error":"invalid path"}'
    key = bazarr_api_key()
    if not key:
        return 500, "application/json", b'{"error":"missing Bazarr API key"}'
    request = urllib.request.Request(
        BAZARR_URL + path,
        headers={"X-API-KEY": key},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content_type = response.headers.get("Content-Type", "application/json")
            return response.status, content_type, response.read()
    except urllib.error.HTTPError as error:
        content_type = error.headers.get("Content-Type", "application/json")
        return error.code, content_type, error.read()
    except Exception as error:
        return 500, "application/json", json.dumps({"error": str(error)}).encode()


def arr_request(base, key, path, method="GET", payload=None, timeout=90):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"X-Api-Key": key}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode()
        return json.loads(raw) if raw else None


def seerr_key():
    try:
        with open(SEERR_CONFIG, encoding="utf-8") as handle:
            data = json.load(handle)
        return str(((data.get("main") or {}).get("apiKey") or "")).strip()
    except Exception:
        return ""


def seerr_request(path, method="GET", payload=None):
    key = seerr_key()
    if not key:
        raise RuntimeError("API key do Seerr não encontrada")
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"X-Api-Key": key}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(SEERR_URL + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=SEERR_TIMEOUT) as response:
        raw = response.read().decode()
        return json.loads(raw) if raw else None


REQUEST_STATUS_LABELS = {
    1: "Pendente",
    2: "Aprovado",
    3: "Recusado",
    4: "Falhou",
    5: "Concluído",
}
MEDIA_STATUS_LABELS = {
    1: "Desconhecido",
    2: "Pendente",
    3: "Processando",
    4: "Parcial",
    5: "Disponível",
    6: "Removido",
    7: "Bloqueado",
}
SEERR_REQUEST_STATUS = {
    1: "request_pending",
    2: "request_approved",
    3: "request_declined",
    4: "request_failed",
}
_SEERR_CACHE_TTL = 20
_SEERR_DETAILS_TTL = 300
_seerr_cache = {"ts": 0.0, "infos": [], "error": ""}
_seerr_details = {}


def _seerr_info(request):
    media = request.get("media") or {}
    status = _as_int(request.get("status")) or 1
    media_status = _as_int(media.get("status")) or 1
    return {
        "type": request.get("type") or media.get("mediaType") or "",
        "requestId": request.get("id"),
        "status": status,
        "statusLabel": REQUEST_STATUS_LABELS.get(status, str(status)),
        "mediaStatus": media_status,
        "mediaStatusLabel": MEDIA_STATUS_LABELS.get(media_status, str(media_status)),
        "profileName": request.get("profileName") or "",
        "profileId": request.get("profileId"),
        "requestedBy": (request.get("requestedBy") or {}).get("displayName") or "",
        "createdAt": request.get("createdAt") or "",
        "updatedAt": request.get("updatedAt") or "",
        "seasonCount": request.get("seasonCount") or 0,
        "is4k": bool(request.get("is4k")),
        "tmdbId": _as_int(media.get("tmdbId")),
        "tvdbId": _as_int(media.get("tvdbId")),
        "externalServiceId": _as_int(media.get("externalServiceId")),
    }


def seerr_infos():
    now = time.time()
    if now - _seerr_cache["ts"] < _SEERR_CACHE_TTL:
        return _seerr_cache["infos"], _seerr_cache["error"]
    error = ""
    infos = []
    try:
        page_size = 100
        skip = 0
        while True:
            payload = seerr_request(f"/api/v1/request?take={page_size}&skip={skip}&filter=all&sort=added") or {}
            batch = payload.get("results") or []
            infos.extend(_seerr_info(item) for item in batch)
            if len(batch) < page_size:
                break
            skip += page_size
            if skip >= 1000:
                break
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    _seerr_cache.update({"ts": now, "infos": infos, "error": error})
    return infos, error


def _seerr_detail(info):
    kind = "movie" if info.get("type") == "movie" else "series"
    ident = info.get("tmdbId") if kind == "movie" else info.get("tvdbId")
    if not ident:
        return {}
    cache_key = (kind, ident)
    now = time.time()
    cached = _seerr_details.get(cache_key)
    if cached and now - cached[0] < _SEERR_DETAILS_TTL:
        return cached[1]
    detail = {}
    try:
        path = f"/api/v1/movie/{ident}" if kind == "movie" else f"/api/v1/tv/{ident}"
        data = seerr_request(path) or {}
        raw_date = str(data.get("releaseDate") or data.get("firstAirDate") or "")
        detail = {
            "title": data.get("title") or data.get("name") or "",
            "year": _as_int(raw_date[:4]) if raw_date else None,
        }
    except Exception:
        detail = {}
    _seerr_details[cache_key] = (now, detail)
    return detail


def _seerr_media_key(info):
    if info.get("is4k"):
        return None
    if info.get("type") == "movie" and info.get("tmdbId"):
        return ("movie", info["tmdbId"])
    if info.get("type") in ("tv", "series") and info.get("tvdbId"):
        return ("series", info["tvdbId"])
    return None


def _merge_seerr(items, infos):
    items_by_key = {}
    for item in items:
        if item["kind"] == "movie" and item.get("tmdbId"):
            items_by_key[("movie", item["tmdbId"])] = item
        elif item["kind"] == "series" and item.get("tvdbId"):
            items_by_key[("series", item["tvdbId"])] = item

    priority = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}
    ordered = sorted(infos, key=lambda info: (priority.get(info.get("status"), 9), info.get("updatedAt") or ""))
    used = set()
    for info in ordered:
        key = _seerr_media_key(info)
        if not key or key in used:
            continue
        used.add(key)
        item = items_by_key.get(key)
        if item is not None:
            item["seerr"] = info
            continue
        status_key = SEERR_REQUEST_STATUS.get(info.get("status"))
        if not status_key:
            continue
        detail = _seerr_detail(info)
        entry = {
            "kind": "movie" if info.get("type") == "movie" else "series",
            "id": None,
            "title": detail.get("title") or f"Pedido Seerr #{info.get('requestId')}",
            "year": detail.get("year"),
            "hasFile": False,
            "profileId": info.get("profileId"),
            "monitored": True,
            "seerrOnly": True,
            "status": status_key,
            "seerr": info,
        }
        if info.get("status") == 3:
            entry["errorMessage"] = "Pedido recusado no Seerr"
        elif info.get("status") == 4:
            entry["errorMessage"] = "Falha ao enviar o pedido ao Radarr/Sonarr"
        items.append(entry)


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


REQUEST_DONE_STATUSES = {"downloaded", "imported", "request_completed"}

_db_lock = threading.Lock()
_reconcile_lock = threading.Lock()
_reconcile_cache = {"ts": 0.0}
_episode_context_cache = {"ts": 0.0, "data": None}
_series_episode_cache = {}


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _iso_ago(seconds):
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _recent(value, seconds=600):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - parsed).total_seconds() < seconds
    except (TypeError, ValueError):
        return False


def _json_load(value):
    if not value:
        return {}
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}


def _format_bytes(value):
    try:
        size = float(value or 0)
    except (TypeError, ValueError):
        size = 0.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit in ("B", "KB", "MB"):
                return f"{size:.0f} {unit}"
            text = f"{size:.1f}".rstrip("0").rstrip(".")
            return f"{text or '0'} {unit}"
        size /= 1024
    return "0 B"


def _storage_entries():
    if not STORAGE_CONFIG:
        return []
    try:
        data = json.loads(STORAGE_CONFIG)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def storage_payload():
    items = []
    for entry in _storage_entries():
        if not isinstance(entry, dict):
            continue
        parts = []
        for part in entry.get("parts") or []:
            if not isinstance(part, dict):
                continue
            path = str(part.get("path") or "").strip()
            if not path:
                continue
            try:
                usage = shutil.disk_usage(path)
            except OSError:
                continue
            total = int(usage.total)
            used = int(usage.used)
            free = int(usage.free)
            parts.append(
                {
                    "label": str(part.get("label") or path),
                    "total": total,
                    "used": used,
                    "free": free,
                    "percent": round(used / total * 100) if total else 0,
                    "totalLabel": _format_bytes(total),
                    "usedLabel": _format_bytes(used),
                    "freeLabel": _format_bytes(free),
                }
            )
        if not parts:
            continue
        total = sum(part["total"] for part in parts)
        used = sum(part["used"] for part in parts)
        free = sum(part["free"] for part in parts)
        items.append(
            {
                "id": str(entry.get("id") or entry.get("label") or "storage"),
                "label": str(entry.get("label") or "Armazenamento"),
                "kind": str(entry.get("kind") or ""),
                "total": total,
                "used": used,
                "free": free,
                "percent": round(used / total * 100) if total else 0,
                "totalLabel": _format_bytes(total),
                "usedLabel": _format_bytes(used),
                "freeLabel": _format_bytes(free),
                "parts": parts,
            }
        )
    return {"ok": True, "items": items, "generatedAt": _now_iso()}


def _db_connect():
    os.makedirs(STATE_DIR, exist_ok=True)
    conn = sqlite3.connect(STATE_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


def _db_init():
    with _db_lock:
        conn = _db_connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS requests (
                    key TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    media_kind TEXT,
                    arr_id INTEGER,
                    series_id INTEGER,
                    episode_id INTEGER,
                    season INTEGER,
                    episode INTEGER,
                    absolute_episode INTEGER,
                    tmdb_id INTEGER,
                    tvdb_id INTEGER,
                    title TEXT,
                    episode_title TEXT,
                    year INTEGER,
                    profile_id INTEGER,
                    profile_name TEXT,
                    root_folder TEXT,
                    source TEXT,
                    seerr_request_id INTEGER,
                    seerr_status INTEGER,
                    seerr_media_status INTEGER,
                    requested_by TEXT,
                    requested_at TEXT,
                    first_seen_at TEXT,
                    last_seen_at TEXT,
                    last_checked_at TEXT,
                    status TEXT,
                    status_message TEXT,
                    completed_at TEXT,
                    hidden_at TEXT,
                    meta TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    at TEXT NOT NULL,
                    status TEXT,
                    message TEXT,
                    source TEXT,
                    meta TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
                CREATE INDEX IF NOT EXISTS idx_requests_hidden ON requests(hidden_at);
                CREATE INDEX IF NOT EXISTS idx_requests_series ON requests(series_id);
                CREATE INDEX IF NOT EXISTS idx_requests_kind ON requests(kind);
                CREATE INDEX IF NOT EXISTS idx_events_key ON events(key, at);
                """
            )
            conn.commit()
        finally:
            conn.close()


def _db_rows(sql, params=()):
    conn = _db_connect()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _db_one(sql, params=()):
    rows = _db_rows(sql, params)
    return rows[0] if rows else None


TRACKED_FIELDS = [
    "kind",
    "media_kind",
    "arr_id",
    "series_id",
    "episode_id",
    "season",
    "episode",
    "absolute_episode",
    "tmdb_id",
    "tvdb_id",
    "title",
    "episode_title",
    "year",
    "profile_id",
    "profile_name",
    "root_folder",
    "source",
    "seerr_request_id",
    "seerr_status",
    "seerr_media_status",
    "requested_by",
    "requested_at",
    "first_seen_at",
    "last_seen_at",
    "last_checked_at",
    "status",
    "status_message",
    "completed_at",
    "hidden_at",
    "meta",
]


def _track_exists(key):
    row = _db_one("SELECT 1 FROM requests WHERE key = ?", (key,))
    return row is not None


def _track_upsert(record, status_authoritative=True):
    key = str(record.get("key") or "").strip()
    if not key:
        return None
    now = _now_iso()
    with _db_lock:
        conn = _db_connect()
        try:
            row = conn.execute("SELECT * FROM requests WHERE key = ?", (key,)).fetchone()

            def pick(name, default=None):
                if row is not None and record.get(name) in (None, ""):
                    if row[name] not in (None, ""):
                        return row[name]
                value = record.get(name)
                return value if value not in (None, "") else default

            status = pick("status")
            status_message = pick("status_message")
            if row is not None and not status_authoritative:
                status = row["status"]
                status_message = row["status_message"]
            elif row is not None and status != row["status"] and not str(record.get("status_message") or "").strip():
                status_message = ""

            merged = {name: pick(name) for name in TRACKED_FIELDS}
            merged["kind"] = merged["kind"] or "movie"
            merged["status"] = status
            merged["status_message"] = status_message
            if record.get("refresh_requested_at") and record.get("requested_at"):
                merged["requested_at"] = record.get("requested_at")
            else:
                merged["requested_at"] = (
                    (row["requested_at"] if row is not None and row["requested_at"] else None)
                    or record.get("requested_at")
                    or now
                )
            merged["first_seen_at"] = row["first_seen_at"] if row is not None else now
            merged["last_seen_at"] = now
            merged["last_checked_at"] = now
            merged["hidden_at"] = row["hidden_at"] if row is not None else record.get("hidden_at")

            completed_at = row["completed_at"] if row is not None else record.get("completed_at")
            if merged["status"] == "request_completed" and record.get("completed_from_seerr"):
                completed_at = record.get("completed_at") or None
            elif merged["status"] in REQUEST_DONE_STATUSES:
                completed_at = completed_at or record.get("completed_at") or now
            elif merged["status"] in ("missing", "error", "request_failed", "request_declined"):
                completed_at = None
            merged["completed_at"] = completed_at

            meta = record.get("meta")
            if meta is not None and not isinstance(meta, str):
                meta = json.dumps(meta, ensure_ascii=False)
            if not meta and row is not None:
                meta = row["meta"]
            merged["meta"] = meta

            if row is None:
                placeholders = ", ".join("?" for _ in TRACKED_FIELDS)
                conn.execute(
                    "INSERT INTO requests (key, " + ", ".join(TRACKED_FIELDS) + ") VALUES (?, " + placeholders + ")",
                    [key] + [merged[name] for name in TRACKED_FIELDS],
                )
            else:
                assignments = ", ".join(name + " = ?" for name in TRACKED_FIELDS)
                conn.execute(
                    "UPDATE requests SET " + assignments + " WHERE key = ?",
                    [merged[name] for name in TRACKED_FIELDS] + [key],
                )

            old_status = row["status"] if row is not None else None
            old_message = row["status_message"] if row is not None else None
            changed = row is None or (status is not None and status != old_status)
            if not changed and status in ("error", "request_failed") and status_message and status_message != old_message:
                changed = True
            if changed and merged["status"]:
                event_at = (record.get("event_at") or now) if row is None else now
                conn.execute(
                    "INSERT INTO events (key, at, status, message, source, meta) VALUES (?, ?, ?, ?, ?, ?)",
                    (key, event_at, merged["status"], merged["status_message"] or "", record.get("source") or merged["source"] or "", merged["meta"]),
                )
            conn.commit()
            return {"key": key, "inserted": row is None, "changed": changed}
        finally:
            conn.close()


def _seerr_key_string(info):
    media_kind = "movie" if info.get("type") == "movie" else "series"
    ident = info.get("tmdbId") if media_kind == "movie" else info.get("tvdbId")
    prefix = "tmdb" if media_kind == "movie" else "tvdb"
    if not ident:
        ident = "request-" + str(info.get("requestId") or "unknown")
        prefix = "req"
    key = f"{media_kind}:{prefix}:{ident}"
    if info.get("is4k"):
        key += ":4k"
    return key, media_kind


def _seerr_status_message(info):
    status = _as_int(info.get("status"))
    if status == 3:
        return "Pedido recusado no Seerr"
    if status == 4:
        return "Falha ao enviar o pedido ao Radarr/Sonarr"
    if status == 5:
        return "Pedido concluído no Seerr"
    return ""


def _track_seerr(infos):
    count = 0
    for info in infos or []:
        key, media_kind = _seerr_key_string(info)
        status = SEERR_REQUEST_STATUS.get(_as_int(info.get("status")))
        if not status:
            status = "request_completed" if _as_int(info.get("status")) == 5 else "request_" + str(info.get("status"))
        detail = _seerr_detail(info)
        record = {
            "key": key,
            "kind": media_kind,
            "media_kind": media_kind,
            "tmdb_id": info.get("tmdbId") if media_kind == "movie" else None,
            "tvdb_id": info.get("tvdbId") if media_kind == "series" else None,
            "title": detail.get("title") or "Pedido Seerr #" + str(info.get("requestId")),
            "year": detail.get("year"),
            "profile_id": info.get("profileId"),
            "profile_name": info.get("profileName"),
            "source": "seerr",
            "seerr_request_id": info.get("requestId"),
            "seerr_status": info.get("status"),
            "seerr_media_status": info.get("mediaStatus"),
            "requested_by": info.get("requestedBy"),
            "requested_at": info.get("createdAt") or None,
            "event_at": info.get("createdAt") or None,
            "status": status,
            "status_message": _seerr_status_message(info),
            "completed_at": (info.get("updatedAt") or None) if status == "request_completed" else None,
            "completed_from_seerr": status == "request_completed",
            "meta": {"seerr": True, "is4k": bool(info.get("is4k"))},
        }
        existing = _db_one("SELECT arr_id FROM requests WHERE key = ?", (key,))
        _track_upsert(record, status_authoritative=existing is None or existing["arr_id"] is None)
        count += 1
    return count


def _item_key(item):
    kind = item.get("kind")
    if kind == "movie":
        if item.get("tmdbId"):
            return "movie:tmdb:" + str(item["tmdbId"])
        if item.get("id"):
            return "movie:arr:" + str(item["id"])
    elif kind == "series":
        if item.get("tvdbId"):
            return "series:tvdb:" + str(item["tvdbId"])
        if item.get("id"):
            return "series:arr:" + str(item["id"])
    return None


def _track_snapshot(items):
    count = 0
    for item in items:
        key = item.get("key") or _item_key(item)
        if not key:
            continue
        seerr = item.get("seerr") or {}
        record = {
            "key": key,
            "kind": item.get("kind"),
            "media_kind": item.get("kind"),
            "arr_id": item.get("id"),
            "tmdb_id": item.get("tmdbId"),
            "tvdb_id": item.get("tvdbId"),
            "title": item.get("title"),
            "year": item.get("year"),
            "profile_id": item.get("profileId"),
            "source": "seerr" if seerr else "arr",
            "seerr_request_id": seerr.get("requestId"),
            "seerr_status": seerr.get("status"),
            "seerr_media_status": seerr.get("mediaStatus"),
            "requested_by": seerr.get("requestedBy"),
            "requested_at": seerr.get("createdAt") or None,
            "event_at": seerr.get("createdAt") or None,
            "status": item.get("status") or ("downloaded" if item.get("hasFile") else "missing"),
            "status_message": item.get("errorMessage") or item.get("lastError") or "",
            "meta": {"seerrOnly": bool(item.get("seerrOnly"))},
        }
        _track_upsert(record)
        count += 1
    return count


def _hidden_keys():
    return {row["key"] for row in _db_rows("SELECT key FROM requests WHERE hidden_at IS NOT NULL")}


def _sonarr_episode_context():
    now = time.time()
    cached = _episode_context_cache.get("data")
    if cached is not None and now - _episode_context_cache["ts"] < 10:
        return cached
    key = arr_key(SONARR_CONFIG)
    empty = {"queue": {}, "history": {}, "searching": set(), "seriesSearching": set()}
    if not key:
        return empty
    queue_payload = _safe_arr_request(
        SONARR_URL,
        key,
        "/api/v3/queue?page=1&pageSize=250&includeUnknownSeriesItems=false",
        20,
        {},
    )
    history_payload = _safe_arr_request(
        SONARR_URL,
        key,
        "/api/v3/history?page=1&pageSize=200&sortKey=date&sortDirection=descending",
        20,
        {},
    )
    commands = _safe_arr_request(SONARR_URL, key, "/api/v3/command", 20, []) or []
    queue = {}
    for record in queue_payload.get("records") or []:
        episode_id = _as_int(record.get("episodeId"))
        if not episode_id:
            continue
        size = _as_float(record.get("size"))
        left = _as_float(record.get("sizeleft"))
        state = str(record.get("trackedDownloadState") or "").lower()
        tracked = str(record.get("trackedDownloadStatus") or "").lower()
        status = str(record.get("status") or "").lower()
        error = str(record.get("errorMessage") or "").strip()
        failed = bool(error) or "error" in tracked or "failed" in state or status == "failed"
        active = status == "downloading" or state in (
            "downloading",
            "importing",
            "importpending",
            "importblocked",
            "downloadclientunavailable",
        )
        entry = queue.setdefault(
            episode_id,
            {"count": 0, "size": 0.0, "left": 0.0, "timeleft": "", "error": "", "failed": False, "active": False, "title": ""},
        )
        entry["count"] += 1
        entry["size"] += size
        entry["left"] += left
        if not entry["timeleft"] and record.get("timeleft"):
            entry["timeleft"] = record["timeleft"]
        if failed and not entry["error"]:
            entry["error"] = error or "Falha no download"
        entry["failed"] = entry["failed"] or failed
        entry["active"] = entry["active"] or active
        if record.get("title") and not entry["title"]:
            entry["title"] = record["title"]
    for entry in queue.values():
        if entry["size"] > 0:
            entry["progress"] = round(((entry["size"] - entry["left"]) / entry["size"]) * 100)
        else:
            entry["progress"] = 0
        if entry["failed"]:
            entry["status"] = "error"
        elif entry["active"]:
            entry["status"] = "downloading"
        else:
            entry["status"] = "queued"
    history = {}
    for record in sorted(history_payload.get("records") or [], key=lambda row: row.get("date") or "", reverse=True):
        episode_id = _as_int(record.get("episodeId"))
        if not episode_id:
            continue
        event = str(record.get("eventType") or "")
        failed = "failed" in event.lower() or "failure" in event.lower()
        data = record.get("data") or {}
        message = data.get("message") or data.get("reason") or ""
        entry = history.setdefault(episode_id, {"lastEvent": None, "lastError": ""})
        if entry["lastEvent"] is None:
            entry["lastEvent"] = {
                "eventType": event,
                "date": record.get("date") or "",
                "sourceTitle": record.get("sourceTitle") or "",
                "failed": failed,
                "message": message,
            }
            if failed:
                entry["lastError"] = message or ("Falha: " + (record.get("sourceTitle") or event))
    searching = set()
    series_searching = set()
    for command in commands:
        if str(command.get("status") or "").lower() not in ("queued", "started"):
            continue
        body = command.get("body") or {}
        if str(command.get("name") or "") == "EpisodeSearch":
            for episode_id in body.get("episodeIds") or []:
                value = _as_int(episode_id)
                if value:
                    searching.add(value)
        elif str(command.get("name") or "") == "SeriesSearch":
            value = _as_int(body.get("seriesId"))
            if value:
                series_searching.add(value)
    data = {"queue": queue, "history": history, "searching": searching, "seriesSearching": series_searching}
    _episode_context_cache.update({"ts": now, "data": data})
    return data


def _series_episodes(series_id):
    now = time.time()
    cached = _series_episode_cache.get(series_id)
    if cached and now - cached[0] < 10:
        return cached[1]
    key = arr_key(SONARR_CONFIG)
    if not key:
        return None
    try:
        raw = arr_request(SONARR_URL, key, f"/api/v3/episode?seriesId={series_id}&includeEpisodeFile=true") or []
    except Exception:
        return None
    result = {_as_int(episode.get("id")): episode for episode in raw if _as_int(episode.get("id"))}
    _series_episode_cache[series_id] = (now, result)
    return result


def _reconcile_episode_requests():
    now = time.time()
    if now - _reconcile_cache.get("ts", 0) < 10:
        return
    with _reconcile_lock:
        if time.time() - _reconcile_cache.get("ts", 0) < 10:
            return
        _reconcile_cache["ts"] = time.time()
        rows = _db_rows("SELECT * FROM requests WHERE kind = 'episode'")
        if not rows:
            return
        context = _sonarr_episode_context()
        by_series = {}
        for row in rows:
            series_id = _as_int(row["series_id"])
            if series_id:
                by_series.setdefault(series_id, []).append(row)
        for series_id, series_rows in by_series.items():
            episodes = _series_episodes(series_id)
            if episodes is None:
                continue
            for row in series_rows:
                episode_id = _as_int(row["episode_id"])
                episode = episodes.get(episode_id)
                if not episode:
                    continue
                meta = _json_load(row["meta"])
                queue = context["queue"].get(episode_id)
                recent = _recent(row["requested_at"])
                if episode.get("hasFile"):
                    status = "downloaded"
                    message = "Arquivo presente no Sonarr"
                elif queue:
                    status = queue["status"]
                    message = queue.get("error") or ""
                    meta = {
                        **meta,
                        "queue": {name: queue.get(name) for name in ("count", "progress", "timeleft", "titles", "error")},
                    }
                elif episode_id in context["searching"] or series_id in context["seriesSearching"]:
                    status = "searching"
                    message = "Busca ativa no Sonarr"
                else:
                    history = context["history"].get(episode_id) or {}
                    if history.get("lastError"):
                        status = "error"
                        message = history["lastError"]
                    elif recent and meta.get("search"):
                        status = "searching"
                        message = "Aguardando o Sonarr iniciar o download"
                    elif recent:
                        status = "requested"
                        message = "Episodio monitorado; sem arquivo"
                    else:
                        status = "missing"
                        message = "Pedido registrado; sem arquivo no Sonarr"
                    if history.get("lastEvent"):
                        meta = {**meta, "lastEvent": history["lastEvent"]}
                _track_upsert(
                    {
                        "key": row["key"],
                        "kind": "episode",
                        "media_kind": "series",
                        "arr_id": row["arr_id"],
                        "series_id": series_id,
                        "episode_id": episode_id,
                        "season": _as_int(episode.get("seasonNumber")),
                        "episode": _as_int(episode.get("episodeNumber")),
                        "absolute_episode": _as_int(episode.get("absoluteEpisodeNumber")),
                        "title": row["title"],
                        "episode_title": episode.get("title") or row["episode_title"],
                        "year": row["year"],
                        "profile_id": row["profile_id"],
                        "profile_name": row["profile_name"],
                        "root_folder": row["root_folder"],
                        "source": row["source"],
                        "requested_at": row["requested_at"],
                        "status": status,
                        "status_message": message,
                        "meta": meta,
                    }
                )
        _reconcile_cache["ts"] = time.time()


def _request_to_item(row, include_events=False):
    item = {
        "key": row["key"],
        "kind": row["kind"],
        "mediaKind": row["media_kind"],
        "arrId": row["arr_id"],
        "seriesId": row["series_id"],
        "episodeId": row["episode_id"],
        "season": row["season"],
        "episode": row["episode"],
        "absoluteEpisode": row["absolute_episode"],
        "title": row["title"],
        "episodeTitle": row["episode_title"],
        "year": row["year"],
        "profileId": row["profile_id"],
        "profileName": row["profile_name"],
        "rootFolder": row["root_folder"],
        "source": row["source"],
        "seerrRequestId": row["seerr_request_id"],
        "seerrStatus": row["seerr_status"],
        "seerrMediaStatus": row["seerr_media_status"],
        "requestedBy": row["requested_by"],
        "requestedAt": row["requested_at"],
        "firstSeenAt": row["first_seen_at"],
        "lastSeenAt": row["last_seen_at"],
        "lastCheckedAt": row["last_checked_at"],
        "status": row["status"],
        "statusMessage": row["status_message"],
        "completedAt": row["completed_at"],
        "hidden": bool(row["hidden_at"]),
        "hiddenAt": row["hidden_at"],
        "meta": _json_load(row["meta"]),
    }
    if include_events:
        events = _db_rows("SELECT at, status, message, source FROM events WHERE key = ? ORDER BY at ASC, id ASC", (row["key"],))
        item["events"] = [
            {
                "at": event["at"],
                "status": event["status"],
                "message": event["message"],
                "source": event["source"],
            }
            for event in events
        ]
    return item


def requests_payload(params):
    try:
        _reconcile_episode_requests()
    except Exception:
        pass
    view = (params.get("view") or ["active"])[0].lower()
    if view in ("history", "all", "archive"):
        try:
            infos, _ = seerr_infos()
            if infos:
                _track_seerr(infos)
        except Exception:
            pass
    kind = (params.get("kind") or [""])[0].strip().lower()
    statuses = [value.strip() for value in (params.get("status") or [""])[0].split(",") if value.strip()]
    query = (params.get("q") or [""])[0].strip()
    series_id = _as_int((params.get("seriesId") or [""])[0])
    episode_id = _as_int((params.get("episodeId") or [""])[0])
    include_events = (params.get("events") or ["0"])[0].lower() in ("1", "true", "yes")
    try:
        page = max(1, int((params.get("page") or ["1"])[0]))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(int((params.get("pageSize") or ["100"])[0]), 500))
    except (TypeError, ValueError):
        page_size = 100

    where = []
    args = []
    if view == "active":
        where.append("hidden_at IS NULL")
    elif view == "archive":
        where.append("hidden_at IS NOT NULL")
    if kind in ("movie", "series", "episode"):
        where.append("kind = ?")
        args.append(kind)
    if statuses:
        where.append("status IN (" + ", ".join("?" for _ in statuses) + ")")
        args.extend(statuses)
    if series_id:
        where.append("series_id = ?")
        args.append(series_id)
    if episode_id:
        where.append("episode_id = ?")
        args.append(episode_id)
    if query:
        like = "%" + query.lower() + "%"
        where.append("(LOWER(COALESCE(title, '')) LIKE ? OR LOWER(COALESCE(episode_title, '')) LIKE ?)")
        args.extend([like, like])
    where_sql = " AND ".join(where) if where else "1=1"

    order_sql = (
        "COALESCE(completed_at, last_seen_at, requested_at) DESC, key"
        if view in ("history", "all", "archive")
        else "CASE status "
        "WHEN 'request_failed' THEN 0 WHEN 'request_declined' THEN 1 WHEN 'error' THEN 2 "
        "WHEN 'request_pending' THEN 3 WHEN 'request_approved' THEN 4 WHEN 'downloading' THEN 5 "
        "WHEN 'queued' THEN 6 WHEN 'searching' THEN 7 WHEN 'requested' THEN 8 WHEN 'missing' THEN 9 "
        "WHEN 'partial' THEN 10 WHEN 'downloaded' THEN 11 ELSE 12 END, requested_at DESC"
    )

    conn = _db_connect()
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM requests WHERE " + where_sql, args).fetchone()["n"]
        counts = {
            row["status"]: row["n"]
            for row in conn.execute(
                "SELECT status, COUNT(*) AS n FROM requests WHERE " + where_sql + " GROUP BY status",
                args,
            )
        }
        hidden_count = conn.execute("SELECT COUNT(*) AS n FROM requests WHERE hidden_at IS NOT NULL").fetchone()["n"]
        offset = (page - 1) * page_size
        rows = conn.execute(
            "SELECT * FROM requests WHERE " + where_sql + " ORDER BY " + order_sql + " LIMIT ? OFFSET ?",
            args + [page_size, offset],
        ).fetchall()
        items = [_request_to_item(row, include_events) for row in rows]
    finally:
        conn.close()
    return {
        "ok": True,
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "counts": counts,
        "hiddenCount": hidden_count,
    }


def _payload_keys(payload):
    values = payload.get("keys")
    if isinstance(values, str):
        values = [values]
    if not values and payload.get("key"):
        values = [payload.get("key")]
    keys = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in keys:
            keys.append(text)
    return keys[:500]


def requests_hide(payload):
    keys = _payload_keys(payload)
    if not keys:
        return {"ok": False, "error": "keys vazio"}
    hidden = bool(payload.get("hidden", True))
    value = _now_iso() if hidden else None
    with _db_lock:
        conn = _db_connect()
        try:
            placeholders = ", ".join("?" for _ in keys)
            cursor = conn.execute(
                "UPDATE requests SET hidden_at = ? WHERE key IN (" + placeholders + ")",
                [value] + keys,
            )
            now = _now_iso()
            event_status = "archived" if hidden else "restored"
            for key in keys:
                conn.execute(
                    "INSERT INTO events (key, at, status, message, source, meta) VALUES (?, ?, ?, ?, ?, ?)",
                    (key, now, event_status, "", "manual", None),
                )
            conn.commit()
            updated = cursor.rowcount
        finally:
            conn.close()
    return {"ok": True, "updated": updated, "hidden": hidden}


def requests_delete(payload):
    if payload.get("confirm") is not True and str(payload.get("confirm")).lower() not in ("1", "true", "yes"):
        return {"ok": False, "error": "confirmacao obrigatoria"}
    keys = _payload_keys(payload)
    if not keys:
        return {"ok": False, "error": "keys vazio"}
    with _db_lock:
        conn = _db_connect()
        try:
            placeholders = ", ".join("?" for _ in keys)
            conn.execute("DELETE FROM events WHERE key IN (" + placeholders + ")", keys)
            cursor = conn.execute("DELETE FROM requests WHERE key IN (" + placeholders + ")", keys)
            conn.commit()
            deleted = cursor.rowcount
        finally:
            conn.close()
    return {"ok": True, "deleted": deleted}


def backfill_episodes(series_id, limit=10, include_downloaded=True, monitored_only=False):
    series_id = _as_int(series_id)
    limit = max(1, min(_as_int(limit) or 10, 100))
    key = arr_key(SONARR_CONFIG)
    if not series_id or not key:
        return {"ok": False, "error": "seriesId/API key invalidos"}
    series = arr_request(SONARR_URL, key, f"/api/v3/series/{series_id}") or {}
    episodes = arr_request(SONARR_URL, key, f"/api/v3/episode?seriesId={series_id}&includeEpisodeFile=true") or []
    history_payload = _safe_arr_request(
        SONARR_URL,
        key,
        "/api/v3/history?page=1&pageSize=200&sortKey=date&sortDirection=descending",
        20,
        {},
    )
    history = {}
    for record in history_payload.get("records") or []:
        if _as_int(record.get("seriesId")) != series_id:
            continue
        episode_id = _as_int(record.get("episodeId"))
        if episode_id:
            history.setdefault(episode_id, []).append(record)
    for records in history.values():
        records.sort(key=lambda row: row.get("date") or "")

    candidates = [
        episode
        for episode in episodes
        if _as_int(episode.get("seasonNumber")) is not None and (not monitored_only or episode.get("monitored"))
    ]
    candidates.sort(key=lambda episode: (_as_int(episode.get("seasonNumber")) or 0, _as_int(episode.get("episodeNumber")) or 0))
    if include_downloaded:
        selected = candidates[-limit:]
    else:
        missing = [episode for episode in candidates if not episode.get("hasFile")]
        selected = (missing or candidates)[-limit:]
    selected.sort(key=lambda episode: (_as_int(episode.get("seasonNumber")) or 0, _as_int(episode.get("episodeNumber")) or 0))

    profile_names = {}
    try:
        profiles, _ = _sonarr_options()
        profile_names = {_as_int(profile.get("id")): profile.get("name") or "" for profile in profiles}
    except Exception:
        profile_names = {}
    requested_values = []
    for episode in selected:
        records = history.get(_as_int(episode.get("id"))) or []
        if records:
            requested_values.append(records[0].get("date") or "")
    fallback = min([value for value in requested_values if value], default=_iso_ago(3600))
    profile_id = _as_int(series.get("qualityProfileId"))

    recorded = []
    for episode in selected:
        episode_id = _as_int(episode.get("id"))
        records = history.get(episode_id) or []
        requested_at = records[0].get("date") if records else fallback
        event_at = records[-1].get("date") if records and episode.get("hasFile") else requested_at
        status = "downloaded" if episode.get("hasFile") else "missing"
        message = "Arquivo presente no Sonarr" if episode.get("hasFile") else "Pedido registrado; sem arquivo no Sonarr"
        record = {
            "key": "episode:" + str(episode_id),
            "kind": "episode",
            "media_kind": "series",
            "arr_id": episode_id,
            "series_id": series_id,
            "episode_id": episode_id,
            "season": _as_int(episode.get("seasonNumber")),
            "episode": _as_int(episode.get("episodeNumber")),
            "absolute_episode": _as_int(episode.get("absoluteEpisodeNumber")),
            "tvdb_id": _as_int(series.get("tvdbId")),
            "title": series.get("title") or "",
            "episode_title": episode.get("title") or "",
            "year": _as_int(series.get("year")),
            "profile_id": profile_id,
            "profile_name": profile_names.get(profile_id, ""),
            "root_folder": series.get("rootFolderPath") or "",
            "source": "backfill",
            "requested_at": requested_at,
            "event_at": event_at,
            "completed_at": event_at if status == "downloaded" else None,
            "status": status,
            "status_message": message,
            "meta": {"backfill": True, "search": False, "monitored": bool(episode.get("monitored"))},
        }
        _track_upsert(record)
        recorded.append(
            {
                "episodeId": episode_id,
                "season": record["season"],
                "episode": record["episode"],
                "title": record["episode_title"],
                "status": status,
            }
        )
    _reconcile_cache["ts"] = 0.0
    _episode_context_cache.update({"ts": 0.0, "data": None})
    _series_episode_cache.pop(series_id, None)
    _reconcile_episode_requests()
    return {
        "ok": True,
        "series": {"id": series_id, "title": series.get("title"), "tvdbId": _as_int(series.get("tvdbId"))},
        "count": len(recorded),
        "episodes": recorded,
    }


def _cli(argv):
    import argparse

    parser = argparse.ArgumentParser(description="media-agent")
    parser.add_argument("--backfill-episodes", type=int, metavar="SERIES_ID")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--monitored-only", action="store_true")
    parser.add_argument("--missing-only", action="store_true")
    args = parser.parse_args(argv)
    if args.backfill_episodes:
        result = backfill_episodes(
            args.backfill_episodes,
            args.limit,
            not args.missing_only,
            args.monitored_only,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 1


def _record_item_id(record, kind):
    return _as_int(record.get("movieId") if kind == "movie" else record.get("seriesId"))


def _safe_arr_request(base, key, path, timeout, default):
    try:
        return arr_request(base, key, path, timeout=timeout) or default
    except Exception:
        return default


def arr_status_maps(base, key, kind):
    queues = {}
    history = {}
    searching = set()

    queue_path = "/api/v3/queue?page=1&pageSize=250&includeUnknownMovieItems=false&includeUnknownSeriesItems=false"
    history_path = "/api/v3/history?page=1&pageSize=200&sortKey=date&sortDirection=descending"
    with ThreadPoolExecutor(max_workers=3) as pool:
        queue_future = pool.submit(_safe_arr_request, base, key, queue_path, 20, {})
        history_future = pool.submit(_safe_arr_request, base, key, history_path, 20, {})
        commands_future = pool.submit(_safe_arr_request, base, key, "/api/v3/command", 20, [])
        payload = queue_future.result() or {}
        history_payload = history_future.result() or {}
        commands = commands_future.result() or []

    queue_records = payload.get("records") or []

    for record in queue_records:
        item_id = _record_item_id(record, kind)
        if item_id is None:
            continue
        size = _as_float(record.get("size"))
        left = _as_float(record.get("sizeleft"))
        state = str(record.get("trackedDownloadState") or "").lower()
        tracked = str(record.get("trackedDownloadStatus") or "").lower()
        status = str(record.get("status") or "").lower()
        error = str(record.get("errorMessage") or "").strip()
        failed = bool(error) or "error" in tracked or "failed" in state or status == "failed"
        active = status == "downloading" or state in (
            "downloading",
            "importing",
            "importpending",
            "importblocked",
            "downloadclientunavailable",
        )
        entry = queues.setdefault(item_id, {
            "count": 0,
            "size": 0.0,
            "left": 0.0,
            "timeleft": "",
            "error": "",
            "failed": False,
            "active": False,
            "titles": [],
        })
        entry["count"] += 1
        entry["size"] += size
        entry["left"] += left
        if not entry["timeleft"] and record.get("timeleft"):
            entry["timeleft"] = record.get("timeleft")
        if failed and not entry["error"]:
            entry["error"] = error or "Falha no download"
        entry["failed"] = entry["failed"] or failed
        entry["active"] = entry["active"] or active
        title = record.get("title")
        if title and len(entry["titles"]) < 3:
            entry["titles"].append(title)

    for entry in queues.values():
        if entry["size"] > 0:
            entry["progress"] = round(((entry["size"] - entry["left"]) / entry["size"]) * 100)
        else:
            entry["progress"] = 0
        if entry["failed"]:
            entry["status"] = "error"
        elif entry["active"]:
            entry["status"] = "downloading"
        else:
            entry["status"] = "queued"

    history_records = history_payload.get("records") or []
    history_records.sort(key=lambda record: record.get("date") or "", reverse=True)
    for record in history_records:
        item_id = _record_item_id(record, kind)
        if item_id is None:
            continue
        event = str(record.get("eventType") or "")
        failed = "failed" in event.lower() or "failure" in event.lower()
        data = record.get("data") or {}
        message = data.get("message") or data.get("reason") or ""
        entry = history.setdefault(item_id, {"lastEvent": None, "lastError": ""})
        if entry["lastEvent"] is None:
            entry["lastEvent"] = {
                "eventType": event,
                "date": record.get("date") or "",
                "sourceTitle": record.get("sourceTitle") or "",
                "failed": failed,
                "message": message,
            }
            if failed:
                entry["lastError"] = message or ("Falha: " + (record.get("sourceTitle") or event))

    for command in commands:
        if str(command.get("status") or "").lower() not in ("queued", "started"):
            continue
        body = command.get("body") or {}
        if kind == "movie":
            for movie_id in body.get("movieIds") or []:
                value = _as_int(movie_id)
                if value is not None:
                    searching.add(value)
        else:
            series_id = _as_int(body.get("seriesId"))
            if series_id is not None:
                searching.add(series_id)

    return queues, history, searching


def _enrich_item(item, queues, history, searching):
    item_id = item.get("id")
    queue = queues.get(item_id)
    hist = history.get(item_id) or {}
    item["searching"] = item_id in searching
    item["queue"] = queue
    item["lastEvent"] = hist.get("lastEvent")
    item["lastError"] = hist.get("lastError") or ""
    item["errorMessage"] = ""

    if queue:
        item["status"] = queue["status"]
        item["errorMessage"] = queue.get("error") or ""
    elif item.get("hasFile"):
        if (
            item.get("kind") == "series"
            and item.get("episodeCount")
            and 0 < (item.get("episodeFileCount") or 0) < item["episodeCount"]
        ):
            item["status"] = "partial"
        else:
            item["status"] = "downloaded"
    elif item["searching"]:
        item["status"] = "searching"
    elif hist.get("lastError"):
        item["status"] = "error"
        item["errorMessage"] = hist["lastError"]
    else:
        item["status"] = "missing"
    return item


_sonarr_series_cache = {"ts": 0.0, "series": []}
_sonarr_options_cache = {"ts": 0.0, "profiles": [], "roots": []}
_sonarr_refresh_cache = {}


def _sonarr_series(refresh=False):
    now = time.time()
    if not refresh and now - _sonarr_series_cache["ts"] < 30:
        return _sonarr_series_cache["series"]
    key = arr_key(SONARR_CONFIG)
    series = arr_request(SONARR_URL, key, "/api/v3/series") if key else []
    _sonarr_series_cache.update({"ts": now, "series": series or []})
    return _sonarr_series_cache["series"]


def _sonarr_options():
    now = time.time()
    if now - _sonarr_options_cache["ts"] < 300:
        return _sonarr_options_cache["profiles"], _sonarr_options_cache["roots"]
    key = arr_key(SONARR_CONFIG)
    profiles = []
    roots = []
    if key:
        try:
            profiles = arr_request(SONARR_URL, key, "/api/v3/qualityprofile") or []
        except Exception:
            profiles = []
        try:
            roots = arr_request(SONARR_URL, key, "/api/v3/rootfolder") or []
        except Exception:
            roots = []
    _sonarr_options_cache.update({"ts": now, "profiles": profiles, "roots": roots})
    return profiles, roots


def _series_summary(series, profile_names=None):
    stats = series.get("statistics") or {}
    return {
        "id": series.get("id"),
        "tvdbId": _as_int(series.get("tvdbId")),
        "title": series.get("title") or "",
        "year": _as_int(series.get("year")),
        "profileId": _as_int(series.get("qualityProfileId")),
        "profileName": (profile_names or {}).get(_as_int(series.get("qualityProfileId")), ""),
        "rootFolderPath": series.get("rootFolderPath") or "",
        "seriesType": series.get("seriesType") or "standard",
        "monitored": bool(series.get("monitored")),
        "episodeCount": stats.get("episodeCount") or 0,
        "episodeFileCount": stats.get("episodeFileCount") or 0,
    }


def sonarr_options_payload():
    try:
        profiles, roots = _sonarr_options()
        return {
            "ok": True,
            "profiles": [{"id": p.get("id"), "name": p.get("name")} for p in profiles],
            "rootFolders": [{"id": r.get("id"), "path": r.get("path")} for r in roots],
            "defaultProfile": SONARR_DUBBED_PROFILE,
        }
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def sonarr_lookup(term):
    try:
        term = (term or "").strip()
        if len(term) < 2:
            return {"ok": False, "error": "termo muito curto"}
        key = arr_key(SONARR_CONFIG)
        if not key:
            return {"ok": False, "error": "API key do Sonarr não encontrada"}
        results = arr_request(SONARR_URL, key, "/api/v3/series/lookup?term=" + urllib.parse.quote(term)) or []
        profiles, _ = _sonarr_options()
        profile_names = {_as_int(p.get("id")): p.get("name") or "" for p in profiles}
        existing = {_as_int(s.get("tvdbId")): s for s in _sonarr_series()}
        rows = []
        for item in results[:15]:
            tvdb_id = _as_int(item.get("tvdbId"))
            poster = ""
            for image in item.get("images") or []:
                if image.get("coverType") == "poster":
                    poster = image.get("remoteUrl") or ""
                    break
            row = {
                "tvdbId": tvdb_id,
                "title": item.get("title") or "",
                "year": _as_int(item.get("year")),
                "overview": (item.get("overview") or "")[:500],
                "network": item.get("network") or "",
                "seasons": len(item.get("seasons") or []),
                "seriesType": item.get("seriesType") or "standard",
                "status": item.get("status") or "",
                "poster": poster,
                "existing": None,
            }
            found = existing.get(tvdb_id)
            if found:
                row["existing"] = _series_summary(found, profile_names)
            rows.append(row)
        return {"ok": True, "results": rows}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def sonarr_add(payload):
    try:
        tvdb_id = _as_int(payload.get("tvdbId"))
        profile_id = _as_int(payload.get("profileId"))
        root_folder = str(payload.get("rootFolderPath") or "").strip()
        series_type = payload.get("seriesType") or "standard"
        if series_type not in ("standard", "anime", "daily"):
            series_type = "standard"
        if not tvdb_id or not profile_id or not root_folder:
            return {"ok": False, "error": "dados incompletos"}
        key = arr_key(SONARR_CONFIG)
        if not key:
            return {"ok": False, "error": "API key do Sonarr não encontrada"}
        profiles, roots = _sonarr_options()
        profile_names = {_as_int(p.get("id")): p.get("name") or "" for p in profiles}
        if profile_id not in profile_names:
            return {"ok": False, "error": "perfil invalido"}
        if root_folder not in {r.get("path") for r in roots}:
            return {"ok": False, "error": "pasta raiz invalida"}
        existing = next((s for s in _sonarr_series(refresh=True) if _as_int(s.get("tvdbId")) == tvdb_id), None)
        if existing:
            return {"ok": True, "alreadyExists": True, "series": _series_summary(existing, profile_names)}
        results = arr_request(
            SONARR_URL,
            key,
            "/api/v3/series/lookup?term=" + urllib.parse.quote(f"tvdb:{tvdb_id}"),
        ) or []
        if not results:
            return {"ok": False, "error": "série não encontrada no TVDB"}
        body = dict(results[0])
        body.pop("id", None)
        body.update({
            "qualityProfileId": profile_id,
            "rootFolderPath": root_folder,
            "monitored": True,
            "seasonFolder": True,
            "seriesType": series_type,
            "addOptions": {"monitor": "none", "searchForMissingEpisodes": False},
        })
        created = arr_request(SONARR_URL, key, "/api/v3/series", "POST", body)
        _sonarr_series_cache.update({"ts": 0.0, "series": []})
        try:
            arr_request(SONARR_URL, key, "/api/v3/command", "POST", {"name": "RefreshSeries", "seriesId": created.get("id")})
            _sonarr_refresh_cache[created.get("id")] = time.time()
        except Exception:
            pass
        return {"ok": True, "alreadyExists": False, "series": _series_summary(created, profile_names)}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def sonarr_episodes(series_id):
    try:
        series_id = _as_int(series_id)
        if not series_id:
            return {"ok": False, "error": "seriesId inválido"}
        key = arr_key(SONARR_CONFIG)
        if not key:
            return {"ok": False, "error": "API key do Sonarr não encontrada"}
        series = arr_request(SONARR_URL, key, f"/api/v3/series/{series_id}")
        profiles, _ = _sonarr_options()
        profile_names = {_as_int(p.get("id")): p.get("name") or "" for p in profiles}
        raw = arr_request(SONARR_URL, key, f"/api/v3/episode?seriesId={series_id}&includeEpisodeFile=true") or []
        refreshing = False
        if not raw:
            refreshing = True
            now = time.time()
            if now - _sonarr_refresh_cache.get(series_id, 0.0) > 30:
                _sonarr_refresh_cache[series_id] = now
                try:
                    arr_request(SONARR_URL, key, "/api/v3/command", "POST", {"name": "RefreshSeries", "seriesId": series_id})
                except Exception:
                    pass
        episodes = []
        for episode in raw:
            episodes.append({
                "id": _as_int(episode.get("id")),
                "seasonNumber": _as_int(episode.get("seasonNumber")) or 0,
                "episodeNumber": _as_int(episode.get("episodeNumber")) or 0,
                "absoluteEpisodeNumber": _as_int(episode.get("absoluteEpisodeNumber")),
                "title": episode.get("title") or "",
                "airDate": episode.get("airDateUtc") or episode.get("airDate") or "",
                "monitored": bool(episode.get("monitored")),
                "hasFile": bool(episode.get("hasFile")),
            })
        episodes.sort(key=lambda ep: (ep["seasonNumber"], ep["episodeNumber"]))
        return {
            "ok": True,
            "series": _series_summary(series, profile_names),
            "episodes": episodes,
            "refreshing": refreshing,
        }
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def _chunks(values, size=100):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def sonarr_monitor_episodes(payload):
    try:
        series_id = _as_int(payload.get("seriesId"))
        episode_ids = {_as_int(value) for value in (payload.get("episodeIds") or [])}
        episode_ids.discard(None)
        monitored = bool(payload.get("monitored", True))
        unmonitor_others = bool(payload.get("unmonitorOthers"))
        search = bool(payload.get("search", True))
        if not series_id or not episode_ids:
            return {"ok": False, "error": "seriesId/episodeIds inválidos"}
        key = arr_key(SONARR_CONFIG)
        if not key:
            return {"ok": False, "error": "API key do Sonarr não encontrada"}
        raw = arr_request(SONARR_URL, key, f"/api/v3/episode?seriesId={series_id}") or []
        valid = {_as_int(episode.get("id")): episode for episode in raw}
        selected = [value for value in episode_ids if value in valid]
        if not selected:
            return {"ok": False, "error": "nenhum episódio válido"}
        unmonitored = 0
        if unmonitor_others:
            others = [
                value for value, episode in valid.items()
                if value not in episode_ids and episode.get("monitored")
            ]
            for chunk in _chunks(others):
                arr_request(SONARR_URL, key, "/api/v3/episode/monitor", "PUT", {"episodeIds": chunk, "monitored": False})
            unmonitored = len(others)
        for chunk in _chunks(selected):
            arr_request(SONARR_URL, key, "/api/v3/episode/monitor", "PUT", {"episodeIds": chunk, "monitored": monitored})
        command_id = None
        if search and monitored:
            command = arr_request(
                SONARR_URL,
                key,
                "/api/v3/command",
                "POST",
                {"name": "EpisodeSearch", "episodeIds": selected},
            )
            command_id = (command or {}).get("id")
        series = {}
        try:
            series = arr_request(SONARR_URL, key, f"/api/v3/series/{series_id}") or {}
        except Exception:
            series = {}
        profile_id = _as_int(series.get("qualityProfileId"))
        profile_name = ""
        try:
            profiles, _ = _sonarr_options()
            profile_name = {_as_int(profile.get("id")): profile.get("name") or "" for profile in profiles}.get(profile_id, "")
        except Exception:
            profile_name = ""
        now = _now_iso()
        recorded = 0
        for episode_id in selected:
            episode = valid.get(episode_id) or {}
            if episode.get("hasFile"):
                status = "downloaded"
                message = "Arquivo ja presente no Sonarr"
            elif search and monitored:
                status = "searching"
                message = "Busca iniciada no Sonarr"
            elif monitored:
                status = "requested"
                message = "Episódio monitorado; busca manual não solicitada"
            else:
                status = "missing"
                message = "Episodio desmarcado"
            _track_upsert(
                {
                    "key": "episode:" + str(episode_id),
                    "kind": "episode",
                    "media_kind": "series",
                    "arr_id": episode_id,
                    "series_id": series_id,
                    "episode_id": episode_id,
                    "season": _as_int(episode.get("seasonNumber")),
                    "episode": _as_int(episode.get("episodeNumber")),
                    "absolute_episode": _as_int(episode.get("absoluteEpisodeNumber")),
                    "tvdb_id": _as_int(series.get("tvdbId")),
                    "title": series.get("title") or "",
                    "episode_title": episode.get("title") or "",
                    "year": _as_int(series.get("year")),
                    "profile_id": profile_id,
                    "profile_name": profile_name,
                    "root_folder": series.get("rootFolderPath") or "",
                    "source": "manual",
                    "requested_at": now,
                    "refresh_requested_at": True,
                    "status": status,
                    "status_message": message,
                    "meta": {
                        "search": bool(search and monitored),
                        "unmonitorOthers": unmonitor_others,
                        "commandId": command_id,
                    },
                }
            )
            recorded += 1
        return {
            "ok": True,
            "monitored": len(selected),
            "unmonitored": unmonitored,
            "searchCommand": command_id,
            "recorded": recorded,
        }
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


_quality_profiles_cache = {}


def _quality_profiles(base, key):
    if not key:
        return []
    now = time.time()
    cached = _quality_profiles_cache.get(base)
    if cached and now - cached[0] < 300:
        return cached[1]
    try:
        profiles = arr_request(base, key, "/api/v3/qualityprofile") or []
    except Exception:
        profiles = []
    _quality_profiles_cache[base] = (now, profiles)
    return profiles


def arr_pending(include_status=False):
    try:
        items = []
        seerr_error = ""
        radarr_key = arr_key(RADARR_CONFIG)
        sonarr_key = arr_key(SONARR_CONFIG)
        radarr_profile_names = {_as_int(p.get("id")): p.get("name") or "" for p in _quality_profiles(RADARR_URL, radarr_key)}
        sonarr_profile_names = {_as_int(p.get("id")): p.get("name") or "" for p in _quality_profiles(SONARR_URL, sonarr_key)}
        radarr_maps = arr_status_maps(RADARR_URL, radarr_key, "movie") if include_status and radarr_key else ({}, {}, set())
        sonarr_maps = arr_status_maps(SONARR_URL, sonarr_key, "series") if include_status and sonarr_key else ({}, {}, set())

        if radarr_key:
            for movie in arr_request(RADARR_URL, radarr_key, "/api/v3/movie") or []:
                profile_id = _as_int(movie.get("qualityProfileId"))
                item = {
                    "kind": "movie",
                    "id": movie.get("id"),
                    "title": movie.get("title"),
                    "year": movie.get("year"),
                    "hasFile": bool(movie.get("hasFile")),
                    "profileId": profile_id,
                    "profileName": radarr_profile_names.get(profile_id, ""),
                    "monitored": bool(movie.get("monitored")),
                    "tmdbId": _as_int(movie.get("tmdbId")),
                    "addedAt": movie.get("added") or "",
                }
                if include_status:
                    _enrich_item(item, *radarr_maps)
                items.append(item)

        if sonarr_key:
            for series in arr_request(SONARR_URL, sonarr_key, "/api/v3/series") or []:
                stats = series.get("statistics") or {}
                profile_id = _as_int(series.get("qualityProfileId"))
                item = {
                    "kind": "series",
                    "id": series.get("id"),
                    "title": series.get("title"),
                    "year": series.get("year"),
                    "hasFile": (stats.get("episodeFileCount") or 0) > 0,
                    "profileId": profile_id,
                    "profileName": sonarr_profile_names.get(profile_id, ""),
                    "monitored": bool(series.get("monitored")),
                    "tvdbId": _as_int(series.get("tvdbId")),
                    "seriesType": series.get("seriesType") or "",
                    "episodeCount": stats.get("episodeCount") or 0,
                    "episodeFileCount": stats.get("episodeFileCount") or 0,
                    "totalEpisodeCount": stats.get("totalEpisodeCount") or 0,
                    "seasonCount": stats.get("seasonCount") or 0,
                    "percent": stats.get("percentOfEpisodes") or 0,
                    "addedAt": series.get("added") or "",
                }
                if include_status:
                    _enrich_item(item, *sonarr_maps)
                items.append(item)

        infos = []
        try:
            infos, seerr_error = seerr_infos()
            _merge_seerr(items, infos)
        except Exception as error:
            seerr_error = f"{type(error).__name__}: {error}"
        for item in items:
            item["key"] = _item_key(item)
        if include_status:
            if infos:
                try:
                    _track_seerr(infos)
                except Exception:
                    pass
            trackable = [
                item for item in items
                if item.get("seerr")
                or (item["kind"] == "movie" and item.get("profileId") == RADARR_DUBBED_PROFILE)
                or (item["kind"] == "series" and item.get("profileId") == SONARR_DUBBED_PROFILE)
            ]
            try:
                _track_snapshot(trackable)
            except Exception:
                pass
        try:
            hidden = _hidden_keys()
        except Exception:
            hidden = set()
        if hidden:
            items = [item for item in items if item.get("key") not in hidden]

        items.sort(key=lambda item: (0 if item["kind"] == "movie" else 1, (item.get("title") or "").lower()))
        return {"ok": True, "items": items, "seerrError": seerr_error}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def arr_check(kind, item_id):
    try:
        if kind == "movie":
            key = arr_key(RADARR_CONFIG)
            releases = arr_request(RADARR_URL, key, f"/api/v3/release?movieId={int(item_id)}")
        elif kind == "series":
            key = arr_key(SONARR_CONFIG)
            releases = arr_request(SONARR_URL, key, f"/api/v3/release?seriesId={int(item_id)}")
        else:
            return {"ok": False, "error": "kind invalido"}
        accepted = [release for release in releases if not release.get("rejected")]
        best = []
        for release in sorted(accepted, key=lambda item: (item.get("customFormatScore") or -999), reverse=True)[:5]:
            best.append({
                "title": release.get("title"),
                "score": release.get("customFormatScore"),
                "seeders": release.get("seeders"),
            })
        return {"ok": True, "accepted": len(accepted), "total": len(releases), "best": best}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def arr_search(kind, item_id, profile=None):
    try:
        if kind == "movie":
            key = arr_key(RADARR_CONFIG)
            item = arr_request(RADARR_URL, key, f"/api/v3/movie/{int(item_id)}")
            if profile is not None:
                item["qualityProfileId"] = int(profile)
                item = arr_request(RADARR_URL, key, f"/api/v3/movie/{int(item_id)}", "PUT", item)
            command = arr_request(RADARR_URL, key, "/api/v3/command", "POST", {"name": "MoviesSearch", "movieIds": [int(item_id)]})
        elif kind == "series":
            key = arr_key(SONARR_CONFIG)
            item = arr_request(SONARR_URL, key, f"/api/v3/series/{int(item_id)}")
            if profile is not None:
                item["qualityProfileId"] = int(profile)
                item = arr_request(SONARR_URL, key, f"/api/v3/series/{int(item_id)}", "PUT", item)
            command = arr_request(SONARR_URL, key, "/api/v3/command", "POST", {"name": "SeriesSearch", "seriesId": int(item_id)})
        else:
            return {"ok": False, "error": "kind invalido"}
        return {"ok": True, "profile": item.get("qualityProfileId"), "command": command.get("id")}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def arr_switch(kind, item_id):
    if kind == "movie":
        profile = RADARR_ORIGINAL_PROFILE
    elif kind == "series":
        profile = SONARR_ORIGINAL_PROFILE
    else:
        return {"ok": False, "error": "kind invalido"}
    return arr_search(kind, item_id, profile)




class Handler(BaseHTTPRequestHandler):
    def _allowed(self):
        try:
            address = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return False
        return any(address in network for network in ALLOWED_NETWORKS)

    def _headers(self, code, ctype, length):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(length))
        self.end_headers()

    def _forbidden(self):
        if self._allowed():
            return False
        self._json(403, {"error": "origem não permitida"})
        return True

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self._headers(code, "application/json", len(body))
        self.wfile.write(body)

    def _raw(self, code, content_type, body):
        self._headers(code, content_type, len(body))
        self.wfile.write(body)

    def _bazarr(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        path = (params.get("path") or [""])[0]
        code, content_type, body = bazarr_proxy(path, self.command)
        self._raw(code, content_type, body)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode())
        except Exception:
            return {}

    def do_OPTIONS(self):
        self._headers(204, "text/plain", 0)

    def do_GET(self):
        if self._forbidden():
            return
        if self.path.startswith("/subs/quota"):
            self._json(200, os_quota())
        elif self.path.startswith("/storage"):
            self._json(200, storage_payload())
        elif self.path.startswith("/requests"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            self._json(200, requests_payload(params))
        elif self.path.startswith("/arr/pending"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            include_status = (params.get("status") or ["0"])[0].lower() in ("1", "true", "yes")
            self._json(200, arr_pending(include_status))
        elif self.path.startswith("/sonarr/options"):
            self._json(200, sonarr_options_payload())
        elif self.path.startswith("/sonarr/lookup"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            self._json(200, sonarr_lookup((params.get("term") or [""])[0]))
        elif self.path.startswith("/sonarr/episodes"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            self._json(200, sonarr_episodes((params.get("seriesId") or [""])[0]))
        elif self.path.startswith("/bazarr"):
            self._bazarr()
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self._forbidden():
            return
        if self.path.startswith("/requests/hide"):
            self._json(200, requests_hide(self._read_json()))
        elif self.path.startswith("/requests/restore"):
            payload = self._read_json()
            payload["hidden"] = False
            self._json(200, requests_hide(payload))
        elif self.path.startswith("/requests/delete"):
            self._json(200, requests_delete(self._read_json()))
        elif self.path.startswith("/arr/check"):
            body = self._read_json()
            self._json(200, arr_check(body.get("kind"), body.get("id")))
        elif self.path.startswith("/arr/search"):
            body = self._read_json()
            self._json(200, arr_search(body.get("kind"), body.get("id")))
        elif self.path.startswith("/arr/switch"):
            body = self._read_json()
            self._json(200, arr_switch(body.get("kind"), body.get("id")))
        elif self.path.startswith("/sonarr/add"):
            self._json(200, sonarr_add(self._read_json()))
        elif self.path.startswith("/sonarr/episodes/monitor"):
            self._json(200, sonarr_monitor_episodes(self._read_json()))
        else:
            self._json(404, {"error": "not found"})

    def do_PATCH(self):
        if self._forbidden():
            return
        if self.path.startswith("/bazarr"):
            self._bazarr()
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    _db_init()
    if len(sys.argv) > 1:
        raise SystemExit(_cli(sys.argv[1:]))
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    print(f"media-agent {LISTEN_HOST}:{LISTEN_PORT} (state: {STATE_DB})")
    server.serve_forever()
