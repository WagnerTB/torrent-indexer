#!/usr/bin/env python3
import ipaddress
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from system_status import request_throttle_clear, status_payload, storage_payload

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
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "ffprobe")
BAZARR_ALLOWED_PATHS = (
    "/api/episodes",
    "/api/movies",
    "/api/series",
    "/api/subtitles",
    "/api/system/jobs",
    "/api/system/logs",
)

RADARR_URL = os.getenv("RADARR_URL", "http://127.0.0.1:7878").rstrip("/")
SONARR_URL = os.getenv("SONARR_URL", "http://127.0.0.1:8989").rstrip("/")
RADARR_CONFIG = os.getenv("RADARR_CONFIG", "/radarr/config.xml")
SONARR_CONFIG = os.getenv("SONARR_CONFIG", "/sonarr/config.xml")
RADARR_DUBBED_PROFILE = int(os.getenv("RADARR_DUBBED_PROFILE", "8"))
SONARR_DUBBED_PROFILE = int(os.getenv("SONARR_DUBBED_PROFILE", "9"))
RADARR_ORIGINAL_PROFILE = int(os.getenv("RADARR_ORIGINAL_PROFILE", "7"))
SONARR_ORIGINAL_PROFILE = int(os.getenv("SONARR_ORIGINAL_PROFILE", "7"))
RADARR_ANIME_LEGENDADO_PROFILE = int(os.getenv("RADARR_ANIME_LEGENDADO_PROFILE", "9"))
RADARR_ANIME_DUBBED_PROFILE = int(os.getenv("RADARR_ANIME_DUBBED_PROFILE", "10"))
SONARR_ANIME_LEGENDADO_PROFILE = int(os.getenv("SONARR_ANIME_LEGENDADO_PROFILE", "8"))
SONARR_ANIME_DUBBED_PROFILE = int(os.getenv("SONARR_ANIME_DUBBED_PROFILE", "10"))

SEERR_URL = os.getenv("SEERR_URL", "http://127.0.0.1:5055").rstrip("/")
SEERR_CONFIG = os.getenv("SEERR_CONFIG", "/seerr/settings.json")
SEERR_TIMEOUT = int(os.getenv("SEERR_TIMEOUT_SECONDS", "15"))

STATE_DIR = os.getenv("STATE_DIR", "/state")
STATE_DB = os.path.join(STATE_DIR, "requests.db")
STORAGE_CONFIG = os.getenv("STORAGE_CONFIG", "").strip()

# --- Packs por temporada (Fase 1) -----------------------------------------
PACK_WORKER_ENABLED = os.getenv("PACK_WORKER_ENABLED", "1").strip().lower() not in (
    "0", "false", "no", "off",
)
PACK_WORKER_DRY_RUN = os.getenv("PACK_WORKER_DRY_RUN", "0").strip().lower() in (
    "1", "true", "yes", "on",
)
PACK_CONCURRENCY = max(1, int(os.getenv("SEASON_SEARCH_CONCURRENCY", "2")))
PACK_MAX_ATTEMPTS = max(1, int(os.getenv("PACK_MAX_ATTEMPTS", "3")))
PACK_RETRY_HOURS = max(0.1, float(os.getenv("PACK_RETRY_HOURS", "6")))
PACK_POLL_SECONDS = max(10, int(os.getenv("PACK_WORKER_POLL_SECONDS", "60")))
PACK_RELEASE_CACHE_SECONDS = max(60, int(os.getenv("PACK_RELEASE_CACHE_SECONDS", "1800")))
PACK_GRAB_GRACE_SECONDS = max(60, int(os.getenv("PACK_GRAB_GRACE_SECONDS", "900")))


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


def bazarr_path_allowed(path):
    if not path or "\\" in path or ".." in path:
        return False
    try:
        base = urllib.parse.urlsplit(path).path
    except ValueError:
        return False
    if not base.startswith("/api/"):
        return False
    return any(base == allowed or base.startswith(allowed + "/") for allowed in BAZARR_ALLOWED_PATHS)


