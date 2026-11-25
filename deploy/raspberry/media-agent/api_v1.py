#!/usr/bin/env python3
r"""BFF `/api/v1` do app da família.

Módulo separado do `media_agent.py` de propósito: sobe em listener próprio para
não arriscar as rotas legadas que o Homepage usa na `:8097`.

Decisões que este arquivo implementa (ver plans/PLANO_APP_NATIVO_JELLYFIN.md):

- D3: o Jellyfin é o IdP. O app manda o `AccessToken` e recebe um token de
       sessão próprio (HMAC), curto e renovável.
- D4: sessão do Seerr por pessoa. O cookie `connect.sid` é guardado **cifrado
       em repouso** e mapeado a `(user_id, device_id)`.
- D6: rotas de admin só existem no servidor subido com `public=False`, que deve
       ficar preso à LAN/Tailscale. No listener público elas respondem 404.
- D7: a senha nunca é persistida aqui; quem guarda é o Keystore do app.

Só stdlib, como o resto do media-agent.

Uso:
    V1_STATE_DIR=/state python3 api_v1.py \
        --host 127.0.0.1 --port 8091 \          # público (atrás do cloudflared)
        --admin-host <LAN_IP> --admin-port 8092

Testes:
    python3 -m unittest test_api_v1 -v

Rotas públicas:
    GET  /api/v1/status
    POST /api/v1/session          {access_token, device_id}
    POST /api/v1/session/seerr    {username, password, device_id}
    POST /api/v1/session/logout
    GET  /api/v1/me
    GET  /api/v1/requests
    POST /api/v1/requests         {media_type, media_id, seasons?}
    POST /api/v1/requests/hide    {key}
    POST /api/v1/requests/profile {kind, id, profile: legendado|dublado}
    GET  /api/v1/search           ?q=&page=&language=
    GET  /api/v1/discover
    GET  /api/v1/house
    GET  /api/v1/services
    GET  /api/v1/pc
    POST /api/v1/pc/wake
    GET  /api/v1/subs/quota
    GET  /api/v1/subs/queue

Rotas de admin (só no listener --admin):
    GET  /api/v1/admin/ping
    GET  /api/v1/admin/downloads  ?status=1

Erros: `{"code": "...", "message": "..."}`.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import argparse
import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import secrets
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPConnection, HTTPSConnection
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

VERSION = "0.1.0"
JELLYFIN_HEADER = (
    'MediaBrowser Client="family-bff", Device="server", '
    'DeviceId="family-bff", Version="' + VERSION + '"'
)
MAX_BODY = 64 * 1024
SESSION_MARGIN = 300  # renova 5 min antes do cookie do Seerr morrer

log = logging.getLogger("api_v1")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str = "", retry_after: float | None = None):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code
        self.retry_after = retry_after


def iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def parse_json(text: str):
    try:
        return json.loads(text) if text else None
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------
# Cifra do cookie em repouso (encrypt-then-MAC, stdlib)
# --------------------------------------------------------------------------
#
# Não é "criptografia caseira" no sentido de inventar primitiva: é HMAC-SHA256
# usado como PRF em modo contador para o keystream, com tag de integridade
# separada (MAC com chave derivada). O objetivo é só que um vazamento do
# arquivo de estado não entregue cookies de sessão do Seerr prontos para uso.
# Se um dia entrar `cryptography` no container, trocar por Fernet é trivial.

def _derive(master: bytes, label: bytes) -> bytes:
    return hmac.new(master, label, hashlib.sha256).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(
            key, b"ctr" + nonce + counter.to_bytes(4, "big"), hashlib.sha256
        ).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def load_or_create_key(path: str) -> bytes:
    """Lê (ou cria) uma chave de 32 bytes com permissão 0600."""
    if os.path.exists(path):
        with open(path, "rb") as handle:
            key = handle.read()
        if len(key) < 32:
            raise ValueError(f"chave curta demais em {path}")
        return key
    key = secrets.token_bytes(32)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(key)
    log.info("chave criada em %s", path)
    return key


class SecretBox:
    def __init__(self, master: bytes):
        if len(master) < 32:
            raise ValueError("chave mestra precisa de ao menos 32 bytes")
        self._enc = _derive(master, b"enc")
        self._mac = _derive(master, b"mac")

    @classmethod
    def load_or_create(cls, path: str) -> "SecretBox":
        return cls(load_or_create_key(path))

    def seal(self, data: bytes) -> bytes:
        nonce = secrets.token_bytes(16)
        stream = _keystream(self._enc, nonce, len(data))
        cipher = bytes(a ^ b for a, b in zip(data, stream))
        tag = hmac.new(self._mac, b"mac" + nonce + cipher, hashlib.sha256).digest()
        return nonce + cipher + tag

    def open(self, blob: bytes) -> bytes:
        if len(blob) < 16 + 32:
            raise ApiError(500, "corrupt_state", "blob cifrado truncado")
        nonce, cipher, tag = blob[:16], blob[16:-32], blob[-32:]
        expected = hmac.new(self._mac, b"mac" + nonce + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ApiError(500, "corrupt_state", "tag de integridade inválida")
        stream = _keystream(self._enc, nonce, len(cipher))
        return bytes(a ^ b for a, b in zip(cipher, stream))


# --------------------------------------------------------------------------
# Cliente HTTP mínimo
# --------------------------------------------------------------------------

class HttpJson:
    def __init__(self, base_url: str, timeout: float = 10.0):
        parts = urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError(f"URL inválida: {base_url!r}")
        self.scheme = parts.scheme
        self.host = parts.hostname
        self.port = parts.port or (443 if parts.scheme == "https" else 80)
        self.prefix = (parts.path or "").rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, body=None, headers=None, timeout=None):
        hdrs = {"Accept": "application/json", "User-Agent": f"family-bff/{VERSION}"}
        hdrs.update(headers or {})
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json"

        wait = timeout if timeout is not None else self.timeout
        if self.scheme == "https":
            conn = HTTPSConnection(self.host, self.port, timeout=wait)
        else:
            conn = HTTPConnection(self.host, self.port, timeout=wait)
        try:
            conn.request(method, self.prefix + path, body=payload, headers=hdrs)
            resp = conn.getresponse()
            raw = resp.read()
            return resp.status, resp.getheaders(), raw.decode("utf-8", "replace")
        finally:
            conn.close()

    def json(self, method: str, path: str, body=None, headers=None, timeout=None):
        status, raw_headers, text = self.request(method, path, body, headers, timeout)
        return status, raw_headers, text, parse_json(text)


def probe_http(base_url: str, path: str = "/", timeout: float = 2.0) -> dict:
    """Testa se um serviço responde. Qualquer resposta HTTP conta como "no ar"."""
    started = time.time()
    try:
        client = HttpJson(base_url, timeout=timeout)
        status, _, _ = client.request("GET", path, timeout=timeout)
        return {
            "ok": True,
            "http_code": status,
            "latency_ms": int((time.time() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001 - health check nunca deve lançar
        return {
            "ok": False,
            "error": str(exc)[:120],
            "latency_ms": int((time.time() - started) * 1000),
        }


# --------------------------------------------------------------------------
# Jellyfin
# --------------------------------------------------------------------------

class JellyfinClient:
    def __init__(self, base_url: str, timeout: float = 8.0):
        self.http = HttpJson(base_url, timeout)

    def authenticate(self, username: str, password: str):
        status, _, text, data = self.http.json(
            "POST",
            "/Users/AuthenticateByName",
            body={"Username": username, "Pw": password},
            headers={"Authorization": JELLYFIN_HEADER},
        )
        if status in (401, 403):
            raise ApiError(401, "invalid_credentials", "usuário ou senha inválidos")
        if status != 200 or not isinstance(data, dict):
            raise ApiError(502, "jellyfin_unavailable", f"Jellyfin respondeu {status}")
        token = data.get("AccessToken")
        if not token:
            raise ApiError(502, "jellyfin_unavailable", "login sem AccessToken")
        return str(token), data.get("User") or {}

    def me(self, token: str):
        status, _, text, data = self.http.json(
            "GET", "/Users/Me", headers={"X-Emby-Token": token, "Authorization": JELLYFIN_HEADER}
        )
        if status in (401, 403):
            raise ApiError(401, "invalid_token", "token do Jellyfin inválido")
        if status != 200 or not isinstance(data, dict):
            raise ApiError(502, "jellyfin_unavailable", f"Jellyfin respondeu {status}")
        return data


class AuthCache:
    """Valida tokens no Jellyfin com cache positivo e negativo.

    Sem isso, cada request do app viraria uma chamada no Pi. O cache negativo
    evita que um token revogado fique batendo no servidor.
    """

    def __init__(self, client: JellyfinClient, ttl: float = 300, negative_ttl: float = 30):
        self.client = client
        self.ttl = ttl
        self.negative_ttl = negative_ttl
        self.calls = 0
        self._cache: dict[str, tuple[float, dict | None]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def resolve(self, token: str):
        if not token:
            raise ApiError(401, "unauthorized", "token ausente")
        key = self._key(token)
        now = time.time()
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] > now:
                if hit[1] is None:
                    raise ApiError(401, "invalid_token", "token do Jellyfin inválido")
                return hit[1]

        self.calls += 1
        try:
            user = self.client.me(token)
        except ApiError as exc:
            if exc.code == "invalid_token":
                with self._lock:
                    self._cache[key] = (now + self.negative_ttl, None)
            raise
        with self._lock:
            self._cache[key] = (now + self.ttl, user)
        return user

    def forget(self, token: str) -> None:
        with self._lock:
            self._cache.pop(self._key(token), None)


# --------------------------------------------------------------------------
# Seerr
# --------------------------------------------------------------------------

def cookie_from_headers(raw_headers, name: str = "connect.sid"):
    for header, value in raw_headers:
        if header.lower() != "set-cookie":
            continue
        jar = SimpleCookie()
        try:
            jar.load(value)
        except Exception:
            continue
        if name in jar:
            morsel = jar[name]
            attrs = {
                key: val for key, val in morsel.items() if val not in ("", None)
            }
            return morsel.value, attrs
    return None, {}


def cookie_expiry(attrs: dict, default_ttl: float = 30 * 86400) -> float:
    now = time.time()
    if "max-age" in attrs:
        try:
            return now + int(attrs["max-age"])
        except (TypeError, ValueError):
            pass
    if "expires" in attrs:
        try:
            parsed = parsedate_to_datetime(str(attrs["expires"]))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except (TypeError, ValueError):
            pass
    return now + default_ttl


class SeerrClient:
    def __init__(self, base_url: str, timeout: float = 12.0):
        self.http = HttpJson(base_url, timeout)

    def login(self, username: str, password: str):
        status, raw_headers, text, data = self.http.json(
            "POST", "/api/v1/auth/jellyfin", body={"username": username, "password": password}
        )
        if status in (401, 403):
            raise ApiError(401, "seerr_invalid_credentials", "Seerr recusou as credenciais")
        if status not in (200, 201):
            raise ApiError(502, "seerr_unavailable", f"Seerr respondeu {status}")

        cookie, attrs = cookie_from_headers(raw_headers)
        if not cookie:
            raise ApiError(502, "seerr_no_cookie", "login aceito sem cookie connect.sid")
        expires = cookie_expiry(attrs) - SESSION_MARGIN
        return cookie, expires, (data or {})

    def call(self, cookie: str, method: str, path: str, body=None, timeout=None):
        status, _, text, data = self.http.json(
            method, path, body=body,
            headers={"Cookie": f"connect.sid={cookie}"},
            timeout=timeout,
        )
        return status, text, data


class MediaAgentClient:
    """Leitura do media-agent legado (Casa, Legendas e Downloads).

    O BFF fala com a `:8097` por localhost; as chaves dos *arr e a conta da
    OpenSubtitles continuam lá. Aqui só passa o recorte que o app precisa.
    """

    def __init__(self, base_url: str, timeout: float = 10.0):
        self.http = HttpJson(base_url, timeout)

    def get(self, path: str, timeout: float | None = None):
        try:
            status, _, text, data = self.http.json("GET", path, timeout=timeout)
        except OSError as exc:
            raise ApiError(
                503, "media_agent_unavailable", f"media-agent inacessível: {exc}"
            ) from None
        if status != 200 or data is None:
            raise ApiError(
                503, "media_agent_unavailable", f"media-agent respondeu {status}"
            )
        return data

    def post(self, path: str, body=None, timeout: float | None = None):
        try:
            status, _, text, data = self.http.json(
                "POST", path, body=body, timeout=timeout
            )
        except OSError as exc:
            raise ApiError(
                503, "media_agent_unavailable", f"media-agent inacessível: {exc}"
            ) from None
        if status != 200 or data is None:
            raise ApiError(
                503, "media_agent_unavailable", f"media-agent respondeu {status}"
            )
        return data


class RateLimiter:
    """Janela deslizante simples, por chave (IP + bucket)."""

    def __init__(self, limit: int, window: float = 60.0):
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str):
        now = time.time()
        with self._lock:
            hits = [t for t in self._hits.get(key, ()) if now - t < self.window]
            if len(hits) >= self.limit:
                retry = self.window - (now - hits[0]) if hits else self.window
                self._hits[key] = hits
                return False, max(retry, 1.0)
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > 2048:
                self._hits = {
                    k: v for k, v in self._hits.items()
                    if v and now - v[-1] < self.window
                }
            return True, 0.0


# --------------------------------------------------------------------------
# Store das sessões do Seerr
# --------------------------------------------------------------------------

class SessionStore:
    """Mantém `(user_id, device_id) -> cookie do Seerr`, cifrado em disco."""

    def __init__(self, path: str, box: SecretBox):
        self.path = path
        self.box = box
        self._lock = threading.Lock()
        self._sessions: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
            self._sessions = dict(data.get("sessions") or {})
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            log.warning("estado ilegível em %s: %s", self.path, exc)
            self._sessions = {}

    def _save(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = self.path + ".tmp"
        payload = {"version": 1, "sessions": self._sessions}
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, self.path)

    @staticmethod
    def _key(user_id: str, device_id: str) -> str:
        return f"{user_id}:{device_id}"

    def _evict(self, now: float) -> None:
        expired = [
            key for key, value in self._sessions.items()
            if float(value.get("expires_at", 0)) <= now
        ]
        for key in expired:
            self._sessions.pop(key, None)

    def put(self, user_id: str, device_id: str, cookie: str, expires_at: float) -> None:
        with self._lock:
            self._evict(time.time())
            self._sessions[self._key(user_id, device_id)] = {
                "user_id": user_id,
                "device_id": device_id,
                "cookie": base64.b64encode(self.box.seal(cookie.encode())).decode(),
                "expires_at": expires_at,
                "linked_at": time.time(),
            }
            self._save()

    def get(self, user_id: str, device_id: str):
        with self._lock:
            self._evict(time.time())
            entry = self._sessions.get(self._key(user_id, device_id))
            if not entry:
                return None
            cookie = self.box.open(base64.b64decode(entry["cookie"])).decode()
            return cookie, float(entry["expires_at"])

    def describe(self, user_id: str, device_id: str):
        with self._lock:
            self._evict(time.time())
            entry = self._sessions.get(self._key(user_id, device_id))
            if not entry:
                return None
            return {
                "linked_at": iso(float(entry.get("linked_at", 0))),
                "expires_at": iso(float(entry.get("expires_at", 0))),
            }

    def delete(self, user_id: str, device_id: str) -> bool:
        with self._lock:
            removed = self._sessions.pop(self._key(user_id, device_id), None) is not None
            if removed:
                self._save()
            return removed


# --------------------------------------------------------------------------
# Token de sessão do BFF
# --------------------------------------------------------------------------

def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def unb64url(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


class TokenSigner:
    def __init__(self, key: bytes, ttl: float = 3600):
        self.key = key
        self.ttl = ttl

    def issue(self, user_id: str, name: str, device_id: str, is_admin: bool, now: float | None = None):
        issued = int(now if now is not None else time.time())
        payload = {
            "sub": user_id,
            "name": name,
            "dev": device_id,
            "adm": bool(is_admin),
            "iat": issued,
            "exp": issued + int(self.ttl),
        }
        body = b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
        sig = b64url(hmac.new(self.key, body.encode(), hashlib.sha256).digest())
        return f"{body}.{sig}", payload["exp"]

    def verify(self, token: str):
        try:
            body, sig = token.rsplit(".", 1)
        except ValueError:
            raise ApiError(401, "invalid_session", "token malformado") from None
        expected = b64url(hmac.new(self.key, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise ApiError(401, "invalid_session", "assinatura inválida")
        try:
            payload = json.loads(unb64url(body))
        except (ValueError, json.JSONDecodeError):
            raise ApiError(401, "invalid_session", "payload inválido") from None
        if int(payload.get("exp", 0)) <= time.time():
            raise ApiError(401, "session_expired", "sessão expirada")
        return payload


# --------------------------------------------------------------------------
# Configuração e serviços
# --------------------------------------------------------------------------

@dataclass
class Config:
    jellyfin_url: str
    seerr_url: str
    state_dir: str
    token_ttl: float = 3600
    jellyfin_cache_ttl: float = 300
    negative_cache_ttl: float = 30
    timeout: float = 10.0
    allowed_networks: tuple = field(default_factory=tuple)
    media_agent_url: str = "http://127.0.0.1:8097"
    gaming_url: str = "http://127.0.0.1:8100"
    radarr_url: str = "http://127.0.0.1:7878"
    sonarr_url: str = "http://127.0.0.1:8989"
    bazarr_url: str = "http://127.0.0.1:6767"
    prowlarr_url: str = "http://127.0.0.1:9696"
    qbittorrent_url: str = "http://127.0.0.1:8082"
    rate_limit_session: int = 20
    rate_limit_default: int = 240

    @classmethod
    def from_env(cls) -> "Config":
        networks = []
        for item in os.getenv(
            "ALLOWED_NETWORKS", "127.0.0.0/8,::1/128,192.168.0.0/16,100.64.0.0/10"
        ).split(","):
            item = item.strip()
            if item:
                networks.append(ipaddress.ip_network(item))
        return cls(
            jellyfin_url=os.getenv("JELLYFIN_URL", "http://127.0.0.1:8096"),
            seerr_url=os.getenv("SEERR_URL", "http://127.0.0.1:5055"),
            state_dir=os.getenv("V1_STATE_DIR", os.getenv("STATE_DIR", "/state")),
            token_ttl=float(os.getenv("V1_TOKEN_TTL", "3600")),
            jellyfin_cache_ttl=float(os.getenv("V1_CACHE_TTL", "300")),
            negative_cache_ttl=float(os.getenv("V1_NEGATIVE_TTL", "30")),
            timeout=float(os.getenv("V1_TIMEOUT", "10")),
            allowed_networks=tuple(networks),
            media_agent_url=os.getenv("MEDIA_AGENT_URL", "http://127.0.0.1:8097"),
            gaming_url=os.getenv("GAMING_URL", "http://127.0.0.1:8100"),
            radarr_url=os.getenv("RADARR_URL", "http://127.0.0.1:7878"),
            sonarr_url=os.getenv("SONARR_URL", "http://127.0.0.1:8989"),
            bazarr_url=os.getenv("BAZARR_URL", "http://127.0.0.1:6767"),
            prowlarr_url=os.getenv("PROWLARR_URL", "http://127.0.0.1:9696"),
            qbittorrent_url=os.getenv("QBITTORRENT_URL", "http://127.0.0.1:8082"),
            rate_limit_session=int(os.getenv("V1_RATE_SESSION", "20")),
            rate_limit_default=int(os.getenv("V1_RATE_DEFAULT", "240")),
        )


class Services:
    def __init__(self, cfg: Config):
        os.makedirs(cfg.state_dir, exist_ok=True)
        self.cfg = cfg
        self.jellyfin = JellyfinClient(cfg.jellyfin_url, cfg.timeout)
        self.auth = AuthCache(
            self.jellyfin, cfg.jellyfin_cache_ttl, cfg.negative_cache_ttl
        )
        self.seerr = SeerrClient(cfg.seerr_url, cfg.timeout)
        self.media_agent = MediaAgentClient(cfg.media_agent_url, cfg.timeout)
        self.limiters = {
            "session": RateLimiter(cfg.rate_limit_session),
            "default": RateLimiter(cfg.rate_limit_default),
        }
        self.box = SecretBox.load_or_create(os.path.join(cfg.state_dir, "v1.key"))
        self.store = SessionStore(os.path.join(cfg.state_dir, "v1_sessions.json"), self.box)
        self.signer = TokenSigner(
            load_or_create_key(os.path.join(cfg.state_dir, "v1.token.key")),
            cfg.token_ttl,
        )


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def make_handler(services: Services, public: bool):
    cfg = services.cfg

    # Cache de metadados do Seerr (título/pôster) por (mediaType, tmdbId).
    # O payload de /request não traz pôster; buscamos uma vez e reusamos.
    meta_cache: dict[tuple[str, int], tuple[float, dict]] = {}
    meta_cache_lock = threading.Lock()
    meta_ttl = 6 * 3600.0
    meta_timeout = 3.0

    # Status dos serviços (probes paralelos) com cache curto.
    services_cache: dict[str, tuple[float, dict]] = {}
    services_cache_lock = threading.Lock()
    services_ttl = 15.0

    # Fila do *arr (progresso/status) por tmdbId/tvdbId, com cache curto.
    arr_cache: dict[str, tuple[float, tuple[dict, dict]]] = {}
    arr_cache_lock = threading.Lock()
    arr_ttl = 15.0

    # Recomendações do discover (famosas e não tão recentes), cache 10 min.
    discover_cache: dict[str, tuple[float, dict]] = {}
    discover_cache_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = f"family-bff/{VERSION}"
        protocol_version = "HTTP/1.1"

        # ---- utilidades -------------------------------------------------

        def log_message(self, fmt, *args):
            log.info("%s %s", self.address_string(), fmt % args)

        def _body(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise ApiError(400, "invalid_body", "Content-Length inválido") from None
            if length > MAX_BODY:
                raise ApiError(413, "body_too_large", "corpo grande demais")
            raw = self.rfile.read(length) if length else b""
            if not raw:
                return {}
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                raise ApiError(400, "invalid_json", "JSON inválido") from None
            if not isinstance(data, dict):
                raise ApiError(400, "invalid_json", "esperado um objeto JSON")
            return data

        def _send(self, status: int, payload, headers=None) -> None:
            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)

        def _error(self, exc: ApiError) -> None:
            if exc.status >= 500:
                log.warning("erro %s %s: %s", exc.status, exc.code, exc.message)
            headers = {}
            if exc.retry_after is not None:
                headers["Retry-After"] = str(int(max(exc.retry_after, 1)))
            self._send(exc.status, {"code": exc.code, "message": exc.message}, headers)

        def _bearer(self) -> str:
            header = self.headers.get("Authorization") or ""
            if not header.lower().startswith("bearer "):
                raise ApiError(401, "unauthorized", "envie Authorization: Bearer <token>")
            return header[7:].strip()

        def _identity(self):
            return services.signer.verify(self._bearer())

        def _query(self):
            return parse_qs(urlsplit(self.path).query)

        def _client_net_ok(self) -> bool:
            try:
                addr = ipaddress.ip_address(self.client_address[0])
            except ValueError:
                return False
            if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
                addr = addr.ipv4_mapped
            return any(addr in net for net in cfg.allowed_networks)

        # ---- rotas ------------------------------------------------------

        def do_GET(self):
            self._dispatch("GET")

        def do_HEAD(self):
            # Health checks (Cloudflare/monitoração) perguntam só cabeçalhos.
            path = urlsplit(self.path).path.rstrip("/") or "/"
            if path == "/api/v1/status":
                body = json.dumps({
                    "status": "ok", "version": VERSION, "time": iso(time.time()),
                }, separators=(",", ":")).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            self._dispatch("POST")

        def _dispatch(self, method: str) -> None:
            path = urlsplit(self.path).path.rstrip("/") or "/"
            try:
                self._rate_limit(path)
                self._route(method, path)
            except ApiError as exc:
                self._error(exc)
            except BrokenPipeError:
                pass
            except Exception:
                log.exception("falha inesperada em %s %s", method, self.path)
                self._error(ApiError(500, "internal_error", "erro interno"))

        def _rate_limit(self, path: str) -> None:
            bucket = "session" if path.startswith("/api/v1/session") else "default"
            allowed, retry = services.limiters[bucket].check(
                f"{bucket}:{self.client_address[0]}"
            )
            if not allowed:
                raise ApiError(
                    429,
                    "rate_limited",
                    "muitas requisições; tente de novo em instantes",
                    retry_after=retry,
                )

        def _route(self, method: str, path: str) -> None:
            if path == "/api/v1/status" and method == "GET":
                return self._status()
            if path == "/api/v1/session" and method == "POST":
                return self._session()
            if path == "/api/v1/session/seerr" and method == "POST":
                return self._link_seerr()
            if path == "/api/v1/session/logout" and method == "POST":
                return self._logout()
            if path == "/api/v1/me" and method == "GET":
                return self._me()
            if path == "/api/v1/requests" and method == "GET":
                return self._list_requests()
            if path == "/api/v1/requests" and method == "POST":
                return self._create_request()
            if path == "/api/v1/requests/hide" and method == "POST":
                return self._hide_request()
            if path == "/api/v1/requests/profile" and method == "POST":
                return self._change_profile()
            if path == "/api/v1/search" and method == "GET":
                return self._search()
            if path == "/api/v1/discover" and method == "GET":
                return self._discover()
            if path == "/api/v1/house" and method == "GET":
                return self._house()
            if path == "/api/v1/services" and method == "GET":
                return self._services()
            if path == "/api/v1/pc" and method == "GET":
                return self._pc()
            if path == "/api/v1/pc/wake" and method == "POST":
                return self._wake()
            if path == "/api/v1/subs/quota" and method == "GET":
                return self._subs_quota()
            if path == "/api/v1/subs/queue" and method == "GET":
                return self._subs_queue()
            if path == "/api/v1/admin/ping" and method == "GET":
                return self._admin_ping()
            if path == "/api/v1/admin/downloads" and method == "GET":
                return self._downloads()
            raise ApiError(404, "not_found", "rota inexistente")

        def _status(self) -> None:
            self._send(200, {"status": "ok", "version": VERSION, "time": iso(time.time())})

        def _session(self) -> None:
            body = self._body()
            access_token = str(body.get("access_token") or "")
            device_id = str(body.get("device_id") or "").strip()
            if not device_id:
                raise ApiError(400, "device_id_required", "informe device_id")

            user = services.auth.resolve(access_token)
            policy = user.get("Policy") or {}
            user_id = str(user.get("Id") or "")
            if not user_id:
                raise ApiError(502, "jellyfin_unavailable", "usuário sem Id")

            token, exp = services.signer.issue(
                user_id,
                str(user.get("Name") or ""),
                device_id,
                bool(policy.get("IsAdministrator")),
            )
            link = services.store.describe(user_id, device_id)
            self._send(200, {
                "token": token,
                "expires_at": iso(exp),
                "user": {
                    "id": user_id,
                    "name": str(user.get("Name") or ""),
                    "is_admin": bool(policy.get("IsAdministrator")),
                },
                "seerr_linked": link is not None,
                "seerr_expires_at": (link or {}).get("expires_at"),
            })

        def _link_seerr(self) -> None:
            identity = self._identity()
            body = self._body()
            username = str(body.get("username") or "")
            password = str(body.get("password") or "")
            device_id = str(body.get("device_id") or identity["dev"])
            if not username or not password:
                raise ApiError(400, "credentials_required", "informe username e password")
            if device_id != identity["dev"]:
                raise ApiError(400, "device_mismatch", "device_id difere do token")

            cookie, expires, _ = services.seerr.login(username, password)
            services.store.put(identity["sub"], device_id, cookie, expires)
            self._send(200, {
                "seerr_linked": True,
                "seerr_expires_at": iso(expires),
            })

        def _logout(self) -> None:
            identity = self._identity()
            removed = services.store.delete(identity["sub"], identity["dev"])
            self._send(200, {"seerr_linked": False, "removed": removed})

        def _me(self) -> None:
            identity = self._identity()
            link = services.store.describe(identity["sub"], identity["dev"])
            self._send(200, {
                "user": {
                    "id": identity["sub"],
                    "name": identity.get("name") or "",
                    "is_admin": bool(identity.get("adm")),
                },
                "device_id": identity["dev"],
                "seerr_linked": link is not None,
                "seerr_expires_at": (link or {}).get("expires_at"),
            })

        def _seerr_cookie(self, identity):
            link = services.store.get(identity["sub"], identity["dev"])
            if not link:
                raise ApiError(
                    409, "seerr_not_linked",
                    "conta do Seerr não vinculada neste aparelho",
                )
            return link[0]

        def _seerr_result(self, status: int, text: str, data):
            if status == 200 and data is not None:
                return data
            if status in (401, 403):
                raise ApiError(
                    401, "seerr_session_expired",
                    "sessão do Seerr expirou; vincule de novo",
                )
            raise ApiError(502, "seerr_unavailable", f"Seerr respondeu {status}")

        def _seerr_metadata(self, cookie: str, media_type: str, tmdb_id: int):
            """Busca título/pôster no Seerr, com cache em memória (6 h)."""
            key = (media_type, tmdb_id)
            now = time.time()
            with meta_cache_lock:
                cached = meta_cache.get(key)
                if cached and cached[0] > now:
                    return cached[1]
            status, _, meta = services.seerr.call(
                cookie, "GET", f"/api/v1/{media_type}/{tmdb_id}",
                timeout=meta_timeout,
            )
            if status != 200 or not isinstance(meta, dict):
                return None
            with meta_cache_lock:
                meta_cache[key] = (now + meta_ttl, meta)
            return meta

        def _arr_pending_maps(self):
            """Mapa tmdbId/tvdbId -> item do *arr (com progresso), cache 15 s."""
            now = time.time()
            with arr_cache_lock:
                cached = arr_cache.get("data")
                if cached and cached[0] > now:
                    return cached[1]
            try:
                data = services.media_agent.get("/arr/pending?status=1", timeout=8)
            except ApiError:
                return {}, {}
            movies, series = {}, {}
            for item in data.get("items") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("kind") == "movie" and item.get("tmdbId") is not None:
                    try:
                        movies[int(item["tmdbId"])] = item
                    except (TypeError, ValueError):
                        pass
                elif item.get("kind") == "series" and item.get("tvdbId") is not None:
                    try:
                        series[int(item["tvdbId"])] = item
                    except (TypeError, ValueError):
                        pass
            with arr_cache_lock:
                arr_cache["data"] = (now + arr_ttl, (movies, series))
            return movies, series

        def _enrich_requests(self, cookie: str, data):
            """Adiciona pôster/título (Seerr) e status/progresso (*arr)."""
            if not isinstance(data, dict):
                return data
            results = data.get("results")
            if not isinstance(results, list):
                return data
            movies, series = self._arr_pending_maps()
            for pedido in results:
                if not isinstance(pedido, dict):
                    continue
                media = pedido.get("media")
                if not isinstance(media, dict):
                    continue
                media_type = media.get("mediaType")

                # 1) Título/pôster (o payload de /request não traz pôster).
                tmdb_id = None
                try:
                    tmdb_id = int(media.get("tmdbId"))
                except (TypeError, ValueError):
                    pass
                if media_type in ("movie", "tv") and tmdb_id is not None:
                    ja_tem_titulo = bool(media.get("title") or media.get("name"))
                    if not (ja_tem_titulo and media.get("posterPath")):
                        meta = self._seerr_metadata(cookie, media_type, tmdb_id)
                        if meta:
                            if media_type == "movie":
                                media["title"] = media.get("title") or meta.get("title")
                            else:
                                media["name"] = media.get("name") or meta.get("name")
                            media["posterPath"] = (
                                media.get("posterPath") or meta.get("posterPath")
                            )

                # 2) Status/progresso da fila do *arr.
                arr_item = None
                try:
                    if media_type == "movie" and media.get("tmdbId") is not None:
                        arr_item = movies.get(int(media["tmdbId"]))
                    elif media_type == "tv" and media.get("tvdbId") is not None:
                        arr_item = series.get(int(media["tvdbId"]))
                except (TypeError, ValueError):
                    arr_item = None
                if arr_item:
                    queue = arr_item.get("queue") or {}
                    media["arr"] = {
                        "key": arr_item.get("key"),
                        "kind": arr_item.get("kind"),
                        "id": arr_item.get("id"),
                        "profileId": arr_item.get("profileId"),
                        "profileName": arr_item.get("profileName"),
                        "status": arr_item.get("status"),
                        "progress": queue.get("progress"),
                        "eta": queue.get("timeleft"),
                        "error": (
                            arr_item.get("errorMessage")
                            or arr_item.get("lastError")
                            or ""
                        ),
                    }
            return data

        def _list_requests(self) -> None:
            identity = self._identity()
            cookie = self._seerr_cookie(identity)
            query = self._query()
            take = min(max(int((query.get("take") or ["50"])[0] or 50), 1), 100)
            skip = max(int((query.get("skip") or ["0"])[0] or 0), 0)
            status_filter = (query.get("filter") or ["all"])[0]
            status, text, data = services.seerr.call(
                cookie,
                "GET",
                f"/api/v1/request?take={take}&skip={skip}&filter={status_filter}&sort=added",
            )
            data = self._seerr_result(status, text, data)
            self._send(200, self._enrich_requests(cookie, data))

        def _search(self) -> None:
            identity = self._identity()
            cookie = self._seerr_cookie(identity)
            query = self._query()
            term = (query.get("q") or [""])[0].strip()
            if not term:
                raise ApiError(400, "query_required", "informe q")
            try:
                page = max(int((query.get("page") or ["1"])[0] or 1), 1)
            except ValueError:
                raise ApiError(400, "invalid_page", "page precisa ser inteiro") from None
            language = (query.get("language") or ["pt-BR"])[0]
            status, text, data = services.seerr.call(
                cookie,
                "GET",
                f"/api/v1/search?query={quote(term)}&page={page}&language={quote(language)}",
            )
            self._send(200, self._seerr_result(status, text, data))

        def _discover(self) -> None:
            """Recomendações famosas e com pelo menos 1 ano (nota/votos altos)."""
            identity = self._identity()
            cookie = self._seerr_cookie(identity)
            now = time.time()
            with discover_cache_lock:
                cached = discover_cache.get("data")
                if cached and cached[0] > now:
                    return self._send(200, cached[1])

            limite = (
                datetime.now(timezone.utc) - timedelta(days=365)
            ).strftime("%Y-%m-%d")
            itens = []
            for kind, endpoint, date_param in (
                ("movie", "/api/v1/discover/movies", "primaryReleaseDateLte"),
                ("tv", "/api/v1/discover/tv", "firstAirDateLte"),
            ):
                path = (
                    f"{endpoint}?sortBy=popularity.desc&voteAverageGte=7"
                    f"&voteCountGte=1000&{date_param}={limite}&page=1"
                )
                status, text, data = services.seerr.call(cookie, "GET", path)
                if status != 200 or not isinstance(data, dict):
                    continue
                for result in (data.get("results") or [])[:12]:
                    if not isinstance(result, dict):
                        continue
                    itens.append({
                        "id": result.get("id"),
                        "mediaType": kind,
                        "title": result.get("title") or result.get("name"),
                        "posterPath": result.get("posterPath"),
                        "backdropPath": result.get("backdropPath"),
                        "overview": result.get("overview"),
                        "releaseDate": result.get("releaseDate"),
                        "firstAirDate": result.get("firstAirDate"),
                        "voteAverage": result.get("voteAverage"),
                        "mediaInfo": result.get("mediaInfo"),
                    })

            filmes = [item for item in itens if item["mediaType"] == "movie"]
            series = [item for item in itens if item["mediaType"] == "tv"]
            misto = []
            for idx in range(max(len(filmes), len(series))):
                if idx < len(filmes):
                    misto.append(filmes[idx])
                if idx < len(series):
                    misto.append(series[idx])

            # O discover (sem language) vem em inglês; o metadata do Seerr
            # devolve título/overview no idioma da instância (pt-BR).
            selecionados = misto[:12]
            for item in selecionados:
                meta = self._seerr_metadata(
                    cookie, item["mediaType"], item["id"]
                )
                if not isinstance(meta, dict):
                    continue
                item["title"] = (
                    meta.get("title") or meta.get("name") or item["title"]
                )
                item["overview"] = meta.get("overview") or item["overview"]
                item["posterPath"] = meta.get("posterPath") or item["posterPath"]
                item["backdropPath"] = (
                    meta.get("backdropPath") or item["backdropPath"]
                )
                item["releaseDate"] = meta.get("releaseDate") or item["releaseDate"]
                item["firstAirDate"] = (
                    meta.get("firstAirDate") or item["firstAirDate"]
                )
                if meta.get("voteAverage") is not None:
                    item["voteAverage"] = meta.get("voteAverage")
                item["mediaInfo"] = meta.get("mediaInfo") or item.get("mediaInfo")

            payload = {"ok": True, "items": selecionados}
            with discover_cache_lock:
                discover_cache["data"] = (now + 600, payload)
            self._send(200, payload)

        def _create_request(self) -> None:
            identity = self._identity()
            cookie = self._seerr_cookie(identity)
            body = self._body()
            media_type = str(body.get("media_type") or "")
            if media_type not in ("movie", "tv"):
                raise ApiError(400, "invalid_media_type", "use movie ou tv")
            try:
                media_id = int(body.get("media_id"))
            except (TypeError, ValueError):
                raise ApiError(400, "invalid_media_id", "media_id precisa ser inteiro") from None

            payload = {"mediaType": media_type, "mediaId": media_id}
            if media_type == "tv":
                seasons = body.get("seasons")
                if seasons in (None, [], "all"):
                    payload["seasons"] = "all"
                else:
                    try:
                        payload["seasons"] = [int(s) for s in seasons]
                    except (TypeError, ValueError):
                        raise ApiError(400, "invalid_seasons", "seasons inválido") from None

            status, text, data = services.seerr.call(
                cookie, "POST", "/api/v1/request", body=payload
            )
            if status in (200, 201, 202) and data is not None:
                return self._send(201, data)
            if status == 409:
                raise ApiError(409, "already_requested", "pedido já existente")
            self._seerr_result(status, text, data)
            raise ApiError(502, "seerr_unavailable", f"Seerr respondeu {status}")

        def _hide_request(self) -> None:
            self._identity()
            body = self._body()
            key = str(body.get("key") or "").strip()
            if not key:
                raise ApiError(400, "key_required", "informe key")
            data = services.media_agent.post(
                "/requests/hide", {"keys": [key], "hidden": True}, timeout=10
            )
            self._send(200, {"ok": bool(data.get("ok")), "updated": data.get("updated")})

        def _change_profile(self) -> None:
            self._identity()
            body = self._body()
            kind = str(body.get("kind") or "").strip().lower()
            try:
                item_id = int(body.get("id"))
            except (TypeError, ValueError):
                raise ApiError(400, "invalid_item", "informe kind e id") from None
            if kind not in ("movie", "series"):
                raise ApiError(400, "invalid_item", "use kind movie ou series")
            profile = str(body.get("profile") or "").strip().lower()
            if profile == "legendado":
                data = services.media_agent.post(
                    "/arr/switch", {"kind": kind, "id": item_id}, timeout=30
                )
            elif profile == "dublado":
                target = 8 if kind == "movie" else 9
                data = services.media_agent.post(
                    "/arr/search",
                    {"kind": kind, "id": item_id, "profile": target},
                    timeout=30,
                )
            else:
                raise ApiError(400, "invalid_profile", "use legendado ou dublado")
            self._send(200, {"ok": bool(data.get("ok")), "profile": data.get("profile")})

        def _house(self) -> None:
            self._identity()
            status = services.media_agent.get("/status", timeout=8)
            storage = services.media_agent.get("/storage", timeout=8)
            host = status.get("host") or {}
            cpu = status.get("cpu") or {}
            memory = status.get("memory") or {}
            temperature = status.get("temperature") or {}
            voltage = status.get("voltage") or {}
            items = []
            for item in storage.get("items") or []:
                items.append({
                    "id": item.get("id"),
                    "label": item.get("label"),
                    "percent": item.get("percent"),
                    "used": item.get("usedLabel"),
                    "free": item.get("freeLabel"),
                    "total": item.get("totalLabel"),
                })
            self._send(200, {
                "ok": True,
                "host": {
                    "name": host.get("hostname"),
                    "uptime": (status.get("uptime") or {}).get("label"),
                },
                "cpu": {
                    "percent": cpu.get("percent"),
                    "cores": cpu.get("cores"),
                    "load": [cpu.get("load1"), cpu.get("load5"), cpu.get("load15")],
                },
                "memory": {
                    "percent": memory.get("percent"),
                    "used": memory.get("usedLabel"),
                    "available": memory.get("availableLabel"),
                    "total": memory.get("totalLabel"),
                    "swap_percent": memory.get("swapPercent"),
                },
                "temperature": {
                    "celsius": temperature.get("celsius"),
                    "status": temperature.get("status"),
                },
                "throttled": bool(int(voltage.get("throttled") or 0)),
                "storage": items,
                "generated_at": status.get("generatedAt"),
            })

        def _services(self) -> None:
            self._identity()
            now = time.time()
            with services_cache_lock:
                cached = services_cache.get("data")
                if cached and cached[0] > now:
                    return self._send(200, cached[1])

            alvos = [
                ("jellyfin", "Jellyfin", cfg.jellyfin_url, "/System/Info/Public"),
                ("seerr", "Seerr", cfg.seerr_url, "/api/v1/settings/public"),
                ("bazarr", "Bazarr", cfg.bazarr_url, "/"),
                ("radarr", "Radarr", cfg.radarr_url, "/"),
                ("sonarr", "Sonarr", cfg.sonarr_url, "/"),
                ("prowlarr", "Prowlarr", cfg.prowlarr_url, "/"),
                ("qbittorrent", "qBittorrent", cfg.qbittorrent_url, "/"),
            ]
            with ThreadPoolExecutor(max_workers=len(alvos)) as pool:
                futuros = [
                    pool.submit(probe_http, base, path)
                    for _, _, base, path in alvos
                ]
                resultados = [futuro.result() for futuro in futuros]

            services = [
                {"id": sid, "name": nome, **resultado}
                for (sid, nome, _, _), resultado in zip(alvos, resultados)
            ]
            payload = {
                "ok": True,
                "services": services,
                "generated_at": iso(time.time()),
            }
            with services_cache_lock:
                services_cache["data"] = (now + services_ttl, payload)
            self._send(200, payload)

        def _pc(self) -> None:
            self._identity()
            try:
                client = HttpJson(cfg.gaming_url, timeout=4.0)
                status, _, text = client.request("GET", "/status", timeout=4.0)
            except Exception as exc:
                raise ApiError(
                    503, "pc_unavailable", f"gaming-agent inacessível: {exc}"
                ) from None
            data = parse_json(text)
            if status != 200 or not isinstance(data, dict):
                raise ApiError(503, "pc_unavailable", f"gaming-agent respondeu {status}")
            # Não expõe IP/MAC do PC para o app.
            self._send(200, {
                "ok": True,
                "online": bool(data.get("online")),
                "status": data.get("status"),
                "checked_at": data.get("checked_at"),
            })

        def _wake(self) -> None:
            self._identity()
            try:
                client = HttpJson(cfg.gaming_url, timeout=6.0)
                status, _, text = client.request("POST", "/wake", timeout=6.0)
            except Exception as exc:
                raise ApiError(
                    503, "pc_unavailable", f"gaming-agent inacessível: {exc}"
                ) from None
            data = parse_json(text)
            if status != 200 or not isinstance(data, dict):
                raise ApiError(503, "pc_unavailable", f"gaming-agent respondeu {status}")
            self._send(200, {
                "ok": bool(data.get("ok")),
                "sent": bool(data.get("ok")),
            })

        def _subs_quota(self) -> None:
            self._identity()
            data = services.media_agent.get("/subs/quota", timeout=12)
            quota = data.get("data") or {}
            # A conta da OpenSubtitles é compartilhada pela casa; o app não
            # precisa (nem deve) receber username/user_id dela.
            self._send(200, {
                "level": quota.get("level"),
                "allowed_downloads": quota.get("allowed_downloads"),
                "downloads_count": quota.get("downloads_count"),
                "remaining_downloads": quota.get("remaining_downloads"),
                "reset_time": quota.get("reset_time"),
                "reset_time_utc": quota.get("reset_time_utc"),
                "vip": bool(quota.get("vip")),
            })

        def _subs_queue(self) -> None:
            self._identity()
            try:
                movies = services.media_agent.get(
                    "/bazarr?path=/api/movies/wanted", timeout=15
                )
                episodes = services.media_agent.get(
                    "/bazarr?path=/api/episodes/wanted", timeout=15
                )
            except ApiError as exc:
                raise ApiError(503, "bazarr_unavailable", exc.message) from None
            items = []
            for movie in (movies.get("data") or [])[:20]:
                if not isinstance(movie, dict):
                    continue
                items.append({
                    "id": "movie:" + str(movie.get("radarrId") or movie.get("title") or ""),
                    "kind": "movie",
                    "title": movie.get("title") or "",
                    "episode": None,
                    "episodeTitle": movie.get("year"),
                    "languages": [
                        miss.get("name") or miss.get("code2")
                        for miss in movie.get("missing_subtitles") or []
                        if isinstance(miss, dict)
                    ],
                })
            for ep in (episodes.get("data") or [])[:40]:
                if not isinstance(ep, dict):
                    continue
                items.append({
                    "id": "episode:" + str(ep.get("sonarrEpisodeId") or ""),
                    "kind": "episode",
                    "title": ep.get("seriesTitle") or "",
                    "episode": ep.get("episode_number") or "",
                    "episodeTitle": ep.get("episodeTitle") or "",
                    "languages": [
                        miss.get("name") or miss.get("code2")
                        for miss in ep.get("missing_subtitles") or []
                        if isinstance(miss, dict)
                    ],
                })
            self._send(200, {
                "ok": True,
                "items": items,
                "movies_total": movies.get("total") or 0,
                "episodes_total": episodes.get("total") or 0,
            })

        def _require_admin(self):
            if public:
                # No listener público a rota nem existe: não vaza que há admin.
                raise ApiError(404, "not_found", "rota inexistente")
            identity = self._identity()
            if not identity.get("adm"):
                raise ApiError(403, "admin_required", "requer administrador")
            if not self._client_net_ok():
                raise ApiError(
                    403, "admin_lan_only",
                    "administração só a partir da LAN/Tailscale",
                )
            return identity

        def _downloads(self) -> None:
            self._require_admin()
            query = self._query()
            raw = (query.get("status") or ["1"])[0]
            try:
                status_filter = int(raw)
            except (TypeError, ValueError):
                raise ApiError(400, "invalid_status", "status precisa ser inteiro") from None
            data = services.media_agent.get(
                f"/arr/pending?status={status_filter}", timeout=45
            )
            items = []
            for item in (data.get("items") or [])[:100]:
                queue = item.get("queue") or {}
                seerr = item.get("seerr") or {}
                items.append({
                    "key": item.get("key"),
                    "kind": item.get("kind"),
                    "title": item.get("title"),
                    "year": item.get("year"),
                    "status": item.get("status"),
                    "profile": item.get("profileName"),
                    "requested_by": seerr.get("requestedBy"),
                    "progress": queue.get("progress"),
                    "eta": queue.get("timeleft"),
                    "error": queue.get("error") or item.get("lastError") or "",
                })
            self._send(200, {
                "ok": True,
                "items": items,
                "seerr_error": data.get("seerrError") or "",
            })

        def _admin_ping(self) -> None:
            identity = self._require_admin()
            self._send(200, {
                "ok": True,
                "user": identity.get("name") or identity["sub"],
                "client": self.client_address[0],
            })

    return Handler


class BffServer(ThreadingHTTPServer):
    """ThreadingHTTPServer que não cospe traceback quando o cliente desiste.

    Cloudflare e o app fecham conexões keep-alive o tempo todo; sem isso o log
    enche de ConnectionResetError sem indicar problema real.
    """

    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def make_server(services: Services, public: bool, host: str = "127.0.0.1", port: int = 8091):
    handler = make_handler(services, public)
    server = BffServer((host, port), handler)
    url = f"http://{host}:{server.server_address[1]}"
    return server, url


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BFF /api/v1 do app da família")
    parser.add_argument("--host", default=os.getenv("V1_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("V1_PORT", "8091")))
    parser.add_argument(
        "--admin",
        action="store_true",
        help="sobe só o listener de admin em --host/--port",
    )
    parser.add_argument(
        "--admin-host",
        default=os.getenv("V1_ADMIN_HOST", ""),
        help="sobe também o listener de admin preso a este IP da LAN",
    )
    parser.add_argument(
        "--admin-port",
        type=int,
        default=int(os.getenv("V1_ADMIN_PORT", "8092")),
    )
    parser.add_argument(
        "--lan-host",
        default=os.getenv("V1_LAN_HOST", ""),
        help="sobe também o listener de LAN (rotas públicas) neste IP",
    )
    parser.add_argument(
        "--lan-port",
        type=int,
        default=int(os.getenv("V1_LAN_PORT", "8091")),
    )
    parser.add_argument("--log-level", default=os.getenv("V1_LOG_LEVEL", "INFO"))
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cfg = Config.from_env()
    services = Services(cfg)

    public = not args.admin
    primary, url = make_server(services, public=public, host=args.host, port=args.port)
    log.info("BFF ouvindo em %s (%s)", url, "público" if public else "admin")

    extra = []
    if public and args.admin_host:
        admin_server, admin_url = make_server(
            services, public=False, host=args.admin_host, port=args.admin_port
        )
        thread = threading.Thread(target=admin_server.serve_forever, daemon=True)
        thread.start()
        extra.append((admin_server, thread))
        log.info("admin ouvindo em %s (LAN)", admin_url)

    # Listener de LAN para o app em casa: mesmas rotas públicas (sem admin),
    # para não depender do DNS público nem passar pela Cloudflare no dia a dia.
    if public and args.lan_host:
        lan_server, lan_url = make_server(
            services, public=True, host=args.lan_host, port=args.lan_port
        )
        thread = threading.Thread(target=lan_server.serve_forever, daemon=True)
        thread.start()
        extra.append((lan_server, thread))
        log.info("app na LAN ouvindo em %s", lan_url)

    try:
        primary.serve_forever()
    except KeyboardInterrupt:
        log.info("encerrando")
    finally:
        for server, thread in extra:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        primary.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