def bazarr_proxy(path, method="GET"):
    if not bazarr_path_allowed(path):
        return 403, "application/json", b'{"error":"path not allowed"}'
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

                CREATE TABLE IF NOT EXISTS pack_jobs (
                    key TEXT PRIMARY KEY,
                    tvdb_id INTEGER NOT NULL,
                    series_id INTEGER,
                    season INTEGER NOT NULL,
                    profile_id INTEGER,
                    profile_name TEXT,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    next_attempt_at TEXT,
                    last_attempt_at TEXT,
                    last_checked_at TEXT,
                    queue_pos INTEGER,
                    release_guid TEXT,
                    release_indexer_id INTEGER,
                    release_title TEXT,
                    release_size INTEGER,
                    release_seeders INTEGER,
                    release_quality TEXT,
                    aired INTEGER,
                    files INTEGER,
                    missing INTEGER,
                    audio_status TEXT,
                    error TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    hidden_at TEXT,
                    meta TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_pack_jobs_tvdb_season
                    ON pack_jobs(tvdb_id, season);
                CREATE INDEX IF NOT EXISTS idx_pack_jobs_status ON pack_jobs(status);
                CREATE INDEX IF NOT EXISTS idx_pack_jobs_next ON pack_jobs(next_attempt_at);

                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    key TEXT,
                    tvdb_id INTEGER,
                    series_id INTEGER,
                    season INTEGER,
                    title TEXT,
                    message TEXT,
                    action TEXT,
                    payload TEXT,
                    created_at TEXT NOT NULL,
                    read_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);
                CREATE INDEX IF NOT EXISTS idx_notifications_key ON notifications(kind, key);

                CREATE TABLE IF NOT EXISTS notification_reads (
                    notification_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    read_at TEXT NOT NULL,
                    PRIMARY KEY (notification_id, user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_notification_reads_user
                    ON notification_reads(user_id, read_at);

                CREATE TABLE IF NOT EXISTS devices (
                    user_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    fcm_token TEXT NOT NULL,
                    platform TEXT,
                    updated_at TEXT NOT NULL,
                    last_seen_at TEXT,
                    PRIMARY KEY (user_id, device_id)
                );

                CREATE TABLE IF NOT EXISTS notification_pushes (
                    notification_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    error TEXT,
                    PRIMARY KEY (notification_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS pack_worker_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT
                );
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
    parser.add_argument("--audio-check", action="store_true")
    parser.add_argument("--kind", choices=("movie", "series"))
    parser.add_argument("--id", type=int)
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
    if args.audio_check:
        result = arr_audio_check(args.kind, args.id, not (args.kind and args.id))
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
                or (item["kind"] == "movie" and item.get("profileId") in (RADARR_DUBBED_PROFILE, RADARR_ANIME_DUBBED_PROFILE))
                or (item["kind"] == "series" and item.get("profileId") in (SONARR_DUBBED_PROFILE, SONARR_ANIME_DUBBED_PROFILE))
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
    try:
        if kind == "movie":
            key = arr_key(RADARR_CONFIG)
            item = arr_request(RADARR_URL, key, f"/api/v3/movie/{int(item_id)}")
            current = _as_int(item.get("qualityProfileId"))
            anime = current in (RADARR_ANIME_LEGENDADO_PROFILE, RADARR_ANIME_DUBBED_PROFILE)
            profile = RADARR_ANIME_LEGENDADO_PROFILE if anime else RADARR_ORIGINAL_PROFILE
        elif kind == "series":
            key = arr_key(SONARR_CONFIG)
            item = arr_request(SONARR_URL, key, f"/api/v3/series/{int(item_id)}")
            current = _as_int(item.get("qualityProfileId"))
            anime = (
                item.get("seriesType") == "anime"
                or "/animes" in (item.get("rootFolderPath") or "").lower()
                or current in (SONARR_ANIME_LEGENDADO_PROFILE, SONARR_ANIME_DUBBED_PROFILE)
            )
            profile = SONARR_ANIME_LEGENDADO_PROFILE if anime else SONARR_ORIGINAL_PROFILE
        else:
            return {"ok": False, "error": "kind invalido"}
        return arr_search(kind, item_id, profile)
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


_AUDIO_LANG_ALIASES = {
    "en": {"en", "eng", "english"},
    "pt": {"pt", "por", "pb", "pt-br", "ptbr", "portuguese", "portugues", "português"},
    "ja": {"ja", "jpn", "jp", "japanese"},
    "es": {"es", "spa", "spanish", "lat", "latino", "castellano"},
    "fr": {"fr", "fra", "fre", "french", "francais", "français"},
}

_VERDICT_PRIORITY = {
    "ok": 0,
    "skipped": 1,
    "ok-multi": 2,
    "unknown": 3,
    "wrong-default": 4,
    "mismatch": 5,
    "no-audio": 6,
    "no-file": 7,
}


def _norm_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).lower()


def _audio_lang_code(value):
    code = str(value or "").strip().lower()
    if not code or code in {"und", "unknown", "none", "null"}:
        return "und"
    for canonical, aliases in _AUDIO_LANG_ALIASES.items():
        if code in aliases:
            return canonical
    return code


_AUDIO_TITLE_WORDS = {
    "en": {"english", "eng"},
    "pt": {"portuguese", "portugues", "português", "pt-br", "ptbr", "brazilian"},
    "ja": {"japanese", "jpn"},
    "es": {"spanish", "espanol", "español", "latino", "castellano"},
    "fr": {"french", "francais", "français"},
}


def _audio_lang_from_title(title):
    text = _norm_text(title)
    if not text:
        return ""
    for canonical, words in _AUDIO_TITLE_WORDS.items():
        if any(word in text for word in words):
            return canonical
    return ""


def _expected_audio(profile_name):
    name = _norm_text(profile_name)
    if "anime" in name and "legendado" in name:
        return {"ja"}
    if "anime" in name and "dublado" in name:
        return {"pt"}
    if "legendado" in name:
        return {"en"}
    if "dublado" in name:
        return {"pt"}
    return set()


def _ffprobe_audio(path):
    if not path or not os.path.exists(path):
        return None
    executable = shutil.which(FFPROBE_PATH)
    if not executable:
        return None
    command = [
        executable,
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index,codec_name:stream_tags=language,title:stream_disposition=default,forced",
        "-of", "json",
        path,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    streams = []
    for stream in payload.get("streams") or []:
        disposition = stream.get("disposition") or {}
        tags = stream.get("tags") or {}
        language = _audio_lang_code(tags.get("language"))
        title = tags.get("title") or ""
        if language == "und":
            language = _audio_lang_from_title(title) or "und"
        streams.append({
            "index": _as_int(stream.get("index")),
            "language": language,
            "title": title,
            "default": bool(disposition.get("default")),
            "forced": bool(disposition.get("forced")),
            "codec": stream.get("codec_name") or "",
        })
    return streams or None


def _media_info_audio(media_info):
    if not media_info:
        return []
    raw = str(media_info.get("audioLanguages") or "")
    separators = raw.replace(";", ",").replace("/", ",").replace("|", ",")
    codes = [
        _audio_lang_code(part)
        for part in separators.split(",")
        if part.strip()
    ]
    count = max(_as_int(media_info.get("audioStreamCount")) or 0, len(codes))
    if not count:
        return []
    streams = []
    for index in range(count):
        streams.append({
            "index": index,
            "language": codes[index] if index < len(codes) else "und",
            "default": index == 0,
            "forced": False,
            "codec": str(media_info.get("audioCodec") or ""),
        })
    return streams


def _audio_streams_for_file(media_file):
    path = media_file.get("path") or ""
    streams = _ffprobe_audio(path)
    if streams:
        return streams, "ffprobe"
    return _media_info_audio(media_file.get("mediaInfo") or {}), "mediaInfo"


def _audio_verdict(expected, streams):
    if not streams:
        return "no-audio", "Nenhuma faixa de áudio encontrada"
    if not expected:
        return "skipped", "Perfil sem expectativa de áudio"
    languages = [stream.get("language") or "und" for stream in streams]
    known = sorted({language for language in languages if language != "und"})
    default_stream = next((stream for stream in streams if stream.get("default")), streams[0])
    default_lang = default_stream.get("language") or "und"
    expected_text = ", ".join(sorted(expected))
    if not known:
        return "unknown", "Faixas sem idioma identificado (und); confira manualmente"
    if default_lang == "und":
        return "unknown", "Faixa padrão sem idioma; confira manualmente"
    if default_lang not in expected:
        if any(language in expected for language in known):
            return "wrong-default", f"Áudio esperado ({expected_text}) existe, mas a faixa padrão é {default_lang}"
        return "mismatch", f"Áudio esperado ({expected_text}) ausente; encontrado: {', '.join(known)}"
    if len(known) > 1:
        return "ok-multi", f"Faixa padrão correta ({default_lang}); há outras faixas: {', '.join(known)}"
    return "ok", f"Faixa padrão: {default_lang}"


def _profile_names(base, key):
    return {
        _as_int(profile.get("id")): profile.get("name") or ""
        for profile in _quality_profiles(base, key)
    }


def _audio_check_movie(movie, profile_names):
    profile_id = _as_int(movie.get("qualityProfileId"))
    profile_name = profile_names.get(profile_id, "")
    media_file = movie.get("movieFile") or {}
    result = {
        "kind": "movie",
        "id": movie.get("id"),
        "title": movie.get("title") or "",
        "year": movie.get("year"),
        "profileId": profile_id,
        "profileName": profile_name,
        "originalLanguage": (movie.get("originalLanguage") or {}).get("name") or "",
        "expected": sorted(_expected_audio(profile_name)),
        "hasFile": bool(media_file),
    }
    if not media_file:
        result.update({"verdict": "no-file", "message": "Sem arquivo importado", "streams": [], "actual": []})
        return result
    streams, source = _audio_streams_for_file(media_file)
    verdict, message = _audio_verdict(set(result["expected"]), streams)
    result.update({
        "file": media_file.get("path") or "",
        "source": source,
        "streams": streams,
        "actual": sorted({stream.get("language") or "und" for stream in streams}),
        "verdict": verdict,
        "message": message,
    })
    return result


def _audio_check_series(series, profile_names, key):
    profile_id = _as_int(series.get("qualityProfileId"))
    profile_name = profile_names.get(profile_id, "")
    expected = _expected_audio(profile_name)
    stats = series.get("statistics") or {}
    result = {
        "kind": "series",
        "id": series.get("id"),
        "title": series.get("title") or "",
        "year": series.get("year"),
        "profileId": profile_id,
        "profileName": profile_name,
        "originalLanguage": (series.get("originalLanguage") or {}).get("name") or "",
        "expected": sorted(expected),
        "hasFile": bool(stats.get("episodeFileCount")),
    }
    files = []
    if result["hasFile"]:
        files = arr_request(SONARR_URL, key, f"/api/v3/episodefile?seriesId={int(series.get('id'))}") or []
    if not files:
        result.update({"verdict": "no-file", "message": "Sem arquivo importado", "files": []})
        return result
    checks = []
    for media_file in files:
        streams, source = _audio_streams_for_file(media_file)
        verdict, message = _audio_verdict(expected, streams)
        checks.append({
            "file": media_file.get("path") or "",
            "season": media_file.get("seasonNumber"),
            "source": source,
            "streams": streams,
            "actual": sorted({stream.get("language") or "und" for stream in streams}),
            "verdict": verdict,
            "message": message,
        })
    worst = max((check["verdict"] for check in checks), key=lambda value: _VERDICT_PRIORITY.get(value, 9))
    counts = {}
    for check in checks:
        counts[check["verdict"]] = counts.get(check["verdict"], 0) + 1
    result.update({
        "files": checks,
        "actual": sorted({
            stream.get("language") or "und"
            for check in checks
            for stream in check.get("streams") or []
        }),
        "verdict": worst,
        "message": ", ".join(f"{name}: {count}" for name, count in sorted(counts.items())),
    })
    return result


def _audio_summary(results, errors):
    counts = {}
    problems = []
    for item in results:
        verdict = item.get("verdict") or "unknown"
        counts[verdict] = counts.get(verdict, 0) + 1
        if verdict not in ("ok", "ok-multi", "skipped"):
            problems.append(item)
    payload = {
        "ok": True,
        "total": len(results),
        "counts": counts,
        "problems": problems,
        "errors": errors,
        "ffprobe": bool(shutil.which(FFPROBE_PATH)),
    }
    if len(results) == 1:
        payload["item"] = results[0]
    return payload


def arr_audio_check(kind=None, item_id=None, all_items=False):
    try:
        if kind not in (None, "movie", "series"):
            return {"ok": False, "error": "kind invalido"}
        results = []
        errors = []
        if kind and item_id:
            if kind == "movie":
                key = arr_key(RADARR_CONFIG)
                movie = arr_request(RADARR_URL, key, f"/api/v3/movie/{int(item_id)}")
                results.append(_audio_check_movie(movie, _profile_names(RADARR_URL, key)))
            else:
                key = arr_key(SONARR_CONFIG)
                series = arr_request(SONARR_URL, key, f"/api/v3/series/{int(item_id)}")
                results.append(_audio_check_series(series, _profile_names(SONARR_URL, key), key))
        elif all_items or kind:
            if kind in (None, "movie"):
                key = arr_key(RADARR_CONFIG)
                if key:
                    names = _profile_names(RADARR_URL, key)
                    for movie in arr_request(RADARR_URL, key, "/api/v3/movie") or []:
                        if movie.get("movieFile"):
                            results.append(_audio_check_movie(movie, names))
            if kind in (None, "series"):
                key = arr_key(SONARR_CONFIG)
                if key:
                    names = _profile_names(SONARR_URL, key)
                    series_list = [
                        series for series in (arr_request(SONARR_URL, key, "/api/v3/series") or [])
                        if (series.get("statistics") or {}).get("episodeFileCount")
                    ]
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        futures = [
                            pool.submit(_audio_check_series, series, names, key)
                            for series in series_list
                        ]
                        for future in futures:
                            try:
                                results.append(future.result())
                            except Exception as error:
                                errors.append(f"{type(error).__name__}: {error}")
        else:
            return {"ok": False, "error": "informe kind+id ou all=1"}
        return _audio_summary(results, errors)
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}





def _import_fmt(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return ("%.0f %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024
    return "%.1f PB" % n


def active_imports():
    """Detect files currently being copied into the media library (growing files)."""
    dirs = ["/media/movies", "/media/series", "/media/animes", "/media/Suits"]
    now = time.time()
    found = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for name in files:
                fp = os.path.join(root, name)
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                if now - st.st_mtime > 180:
                    continue
                s1 = st.st_size
                time.sleep(0.4)
                try:
                    s2 = os.stat(fp).st_size
                except OSError:
                    continue
                if s2 <= s1:
                    continue
                found.append({
                    "name": name,
                    "library": os.path.basename(d),
                    "size": s2,
                    "sizeLabel": _import_fmt(s2),
                    "rateBps": int((s2 - s1) / 0.4),
                    "rateLabel": _import_fmt((s2 - s1) / 0.4) + "/s",
                })
    found.sort(key=lambda x: -x["size"])
    return {"ok": True, "active": found}


def migration_status():
    """Return the running data-migration progress (if any)."""
    for path in ("/media/.migration-status.json", "/migration/status.json"):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data["path"] = path
                return data
        except (OSError, ValueError):
            continue
    return {"phase": "idle", "percent": None}

# ---------------------------------------------------------------------------
# Packs por temporada (Fase 1)
#
# Regras fechadas (PLANO_PACKS_TEMPORADA.md):
#   - só pack completo (fullSeason), nunca busca de episódio solto;
#   - aceito = !rejected && downloadAllowed && temporada correta && sem multi-temporada;
#   - ranking: seeders desc, qualidade desc, tamanho desc;
#   - fila com concorrência 2, 3 tentativas com intervalo de 6 h;
#   - temporada no ar: desmonitorar e aguardar o finale;
#   - exceção 7/8: fechar com 1 episódio solto (manual, via endpoint).
# ---------------------------------------------------------------------------

PACK_STATUSES = (
    "queued", "waiting_finale", "searching", "pack_found", "downloading",
    "importing", "complete", "incomplete", "no_pack", "failed", "ignored",
)
PACK_ACTIVE_STATUSES = ("pack_found", "downloading", "importing")

PACK_STATUS_LABELS = {
    "queued": "Na fila para procura",
    "waiting_finale": "Aguardando finalização da exibição",
    "searching": "Procurando pack",
    "pack_found": "Pack encontrado",
    "downloading": "Baixando",
    "importing": "Importando",
    "complete": "Completa",
    "incomplete": "Incompleta",
    "no_pack": "Sem pack completo",
    "failed": "Falhou",
    "ignored": "Ignorado",
}

PACK_JOB_FIELDS = (
    "tvdb_id", "series_id", "season", "profile_id", "profile_name", "status",
    "attempts", "max_attempts", "next_attempt_at", "last_attempt_at",
    "last_checked_at", "queue_pos", "release_guid", "release_indexer_id",
    "release_title", "release_size", "release_seeders", "release_quality",
    "aired", "files", "missing", "audio_status", "error", "hidden_at", "meta",
)

# Packs que cobrem mais de uma temporada (S01-S09, S01 S08, Complete Series...).
PACK_MULTI_SEASON_RE = re.compile(
    r"(\bS\d{1,2}\s*[-\u2013\u2014]\s*S\d{1,2}\b"
    r"|\bS\d{1,2}\s+S\d{1,2}\b"
    r"|\bSEASON\s*\d{1,2}\s*[-\u2013\u2014]\s*\d{1,2}\b"
    r"|\bTEMPORADAS?\s*\d{1,2}\s*[-\u2013\u2014]\s*\d{1,2}\b"
    r"|\bCOMPLETE\s+SERIES\b"
    r"|COMPLETA\s+S[E\u00c9]RIE)",
    re.I,
)

_pack_state = {
    "started_at": None,
    "last_tick_at": None,
    "last_error": "",
    "thread": None,
}
_pack_running = {}
_pack_executor = None
_pack_lock = threading.Lock()
_pack_episode_cache = {}
_pack_release_cache = {}


def _parse_iso(value):
    if not value:
        return None
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _iso_in(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _pack_key(tvdb_id, season):
    return f"tvdb:{int(tvdb_id)}:s{int(season)}"


def _pack_job_from_row(row):
    job = {name: row[name] for name in row.keys()}
    job["meta"] = _json_load(job.get("meta")) if job.get("meta") else {}
    return job


def _pack_job_get(key):
    row = _db_one("SELECT * FROM pack_jobs WHERE key = ?", (key,))
    return _pack_job_from_row(row) if row else None


def _pack_job_upsert(record):
    key = str(record.get("key") or "").strip()
    if not key:
        return None
    values = {}
    for field in PACK_JOB_FIELDS:
        if field in record:
            value = record[field]
            if field == "meta" and isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            values[field] = value
    now = _now_iso()
    with _db_lock:
        conn = _db_connect()
        try:
            row = conn.execute("SELECT * FROM pack_jobs WHERE key = ?", (key,)).fetchone()
            if row is None:
                values.setdefault("status", "queued")
                values.setdefault("attempts", 0)
                values.setdefault("max_attempts", PACK_MAX_ATTEMPTS)
                values.setdefault("created_at", now)
                values["key"] = key
                values["updated_at"] = now
                cols = ",".join(values.keys())
                marks = ",".join("?" for _ in values)
                conn.execute(
                    f"INSERT INTO pack_jobs ({cols}) VALUES ({marks})",
                    list(values.values()),
                )
            else:
                updates = {name: value for name, value in values.items() if row[name] != value}
                if updates:
                    updates["updated_at"] = now
                    sets = ",".join(f"{name}=?" for name in updates)
                    conn.execute(
                        f"UPDATE pack_jobs SET {sets} WHERE key = ?",
                        list(updates.values()) + [key],
                    )
            conn.commit()
        finally:
            conn.close()
    return _pack_job_get(key)


def _pack_job_update(key, meta_patch=None, **fields):
    job = _pack_job_get(key)
    if not job:
        return None
    record = {"key": key, **fields}
    if meta_patch is not None:
        meta = dict(job.get("meta") or {})
        meta.update(meta_patch)
        record["meta"] = meta
    return _pack_job_upsert(record)


def _pack_state_get(key, default=None):
    row = _db_one("SELECT value FROM pack_worker_state WHERE key = ?", (key,))
    return row["value"] if row else default


def _pack_state_set(key, value):
    with _db_lock:
        conn = _db_connect()
        try:
            conn.execute(
                "INSERT INTO pack_worker_state (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key, str(value), _now_iso()),
            )
            conn.commit()
        finally:
            conn.close()


def _pack_quality_size_cap_gb(name):
    """Teto grosseiro de GB por episódio (guarda contra mapeamento quebrado)."""
    quality = (name or "").lower()
    if "2160" in quality or "4k" in quality:
        return 15.0
    if "1080" in quality:
        return 4.0
    if "720" in quality:
        return 2.0
    return 1.0


def pack_evaluate_release(release, season, tvdb_id=None, expected_episodes=None):
    """Motivos para recusar um release como pack da temporada (vazio = aceito)."""
    reasons = []
    release = release or {}
    if not release.get("fullSeason"):
        reasons.append("nao_e_pack_temporada")
    if release.get("rejected"):
        reasons.append("rejeitado_sonarr")
    if release.get("downloadAllowed") is False:
        reasons.append("download_nao_permitido")
    mapped = _as_int(release.get("mappedSeasonNumber"))
    if mapped is not None and mapped != _as_int(season):
        reasons.append(f"temporada_incorreta:{mapped}")
    if PACK_MULTI_SEASON_RE.search(str(release.get("title") or "")):
        reasons.append("multi_temporada")
    release_tvdb = _as_int(release.get("tvdbId"))
    if tvdb_id and release_tvdb and release_tvdb != _as_int(tvdb_id):
        reasons.append("tvdb_divergente")
    if expected_episodes:
        size = _as_float(release.get("size"))
        per_episode = size / 1e9 / int(expected_episodes)
        quality = ((release.get("quality") or {}).get("quality") or {}).get("name")
        cap = _pack_quality_size_cap_gb(quality)
        if per_episode > cap:
            reasons.append(f"tamanho_por_episodio:{per_episode:.2f}>{cap:g}")
    return reasons


def pack_rank_releases(releases):
    return sorted(
        releases or [],
        key=lambda item: (
            -_as_float(item.get("seeders")),
            -_as_float(item.get("qualityWeight")),
            -_as_float(item.get("size")),
        ),
    )


def pack_filter_releases(releases, season, tvdb_id=None, expected_episodes=None):
    """(aceitos ranqueados, recusados com motivo)."""
    accepted = []
    skipped = []
    for release in releases or []:
        reasons = pack_evaluate_release(release, season, tvdb_id, expected_episodes)
        if reasons:
            skipped.append({
                "title": release.get("title") or "",
                "seeders": _as_int(release.get("seeders")),
                "size": _as_int(release.get("size")),
                "reasons": reasons,
            })
        else:
            accepted.append(release)
    return pack_rank_releases(accepted), skipped


def _pack_episode_aired(episode, now=None):
    now = now or datetime.now(timezone.utc)
    parsed = _parse_iso(episode.get("airDateUtc") or episode.get("airDate"))
    if parsed is None:
        return True
    return parsed <= now


def pack_episode_stats(episodes, season, now=None):
    season = _as_int(season)
    season_episodes = [
        episode for episode in (episodes or [])
        if _as_int(episode.get("seasonNumber")) == season
    ]
    aired = [episode for episode in season_episodes if _pack_episode_aired(episode, now)]
    future = [episode for episode in season_episodes if not _pack_episode_aired(episode, now)]
    files = [episode for episode in aired if episode.get("hasFile")]
    dates = [
        episode.get("airDateUtc") or episode.get("airDate") or ""
        for episode in season_episodes
    ]
    dates = [value for value in dates if value]
    return {
        "episodeCount": len(season_episodes),
        "aired": len(aired),
        "files": len(files),
        "missing": max(0, len(aired) - len(files)),
        "future": len(future),
        "monitored": sum(1 for episode in season_episodes if episode.get("monitored")),
        "lastAirDate": max((episode.get("airDateUtc") or episode.get("airDate") or "" for episode in aired), default=""),
        "finalAirDate": max(dates, default=""),
        "nextAirDate": min(dates, default=""),
    }


def _pack_series_episodes(series_id, refresh=False):
    series_id = _as_int(series_id)
    if not series_id:
        return []
    now = time.time()
    cached = _pack_episode_cache.get(series_id)
    if cached and not refresh and now - cached[0] < 30:
        return cached[1]
    key = arr_key(SONARR_CONFIG)
    if not key:
        return []
    raw = arr_request(
        SONARR_URL, key, f"/api/v3/episode?seriesId={series_id}&includeEpisodeFile=true"
    ) or []
    episodes = []
    for episode in raw:
        episodes.append({
            "id": _as_int(episode.get("id")),
            "seasonNumber": _as_int(episode.get("seasonNumber")) or 0,
            "episodeNumber": _as_int(episode.get("episodeNumber")) or 0,
            "absoluteEpisodeNumber": _as_int(episode.get("absoluteEpisodeNumber")),
            "title": episode.get("title") or "",
            "airDateUtc": episode.get("airDateUtc") or "",
            "airDate": episode.get("airDate") or "",
            "monitored": bool(episode.get("monitored")),
            "hasFile": bool(episode.get("hasFile")),
        })
    _pack_episode_cache[series_id] = (now, episodes)
    return episodes


def _pack_series_by_tvdb(tvdb_id, refresh=False):
    tvdb_id = _as_int(tvdb_id)
    if not tvdb_id:
        return None
    for series in _sonarr_series(refresh=refresh):
        if _as_int(series.get("tvdbId")) == tvdb_id:
            return series
    return None


def _pack_set_season_flag(series_id, season, monitored):
    """Atualiza `seasons[].monitored` na série (o Sonarr não faz isso por episódio)."""
    series_id = _as_int(series_id)
    season = _as_int(season)
    if not series_id or season is None:
        return False
    key = arr_key(SONARR_CONFIG)
    if not key:
        return False
    series = arr_request(SONARR_URL, key, f"/api/v3/series/{series_id}") or {}
    changed = False
    for row in series.get("seasons") or []:
        if _as_int(row.get("seasonNumber")) == season and bool(row.get("monitored")) != monitored:
            row["monitored"] = monitored
            changed = True
    if changed:
        arr_request(SONARR_URL, key, f"/api/v3/series/{series_id}", "PUT", series)
        _sonarr_series_cache.update({"ts": 0.0, "series": []})
    return changed


def _pack_monitored_seasons():
    """Temporadas monitoradas de fato (flag da temporada ou episódio monitorado)."""
    try:
        series_list = _sonarr_series(refresh=True)
    except Exception:
        return []
    found = {}
    for series in series_list:
        series_id = _as_int(series.get("id"))
        if not series_id:
            continue
        flagged = []
        for row in series.get("seasons") or []:
            season = _as_int(row.get("seasonNumber"))
            if season is None or season <= 0 or not row.get("monitored"):
                continue
            flagged.append(season)
            found[(series_id, season)] = series
        if series.get("monitored") and not flagged:
            # Seerr pode monitorar episódios sem marcar a temporada.
            try:
                episodes = _pack_series_episodes(series_id)
            except Exception:
                continue
            seasons = {
                _as_int(episode.get("seasonNumber")) for episode in episodes
                if episode.get("monitored")
            }
            for season in seasons:
                if season and season > 0:
                    found[(series_id, season)] = series
    return [
        {"series": series, "season": season}
        for (series_id, season), series in found.items()
    ]


def _pack_fetch_releases(series_id, season, refresh=False):
    cache_key = (_as_int(series_id), _as_int(season))
    now = time.time()
    cached = _pack_release_cache.get(cache_key)
    if cached and not refresh and now - cached[0] < PACK_RELEASE_CACHE_SECONDS:
        return cached[1]
    key = arr_key(SONARR_CONFIG)
    if not key:
        raise RuntimeError("API key do Sonarr não encontrada")
    raw = arr_request(
        SONARR_URL,
        key,
        f"/api/v3/release?seriesId={cache_key[0]}&seasonNumber={cache_key[1]}",
        timeout=180,
    ) or []
    _pack_release_cache[cache_key] = (now, raw)
    return raw


def _pack_queue_map():
    key = arr_key(SONARR_CONFIG)
    if not key:
        return {}
    payload = _safe_arr_request(
        SONARR_URL, key,
        "/api/v3/queue?page=1&pageSize=250&includeUnknownSeriesItems=true",
        20, {},
    ) or {}
    result = {}
    for record in payload.get("records") or []:
        if record.get("title"):
            result[str(record["title"])] = record
        if record.get("downloadId"):
            result[str(record["downloadId"])] = record
    return result


def _pack_queue_progress(record):
    size = _as_float(record.get("size"))
    left = _as_float(record.get("sizeleft"))
    if size <= 0:
        return 0
    return max(0, min(100, round(((size - left) / size) * 100)))


def _pack_status_label(job):
    status = job.get("status") or "queued"
    label = PACK_STATUS_LABELS.get(status, status)
    meta = job.get("meta") or {}
    if status == "downloading" and meta.get("progress") is not None:
        return f"{label} {meta['progress']}%"
    if status in ("importing", "complete", "incomplete"):
        return f"{label} {job.get('files') or 0}/{job.get('aired') or 0}"
    return label


def _pack_job_public(job, queue_pos=None):
    meta = job.get("meta") or {}
    return {
        "key": job.get("key"),
        "tvdbId": job.get("tvdb_id"),
        "seriesId": job.get("series_id"),
        "season": job.get("season"),
        "status": job.get("status"),
        "statusLabel": _pack_status_label(job),
        "attempt": job.get("attempts") or 0,
        "maxAttempts": job.get("max_attempts") or PACK_MAX_ATTEMPTS,
        "nextAttemptAt": job.get("next_attempt_at"),
        "queuePosition": queue_pos,
        "title": meta.get("title") or "",
        "releaseTitle": job.get("release_title") or "",
        "sizeGb": round((job.get("release_size") or 0) / 1e9, 2) if job.get("release_size") else None,
        "seeders": job.get("release_seeders"),
        "quality": job.get("release_quality"),
        "aired": job.get("aired"),
        "files": job.get("files"),
        "missing": job.get("missing"),
        "audioStatus": job.get("audio_status"),
        "progress": meta.get("progress"),
        "lastAirDate": meta.get("lastAirDate"),
        "dryRun": bool(meta.get("dryRun")),
        "error": job.get("error") or "",
        "updatedAt": job.get("updated_at"),
    }


def _pack_notify(kind, severity, job, title, message, action="", dedupe_seconds=86400):
    meta = (job or {}).get("meta") or {}
    return _notify_create(
        kind,
        severity,
        key=(job or {}).get("key"),
        tvdb_id=(job or {}).get("tvdb_id"),
        series_id=(job or {}).get("series_id"),
        season=(job or {}).get("season"),
        title=title,
        message=message,
        action=action,
        payload={
            "key": (job or {}).get("key"),
            "seriesTitle": meta.get("title") or "",
            "season": (job or {}).get("season"),
            "releaseTitle": (job or {}).get("release_title") or "",
        },
        dedupe_seconds=dedupe_seconds,
    )


# --- Notificações / dispositivos ------------------------------------------


def _notify_create(kind, severity, key=None, tvdb_id=None, series_id=None, season=None,
                   title="", message="", action="", payload=None, dedupe_seconds=86400):
    now = datetime.now(timezone.utc)
    created = now.isoformat().replace("+00:00", "Z")
    cutoff = (now - timedelta(seconds=dedupe_seconds)).isoformat().replace("+00:00", "Z")
    with _db_lock:
        conn = _db_connect()
        try:
            if key and dedupe_seconds:
                row = conn.execute(
                    "SELECT n.id FROM notifications n WHERE n.kind = ? AND n.key = ? "
                    "AND n.created_at >= ? AND NOT EXISTS ("
                    "  SELECT 1 FROM notification_reads r WHERE r.notification_id = n.id"
                    ") ORDER BY n.id DESC LIMIT 1",
                    (kind, key, cutoff),
                ).fetchone()
                if row:
                    return row["id"]
            cursor = conn.execute(
                "INSERT INTO notifications "
                "(kind, severity, key, tvdb_id, series_id, season, title, message, action, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    kind, severity, key, tvdb_id, series_id, season, title, message,
                    action, json.dumps(payload or {}, ensure_ascii=False), created,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()


def _notification_public(row, user_id=None):
    item = {
        "id": row["id"],
        "kind": row["kind"],
        "severity": row["severity"],
        "key": row["key"],
        "tvdbId": row["tvdb_id"],
        "seriesId": row["series_id"],
        "season": row["season"],
        "title": row["title"],
        "message": row["message"],
        "action": row["action"],
        "payload": _json_load(row["payload"]) if row["payload"] else {},
        "createdAt": row["created_at"],
        "readAt": row["user_read_at"] if "user_read_at" in row.keys() else None,
    }
    item["read"] = bool(item["readAt"])
    return item


def notifications_payload(user_id, limit=50, unread_only=False):
    user_id = str(user_id or "").strip()
    if not user_id:
        return {"ok": False, "error": "user_id obrigatório"}
    try:
        limit = max(1, min(200, int(limit)))
    except (TypeError, ValueError):
        limit = 50
    rows = _db_rows(
        "SELECT n.*, r.read_at AS user_read_at FROM notifications n "
        "LEFT JOIN notification_reads r "
        "  ON r.notification_id = n.id AND r.user_id = ? "
        "ORDER BY n.id DESC LIMIT ?",
        (user_id, limit),
    )
    items = [_notification_public(row) for row in rows]
    if unread_only:
        items = [item for item in items if not item["read"]]
    unread = _db_one(
        "SELECT COUNT(*) AS total FROM notifications n WHERE NOT EXISTS ("
        "  SELECT 1 FROM notification_reads r WHERE r.notification_id = n.id AND r.user_id = ?"
        ")",
        (user_id,),
    )
    return {"ok": True, "notifications": items, "unread": (unread["total"] if unread else 0)}


def notifications_mark_read(notification_id, user_id):
    try:
        notification_id = int(notification_id)
    except (TypeError, ValueError):
        return {"ok": False, "error": "id inválido"}
    user_id = str(user_id or "").strip()
    if not user_id:
        return {"ok": False, "error": "user_id obrigatório"}
    with _db_lock:
        conn = _db_connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO notification_reads (notification_id, user_id, read_at) "
                "VALUES (?, ?, ?)",
                (notification_id, user_id, _now_iso()),
            )
            conn.commit()
        finally:
            conn.close()
    return {"ok": True, "id": notification_id}


def notifications_mark_all_read(user_id):
    user_id = str(user_id or "").strip()
    if not user_id:
        return {"ok": False, "error": "user_id obrigatório"}
    with _db_lock:
        conn = _db_connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO notification_reads (notification_id, user_id, read_at) "
                "SELECT id, ?, ? FROM notifications",
                (user_id, _now_iso()),
            )
            conn.commit()
        finally:
            conn.close()
    return {"ok": True}


def notifications_mark_pushed(notification_id, user_id, error=""):
    try:
        notification_id = int(notification_id)
    except (TypeError, ValueError):
        return {"ok": False, "error": "id inválido"}
    user_id = str(user_id or "").strip()
    if not user_id:
        return {"ok": False, "error": "user_id obrigatório"}
    with _db_lock:
        conn = _db_connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO notification_pushes (notification_id, user_id, sent_at, error) "
                "VALUES (?, ?, ?, ?)",
                (notification_id, user_id, _now_iso(), error or ""),
            )
            conn.commit()
        finally:
            conn.close()
    return {"ok": True}


def devices_upsert(payload):
    user_id = str((payload or {}).get("user_id") or "").strip()
    device_id = str((payload or {}).get("device_id") or "").strip()
    token = str((payload or {}).get("fcm_token") or "").strip()
    if not user_id or not device_id or not token:
        return {"ok": False, "error": "user_id/device_id/fcm_token obrigatórios"}
    now = _now_iso()
    with _db_lock:
        conn = _db_connect()
        try:
            conn.execute(
                "INSERT INTO devices (user_id, device_id, fcm_token, platform, updated_at, last_seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id, device_id) DO UPDATE SET "
                "fcm_token = excluded.fcm_token, platform = excluded.platform, "
                "updated_at = excluded.updated_at, last_seen_at = excluded.last_seen_at",
                (user_id, device_id, token, payload.get("platform") or "", now, now),
            )
            conn.commit()
        finally:
            conn.close()
    return {"ok": True}


def devices_remove(user_id, device_id):
    user_id = str(user_id or "").strip()
    device_id = str(device_id or "").strip()
    if not user_id or not device_id:
        return {"ok": False, "error": "user_id/device_id obrigatórios"}
    with _db_lock:
        conn = _db_connect()
        try:
            cursor = conn.execute(
                "DELETE FROM devices WHERE user_id = ? AND device_id = ?",
                (user_id, device_id),
            )
            conn.commit()
            removed = cursor.rowcount
        finally:
            conn.close()
    return {"ok": True, "removed": removed}


# --- Worker ---------------------------------------------------------------


def _pack_unmonitor_season(series_id, season):
    episodes = _pack_series_episodes(series_id, refresh=True)
    ids = [
        episode["id"] for episode in episodes
        if _as_int(episode.get("seasonNumber")) == _as_int(season)
        and episode.get("monitored") and episode.get("id")
    ]
    key = arr_key(SONARR_CONFIG)
    count = 0
    if key and ids:
        arr_request(SONARR_URL, key, "/api/v3/episode/monitor", "PUT", {
            "episodeIds": ids, "monitored": False,
        })
        _pack_episode_cache.pop(_as_int(series_id), None)
        count = len(ids)
    try:
        _pack_set_season_flag(series_id, season, False)
    except Exception:
        pass
    return count


def _pack_monitor_season(series_id, season):
    episodes = _pack_series_episodes(series_id, refresh=True)
    ids = [
        episode["id"] for episode in episodes
        if _as_int(episode.get("seasonNumber")) == _as_int(season)
        and not episode.get("monitored") and episode.get("id")
    ]
    key = arr_key(SONARR_CONFIG)
    count = 0
    if key and ids:
        arr_request(SONARR_URL, key, "/api/v3/episode/monitor", "PUT", {
            "episodeIds": ids, "monitored": True,
        })
        _pack_episode_cache.pop(_as_int(series_id), None)
        count = len(ids)
    try:
        _pack_set_season_flag(series_id, season, True)
    except Exception:
        pass
    return count


def _pack_mark_waiting(job, stats, series_title=""):
    try:
        _pack_unmonitor_season(job["series_id"], job["season"])
    except Exception as error:
        # Não impede o estado; o próximo tick tenta de novo.
        job["error"] = f"desmonitorar: {error}"
    finale = _parse_iso(stats.get("finalAirDate"))
    next_at = (
        (finale + timedelta(hours=PACK_RETRY_HOURS)).isoformat().replace("+00:00", "Z")
        if finale else _iso_in(PACK_RETRY_HOURS * 3600)
    )
    updated = _pack_job_update(
        job["key"],
        status="waiting_finale",
        next_attempt_at=next_at,
        last_checked_at=_now_iso(),
        aired=stats.get("aired"),
        files=stats.get("files"),
        missing=stats.get("missing"),
        meta_patch={
            "lastAirDate": stats.get("lastAirDate"),
            "finalAirDate": stats.get("finalAirDate"),
            "nextAirDate": stats.get("nextAirDate"),
        },
    )
    title = series_title or (job.get("meta") or {}).get("title") or ""
    finale_text = str(stats.get("finalAirDate") or "")[:10] or "data indefinida"
    _pack_notify(
        "waiting_finale", "info", updated or job, "Aguardando finale",
        f"{title} T{job['season']}: último episódio em {finale_text}. "
        f"A busca do pack começa após o finale (+{PACK_RETRY_HOURS:g} h).",
        action="open_request", dedupe_seconds=7 * 86400,
    )
    return updated


def _pack_fail(job, reason):
    attempts = _as_int(job.get("attempts")) or 0
    max_attempts = _as_int(job.get("max_attempts")) or PACK_MAX_ATTEMPTS
    title = (job.get("meta") or {}).get("title") or ""
    if attempts >= max_attempts:
        updated = _pack_job_update(
            job["key"], status="no_pack", error=reason,
            next_attempt_at=_iso_in(PACK_RETRY_HOURS * 3600),
            last_checked_at=_now_iso(),
        )
        _pack_notify(
            "pack_no_pack", "warning", updated or job, "Sem pack completo",
            f"{title} T{job['season']}: {reason} após {attempts} tentativa(s). "
            "Você pode tentar de novo.",
            action="retry_pack",
        )
        return updated
    updated = _pack_job_update(
        job["key"], status="queued", error=reason,
        next_attempt_at=_iso_in(PACK_RETRY_HOURS * 3600),
        last_checked_at=_now_iso(),
    )
    return updated


def _pack_snapshot_once():
    if _pack_state_get("snapshot_done") == "1":
        return 0
    try:
        series_list = _sonarr_series(refresh=True)
    except Exception:
        return 0
    candidates = _pack_monitored_seasons()
    created = 0
    for item in candidates:
        series = item["series"]
        season = item["season"]
        tvdb_id = _as_int(series.get("tvdbId"))
        if not tvdb_id:
            continue
        key = _pack_key(tvdb_id, season)
        if _pack_job_get(key):
            continue
        _pack_job_upsert({
            "key": key,
            "tvdb_id": tvdb_id,
            "series_id": _as_int(series.get("id")),
            "season": season,
            "profile_id": _as_int(series.get("qualityProfileId")),
            "status": "ignored",
            "attempts": 0,
            "max_attempts": PACK_MAX_ATTEMPTS,
            "created_at": _now_iso(),
            "meta": {"snapshot": True, "title": series.get("title") or ""},
        })
        created += 1
    _pack_state_set("snapshot_done", "1")
    return created


def _pack_prepare_job(job, series):
    try:
        episodes = _pack_series_episodes(series.get("id"), refresh=True)
    except Exception:
        return job
    stats = pack_episode_stats(episodes, job["season"])
    base = {
        "aired": stats["aired"], "files": stats["files"],
        "missing": stats["missing"], "last_checked_at": _now_iso(),
    }
    if stats["aired"] > 0 and stats["missing"] == 0:
        return _pack_job_update(
            job["key"], status="complete", next_attempt_at=None,
            meta_patch={"episodeCount": stats["episodeCount"]}, **base,
        )
    _pack_job_update(job["key"], meta_patch={"episodeCount": stats["episodeCount"]}, **base)
    if stats["future"]:
        return _pack_mark_waiting(job, stats, series.get("title") or "")
    return _pack_job_get(job["key"])


def _pack_discover():
    try:
        candidates = _pack_monitored_seasons()
    except Exception:
        return []
    created = []
    for item in candidates:
        series = item["series"]
        season = item["season"]
        tvdb_id = _as_int(series.get("tvdbId"))
        if not tvdb_id:
            continue
        key = _pack_key(tvdb_id, season)
        if _pack_job_get(key):
            continue
        job = _pack_job_upsert({
            "key": key,
            "tvdb_id": tvdb_id,
            "series_id": _as_int(series.get("id")),
            "season": season,
            "profile_id": _as_int(series.get("qualityProfileId")),
            "profile_name": "",
            "status": "queued",
            "attempts": 0,
            "max_attempts": PACK_MAX_ATTEMPTS,
            "next_attempt_at": None,
            "created_at": _now_iso(),
            "meta": {"title": series.get("title") or ""},
        })
        if job:
            _pack_prepare_job(job, series)
            created.append(key)
    return created


def _pack_refresh_waiting():
    rows = _db_rows(
        "SELECT * FROM pack_jobs WHERE status = 'waiting_finale' "
        "AND (next_attempt_at IS NULL OR next_attempt_at <= ?)",
        (_now_iso(),),
    )
    activated = []
    for row in rows:
        job = _pack_job_from_row(row)
        series = _pack_series_by_tvdb(job["tvdb_id"])
        if not series:
            continue
        try:
            episodes = _pack_series_episodes(series.get("id"), refresh=True)
        except Exception:
            continue
        stats = pack_episode_stats(episodes, job["season"])
        if stats["future"]:
            finale = _parse_iso(stats.get("finalAirDate"))
            next_at = (
                (finale + timedelta(hours=PACK_RETRY_HOURS)).isoformat().replace("+00:00", "Z")
                if finale else _iso_in(PACK_RETRY_HOURS * 3600)
            )
            _pack_job_update(job["key"], next_attempt_at=next_at, last_checked_at=_now_iso())
            continue
        if stats["aired"] > 0 and stats["missing"] == 0:
            _pack_job_update(
                job["key"], status="complete", next_attempt_at=None,
                aired=stats["aired"], files=stats["files"], missing=0,
                last_checked_at=_now_iso(),
            )
            continue
        try:
            _pack_monitor_season(series.get("id"), job["season"])
        except Exception:
            pass
        _pack_job_update(
            job["key"], status="queued", next_attempt_at=None,
            aired=stats["aired"], files=stats["files"], missing=stats["missing"],
            last_checked_at=_now_iso(),
        )
        activated.append(job["key"])
    return activated


def _pack_track_active():
    rows = _db_rows(
        "SELECT * FROM pack_jobs WHERE status IN ('pack_found', 'downloading', 'importing')"
    )
    if not rows:
        return 0
    queue = _pack_queue_map()
    changed = 0
    for row in rows:
        job = _pack_job_from_row(row)
        meta = job.get("meta") or {}
        if meta.get("dryRun"):
            continue
        record = queue.get(job.get("release_title") or "") or queue.get(meta.get("infoHash") or "")
        if record:
            state = str(record.get("trackedDownloadState") or "").lower()
            status = "importing" if state in ("importing", "importpending", "importblocked") else "downloading"
            _pack_job_update(
                job["key"], status=status, last_checked_at=_now_iso(),
                meta_patch={"progress": _pack_queue_progress(record), "queueState": state},
            )
            changed += 1
            continue
        series = _pack_series_by_tvdb(job["tvdb_id"])
        if not series:
            continue
        try:
            episodes = _pack_series_episodes(series.get("id"), refresh=True)
        except Exception:
            continue
        stats = pack_episode_stats(episodes, job["season"])
        if stats["aired"] and stats["missing"] == 0:
            _pack_job_update(
                job["key"], status="complete", next_attempt_at=None,
                aired=stats["aired"], files=stats["files"], missing=0,
                last_checked_at=_now_iso(),
            )
            title = meta.get("title") or ""
            _pack_notify(
                "pack_done", "success", job, "Pack completo",
                f"{title} T{job['season']} completa ({stats['files']}/{stats['aired']}).",
                action="open_request",
            )
            changed += 1
            continue
        grabbed_at = _parse_iso(meta.get("grabbedAt"))
        elapsed = (
            (datetime.now(timezone.utc) - grabbed_at).total_seconds()
            if grabbed_at else PACK_GRAB_GRACE_SECONDS + 1
        )
        if meta.get("acceptSingle"):
            if elapsed < PACK_RETRY_HOURS * 3600:
                continue
        elif elapsed < PACK_GRAB_GRACE_SECONDS:
            continue
        _pack_job_update(
            job["key"], aired=stats["aired"], files=stats["files"],
            missing=stats["missing"], last_checked_at=_now_iso(),
        )
        job = _pack_job_get(job["key"]) or job
        if stats["files"] > 0 and stats["missing"] == 1 and stats["aired"] >= 2:
            updated = _pack_job_update(
                job["key"], status="incomplete",
                error=f"Faltam {stats['missing']} episódio(s)",
                next_attempt_at=_iso_in(PACK_RETRY_HOURS * 3600),
            )
            _pack_notify(
                "pack_incomplete", "warning", updated or job, "Pack incompleto",
                f"Faltam {stats['missing']} episódio(s). Você pode fechar com o "
                "episódio solto ou tentar outro pack.",
                action="accept_single",
            )
        else:
            _pack_fail(job, f"Pack incompleto: faltam {stats['missing']} episódio(s)")
        changed += 1
    return changed


def _pack_grab(job, release):
    key = arr_key(SONARR_CONFIG)
    if not key:
        return _pack_fail(job, "API key do Sonarr não encontrada")
    try:
        arr_request(SONARR_URL, key, "/api/v3/release", "POST", release)
    except Exception as error:
        return _pack_fail(job, f"grab: {type(error).__name__}: {error}")
    _pack_release_cache.pop((_as_int(job.get("series_id")), _as_int(job.get("season"))), None)
    return _pack_job_update(
        job["key"],
        status="downloading",
        error="",
        next_attempt_at=None,
        last_checked_at=_now_iso(),
        meta_patch={"grabbedAt": _now_iso(), "progress": 0, "dryRun": False},
    )


def _pack_search_job(key):
    job = _pack_job_get(key)
    if not job or job.get("status") != "searching":
        return
    try:
        series = _pack_series_by_tvdb(job["tvdb_id"], refresh=True)
        if not series:
            return _pack_fail(job, "Série não encontrada no Sonarr")
        episodes = _pack_series_episodes(series.get("id"), refresh=True)
        stats = pack_episode_stats(episodes, job["season"])
        _pack_job_update(
            job["key"], aired=stats["aired"], files=stats["files"],
            missing=stats["missing"], last_checked_at=_now_iso(),
        )
        job = _pack_job_get(key) or job
        if stats["future"]:
            return _pack_mark_waiting(job, stats, series.get("title") or "")
        if stats["aired"] > 0 and stats["missing"] == 0:
            return _pack_job_update(
                job["key"], status="complete", next_attempt_at=None,
                aired=stats["aired"], files=stats["files"], missing=0,
                last_checked_at=_now_iso(),
            )
        if stats["aired"] <= 0:
            return _pack_fail(job, "Temporada sem episódios no ar")
        releases = _pack_fetch_releases(series.get("id"), job["season"], refresh=True)
        accepted, skipped = pack_filter_releases(
            releases, job["season"], tvdb_id=job["tvdb_id"],
            expected_episodes=stats["aired"],
        )
        if not accepted:
            return _pack_fail(job, f"Sem pack completo ({len(skipped)} release(s) recusado(s))")
        release = accepted[0]
        quality = ((release.get("quality") or {}).get("quality") or {}).get("name") or ""
        updated = _pack_job_update(
            job["key"],
            status="pack_found",
            release_guid=release.get("guid") or "",
            release_indexer_id=_as_int(release.get("indexerId")),
            release_title=release.get("title") or "",
            release_size=_as_int(release.get("size")),
            release_seeders=_as_int(release.get("seeders")),
            release_quality=quality,
            error="",
            last_checked_at=_now_iso(),
            meta_patch={
                "infoHash": release.get("infoHash") or "",
                "expected": stats["aired"],
                "candidates": len(accepted),
                "dryRun": PACK_WORKER_DRY_RUN,
                "release": {
                    "guid": release.get("guid"),
                    "indexerId": release.get("indexerId"),
                    "title": release.get("title"),
                },
            },
        )
        if PACK_WORKER_DRY_RUN:
            return updated
        return _pack_grab(updated or job, release)
    except Exception as error:
        return _pack_fail(job, f"{type(error).__name__}: {error}")


def _pack_reap_futures():
    with _pack_lock:
        finished = [(key, future) for key, future in _pack_running.items() if future.done()]
        for key, future in finished:
            _pack_running.pop(key, None)
            try:
                future.result()
            except Exception as error:
                _pack_state["last_error"] = f"{key}: {type(error).__name__}: {error}"


def _pack_start_searches():
    if _pack_executor is None:
        return 0
    with _pack_lock:
        available = max(0, PACK_CONCURRENCY - len(_pack_running))
    if available <= 0:
        return 0
    rows = _db_rows(
        "SELECT * FROM pack_jobs WHERE status = 'queued' "
        "AND (next_attempt_at IS NULL OR next_attempt_at <= ?) "
        "ORDER BY created_at LIMIT ?",
        (_now_iso(), available),
    )
    started = 0
    for row in rows:
        job = _pack_job_from_row(row)
        attempts = (_as_int(job.get("attempts")) or 0) + 1
        _pack_job_update(
            job["key"], status="searching", attempts=attempts,
            last_attempt_at=_now_iso(), error="",
        )
        with _pack_lock:
            _pack_running[job["key"]] = _pack_executor.submit(_pack_search_job, job["key"])
        started += 1
    return started


def pack_worker_tick():
    if not PACK_WORKER_ENABLED:
        return {"ok": True, "enabled": False}
    started = time.time()
    _pack_snapshot_once()
    discovered = _pack_discover()
    _pack_reap_futures()
    waiting = _pack_refresh_waiting()
    tracked = _pack_track_active()
    searching = _pack_start_searches()
    _pack_state["last_tick_at"] = _now_iso()
    _pack_state["last_error"] = ""
    return {
        "ok": True,
        "enabled": True,
        "discovered": discovered,
        "activated": waiting,
        "tracked": tracked,
        "started": searching,
        "seconds": round(time.time() - started, 2),
    }


def _pack_worker_loop():
    while True:
        try:
            pack_worker_tick()
        except Exception as error:
            _pack_state["last_error"] = f"{type(error).__name__}: {error}"
        time.sleep(PACK_POLL_SECONDS)


def pack_worker_start():
    global _pack_executor
    if not PACK_WORKER_ENABLED:
        return None
    thread = _pack_state.get("thread")
    if thread and thread.is_alive():
        return thread
    if _pack_executor is None:
        _pack_executor = ThreadPoolExecutor(max_workers=PACK_CONCURRENCY)
    _pack_state["started_at"] = _now_iso()
    thread = threading.Thread(target=_pack_worker_loop, name="pack-worker", daemon=True)
    _pack_state["thread"] = thread
    thread.start()
    return thread


def pack_worker_health():
    with _pack_lock:
        running = sorted(_pack_running.keys())
    counts = {}
    for row in _db_rows("SELECT status, COUNT(*) AS total FROM pack_jobs GROUP BY status"):
        counts[row["status"]] = row["total"]
    return {
        "ok": True,
        "enabled": PACK_WORKER_ENABLED,
        "dryRun": PACK_WORKER_DRY_RUN,
        "concurrency": PACK_CONCURRENCY,
        "maxAttempts": PACK_MAX_ATTEMPTS,
        "retryHours": PACK_RETRY_HOURS,
        "startedAt": _pack_state.get("started_at"),
        "lastTickAt": _pack_state.get("last_tick_at"),
        "lastError": _pack_state.get("last_error"),
        "running": running,
        "jobs": counts,
    }


# --- Endpoints (media-agent) ----------------------------------------------


def sonarr_series_payload(tvdb_id):
    tvdb_id = _as_int(tvdb_id)
    if not tvdb_id:
        return {"ok": False, "error": "tvdbId inválido"}
    try:
        series = _pack_series_by_tvdb(tvdb_id, refresh=True)
        if not series:
            return {"ok": True, "series": None}
        profiles, _ = _sonarr_options()
        profile_names = {_as_int(p.get("id")): p.get("name") or "" for p in profiles}
        summary = _series_summary(series, profile_names)
        summary["seasons"] = [
            {
                "seasonNumber": _as_int(row.get("seasonNumber")),
                "monitored": bool(row.get("monitored")),
                "episodeCount": (row.get("statistics") or {}).get("totalEpisodeCount") or 0,
                "episodeFileCount": (row.get("statistics") or {}).get("episodeFileCount") or 0,
            }
            for row in series.get("seasons") or []
        ]
        return {"ok": True, "series": summary}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def sonarr_releases_payload(series_id, season_number, refresh=False, limit=20):
    series_id = _as_int(series_id)
    season_number = _as_int(season_number)
    if not series_id or season_number is None:
        return {"ok": False, "error": "seriesId/seasonNumber inválidos"}
    try:
        releases = _pack_fetch_releases(series_id, season_number, refresh=refresh)
        stats = pack_episode_stats(_pack_series_episodes(series_id), season_number)
        accepted, skipped = pack_filter_releases(
            releases, season_number,
            expected_episodes=stats["aired"] or None,
        )
        try:
            limit = max(1, min(100, int(limit)))
        except (TypeError, ValueError):
            limit = 20
        items = []
        for release in accepted[:limit]:
            items.append({
                "guid": release.get("guid"),
                "indexerId": _as_int(release.get("indexerId")),
                "indexer": release.get("indexer") or "",
                "title": release.get("title") or "",
                "size": _as_int(release.get("size")),
                "sizeGb": round(_as_float(release.get("size")) / 1e9, 2),
                "seeders": _as_int(release.get("seeders")),
                "leechers": _as_int(release.get("leechers")),
                "quality": ((release.get("quality") or {}).get("quality") or {}).get("name") or "",
                "qualityWeight": _as_int(release.get("qualityWeight")),
                "customFormatScore": _as_int(release.get("customFormatScore")),
                "fullSeason": bool(release.get("fullSeason")),
                "mappedSeasonNumber": _as_int(release.get("mappedSeasonNumber")),
                "age": _as_float(release.get("age")),
            })
        return {
            "ok": True,
            "seriesId": series_id,
            "seasonNumber": season_number,
            "total": len(releases),
            "fullSeason": sum(1 for release in releases if release.get("fullSeason")),
            "accepted": len(accepted),
            "skipped": len(skipped),
            "episodes": stats,
            "releases": items,
            "rejectedReasons": _pack_reason_counts(skipped),
        }
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def _pack_reason_counts(skipped):
    counts = {}
    for item in skipped or []:
        for reason in item.get("reasons") or []:
            bucket = reason.split(":", 1)[0]
            counts[bucket] = counts.get(bucket, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: -pair[1]))


def sonarr_season_monitor(payload):
    try:
        payload = payload or {}
        series_id = _as_int(payload.get("seriesId"))
        tvdb_id = _as_int(payload.get("tvdbId"))
        season = _as_int(payload.get("season"))
        if season is None:
            season = _as_int(payload.get("seasonNumber"))
        monitored = bool(payload.get("monitored", True))
        search = bool(payload.get("search", False))
        if (not series_id and not tvdb_id) or season is None:
            return {"ok": False, "error": "seriesId/tvdbId e season obrigatórios"}
        series = (
            _pack_series_by_tvdb(tvdb_id, refresh=True) if tvdb_id
            else next((s for s in _sonarr_series(refresh=True) if _as_int(s.get("id")) == series_id), None)
        )
        if not series:
            return {"ok": False, "error": "série não encontrada"}
        series_id = _as_int(series.get("id"))
        episodes = _pack_series_episodes(series_id, refresh=True)
        ids = [
            episode["id"] for episode in episodes
            if _as_int(episode.get("seasonNumber")) == season and episode.get("id")
        ]
        if not ids:
            return {"ok": False, "error": "temporada sem episódios"}
        key = arr_key(SONARR_CONFIG)
        if not key:
            return {"ok": False, "error": "API key do Sonarr não encontrada"}
        changed = 0
        for chunk in _chunks(ids):
            arr_request(SONARR_URL, key, "/api/v3/episode/monitor", "PUT", {
                "episodeIds": chunk, "monitored": monitored,
            })
            changed += len(chunk)
        command_id = None
        if search and monitored:
            command = arr_request(SONARR_URL, key, "/api/v3/command", "POST", {
                "name": "SeasonSearch",
                "seriesId": series_id,
                "seasonNumber": season,
            })
            command_id = (command or {}).get("id")
        _pack_episode_cache.pop(series_id, None)
        _pack_set_season_flag(series_id, season, monitored)
        return {
            "ok": True,
            "seriesId": series_id,
            "season": season,
            "monitored": changed if monitored else 0,
            "unmonitored": 0 if monitored else changed,
            "searchCommand": command_id,
        }
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def sonarr_grab(payload):
    try:
        payload = payload or {}
        series_id = _as_int(payload.get("seriesId"))
        season = _as_int(payload.get("seasonNumber"))
        guid = str(payload.get("guid") or "").strip()
        indexer_id = _as_int(payload.get("indexerId"))
        job_key = str(payload.get("jobKey") or "").strip()
        if not series_id or season is None:
            job = _pack_job_get(job_key) if job_key else None
            if job:
                series_id = job.get("series_id")
                season = job.get("season")
        if not series_id or season is None:
            return {"ok": False, "error": "seriesId/seasonNumber inválidos"}
        releases = _pack_fetch_releases(series_id, season, refresh=True)
        release = None
        wanted_title = str(payload.get("title") or "")
        for candidate in releases:
            if guid:
                if str(candidate.get("guid") or "") != guid:
                    continue
            elif wanted_title and candidate.get("title") != wanted_title:
                continue
            if indexer_id is not None and _as_int(candidate.get("indexerId")) != indexer_id:
                continue
            release = candidate
            break
        if not release:
            return {"ok": False, "error": "release não encontrado"}
        reasons = pack_evaluate_release(release, season)
        if reasons:
            return {"ok": False, "error": "release recusado pelo filtro", "reasons": reasons}
        key = arr_key(SONARR_CONFIG)
        if not key:
            return {"ok": False, "error": "API key do Sonarr não encontrada"}
        arr_request(SONARR_URL, key, "/api/v3/release", "POST", release)
        if job_key:
            _pack_job_update(
                job_key, status="downloading", error="", next_attempt_at=None,
                release_guid=release.get("guid") or "",
                release_indexer_id=_as_int(release.get("indexerId")),
                release_title=release.get("title") or "",
                release_size=_as_int(release.get("size")),
                release_seeders=_as_int(release.get("seeders")),
                last_checked_at=_now_iso(),
                meta_patch={
                    "grabbedAt": _now_iso(), "progress": 0, "dryRun": False,
                    "infoHash": release.get("infoHash") or "",
                },
            )
        _pack_release_cache.pop((series_id, season), None)
        return {
            "ok": True,
            "guid": release.get("guid"),
            "indexerId": _as_int(release.get("indexerId")),
            "title": release.get("title") or "",
        }
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def pack_jobs_payload(params=None):
    params = params or {}

    def first(name):
        value = params.get(name)
        if isinstance(value, list):
            return value[0] if value else None
        return value

    where = ["1=1"]
    values = []
    tvdb_id = _as_int(first("tvdbId") or first("tvdb_id"))
    if tvdb_id:
        where.append("tvdb_id = ?")
        values.append(tvdb_id)
    season = _as_int(first("season"))
    if season is not None:
        where.append("season = ?")
        values.append(season)
    status = str(first("status") or "").strip()
    if status:
        allowed = [item for item in status.split(",") if item in PACK_STATUSES]
        if allowed:
            where.append("status IN (" + ",".join("?" for _ in allowed) + ")")
            values.extend(allowed)
    if first("includeIgnored") not in ("1", "true", "yes"):
        where.append("status != 'ignored'")
    rows = _db_rows(
        "SELECT * FROM pack_jobs WHERE " + " AND ".join(where) + " ORDER BY created_at",
        tuple(values),
    )
    queued = _db_rows(
        "SELECT key FROM pack_jobs WHERE status = 'queued' ORDER BY created_at"
    )
    positions = {row["key"]: index + 1 for index, row in enumerate(queued)}
    jobs = [
        _pack_job_public(_pack_job_from_row(row), positions.get(row["key"]))
        for row in rows
    ]
    return {"ok": True, "jobs": jobs, "count": len(jobs)}


def pack_retry(payload):
    try:
        payload = payload or {}
        key = str(payload.get("key") or "").strip()
        if not key:
            tvdb_id = _as_int(payload.get("tvdbId"))
            season = _as_int(payload.get("season"))
            if tvdb_id and season is not None:
                key = _pack_key(tvdb_id, season)
        job = _pack_job_get(key)
        if not job:
            return {"ok": False, "error": "job não encontrado"}
        updated = _pack_job_update(
            key, status="queued", attempts=0, error="", next_attempt_at=None,
            release_guid=None, release_indexer_id=None, release_title=None,
            release_size=None, release_seeders=None, release_quality=None,
            last_checked_at=_now_iso(),
            meta_patch={"grabbedAt": None, "progress": None, "dryRun": False, "acceptSingle": False},
        )
        return {"ok": True, "job": _pack_job_public(updated)}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def pack_accept_single(payload):
    try:
        payload = payload or {}
        key = str(payload.get("key") or "").strip()
        if not key:
            tvdb_id = _as_int(payload.get("tvdbId"))
            season = _as_int(payload.get("season"))
            if tvdb_id and season is not None:
                key = _pack_key(tvdb_id, season)
        job = _pack_job_get(key)
        if not job:
            return {"ok": False, "error": "job não encontrado"}
        episodes = _pack_series_episodes(job["series_id"], refresh=True)
        stats = pack_episode_stats(episodes, job["season"])
        aired = [
            episode for episode in episodes
            if _as_int(episode.get("seasonNumber")) == job["season"]
            and _pack_episode_aired(episode)
        ]
        missing = [episode for episode in aired if not episode.get("hasFile")]
        if len(aired) < 2:
            return {"ok": False, "error": "temporada com menos de 2 episódios no ar"}
        if len(missing) != 1:
            return {"ok": False, "error": f"faltam {len(missing)} episódios; exceção só vale para 1"}
        episode = missing[0]
        api_key = arr_key(SONARR_CONFIG)
        if not api_key:
            return {"ok": False, "error": "API key do Sonarr não encontrada"}
        arr_request(SONARR_URL, api_key, "/api/v3/episode/monitor", "PUT", {
            "episodeIds": [episode["id"]], "monitored": True,
        })
        command = arr_request(SONARR_URL, api_key, "/api/v3/command", "POST", {
            "name": "EpisodeSearch", "episodeIds": [episode["id"]],
        })
        _pack_episode_cache.pop(_as_int(job["series_id"]), None)
        updated = _pack_job_update(
            key, status="downloading", error="", next_attempt_at=None,
            last_checked_at=_now_iso(),
            meta_patch={
                "acceptSingle": True, "grabbedAt": _now_iso(), "progress": 0,
                "singleEpisode": {
                    "id": episode["id"],
                    "episodeNumber": episode.get("episodeNumber"),
                    "commandId": (command or {}).get("id"),
                },
            },
        )
        return {
            "ok": True,
            "episode": {
                "id": episode["id"],
                "episodeNumber": episode.get("episodeNumber"),
                "title": episode.get("title") or "",
            },
            "aired": stats["aired"],
            "job": _pack_job_public(updated) if updated else None,
        }
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
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
        elif self.path.startswith("/status"):
            self._json(200, status_payload(STORAGE_CONFIG))
        elif self.path.startswith("/storage"):
            self._json(200, storage_payload(STORAGE_CONFIG))
        elif self.path.startswith("/requests"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            self._json(200, requests_payload(params))
        elif self.path.startswith("/arr/audio-check"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            kind = (params.get("kind") or [None])[0]
            item_id = _as_int((params.get("id") or [None])[0])
            all_items = (params.get("all") or ["0"])[0].lower() in ("1", "true", "yes")
            self._json(200, arr_audio_check(kind, item_id, all_items))
        elif self.path.startswith("/arr/pending"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            include_status = (params.get("status") or ["0"])[0].lower() in ("1", "true", "yes")
            self._json(200, arr_pending(include_status))
        elif self.path.startswith("/sonarr/options"):
            self._json(200, sonarr_options_payload())
        elif self.path.startswith("/sonarr/series"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            self._json(200, sonarr_series_payload((params.get("tvdbId") or [""])[0]))
        elif self.path.startswith("/sonarr/releases"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            refresh = (params.get("refresh") or ["0"])[0].lower() in ("1", "true", "yes")
            self._json(200, sonarr_releases_payload(
                (params.get("seriesId") or [""])[0],
                (params.get("seasonNumber") or [""])[0],
                refresh,
                (params.get("limit") or ["20"])[0],
            ))
        elif self.path.startswith("/pack-worker/health"):
            self._json(200, pack_worker_health())
        elif self.path.startswith("/pack-jobs"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            self._json(200, pack_jobs_payload(params))
        elif self.path.startswith("/notifications"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            unread = (params.get("unread") or ["0"])[0].lower() in ("1", "true", "yes")
            self._json(200, notifications_payload(
                (params.get("user_id") or [""])[0],
                (params.get("limit") or ["50"])[0],
                unread,
            ))
        elif self.path.startswith("/sonarr/lookup"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            self._json(200, sonarr_lookup((params.get("term") or [""])[0]))
        elif self.path.startswith("/sonarr/episodes"):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            self._json(200, sonarr_episodes((params.get("seriesId") or [""])[0]))
        elif self.path.startswith("/imports/active"):
            self._json(200, active_imports())
        elif self.path.startswith("/migration/status"):
            self._json(200, migration_status())
        elif self.path.startswith("/bazarr"):
            self._bazarr()
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self._forbidden():
            return
        if self.path.startswith("/status/clear-throttle"):
            self._json(200, request_throttle_clear(STORAGE_CONFIG))
        elif self.path.startswith("/requests/hide"):
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
        elif self.path.startswith("/sonarr/season/monitor"):
            self._json(200, sonarr_season_monitor(self._read_json()))
        elif self.path.startswith("/sonarr/grab"):
            self._json(200, sonarr_grab(self._read_json()))
        elif self.path.startswith("/pack-jobs/retry"):
            self._json(200, pack_retry(self._read_json()))
        elif self.path.startswith("/pack-jobs/accept-single"):
            self._json(200, pack_accept_single(self._read_json()))
        elif self.path.startswith("/notifications/read-all"):
            body = self._read_json()
            self._json(200, notifications_mark_all_read(body.get("user_id")))
        elif self.path.startswith("/notifications/read"):
            body = self._read_json()
            self._json(200, notifications_mark_read(body.get("id"), body.get("user_id")))
        elif self.path.startswith("/notifications/pushed"):
            body = self._read_json()
            self._json(200, notifications_mark_pushed(
                body.get("notification_id"), body.get("user_id"), body.get("error") or "",
            ))
        elif self.path.startswith("/devices"):
            self._json(200, devices_upsert(self._read_json()))
        else:
            self._json(404, {"error": "not found"})

    def do_DELETE(self):
        if self._forbidden():
            return
        if self.path.startswith("/devices/"):
            parsed = urllib.parse.urlparse(self.path)
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 3:
                self._json(200, devices_remove(
                    urllib.parse.unquote(parts[1]),
                    urllib.parse.unquote(parts[2]),
                ))
            else:
                self._json(200, {"ok": False, "error": "user_id/device_id ausentes"})
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
    pack_worker_start()
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    print(f"media-agent {LISTEN_HOST}:{LISTEN_PORT} (state: {STATE_DB})")
    print(
        f"pack-worker enabled={PACK_WORKER_ENABLED} dry_run={PACK_WORKER_DRY_RUN} "
        f"concurrency={PACK_CONCURRENCY}"
    )
    server.serve_forever()
