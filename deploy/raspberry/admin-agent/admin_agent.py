#!/usr/bin/env python3
"""admin-agent: administração LAN-only dos containers do stack de mídia.

Decisões de escopo (2026-11-26):
- Só containers Docker do projeto Compose (padrão `media`).
- Ações permitidas: start, stop e restart. Nada de exec, imagens, volumes,
  redes, compose ou .env.
- Login dedicado por senha (funciona mesmo se o Jellyfin estiver fora).
- Escuta somente na LAN (bind no IP da LAN + allowlist de origem/rede).
- Todas as ações são registradas em auditoria.

O acesso ao Docker é feito por um `docker-socket-proxy` interno, que só libera
`GET /containers/json` e as ações de start/stop/restart. Este processo nunca
monta o socket do Docker e nunca lê o compose ou o .env.

Uso:
    LISTEN_PORT=8093 python3 admin_agent.py

Rotas:
    GET  /health
    GET  /admin/ping
    GET  /admin/services
    GET  /admin/audit?limit=20
    POST /admin/services/{service}/{start|stop|restart}
         corpo JSON: {"confirm": "<service>"}
"""

from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "0.1.0"
MAX_BODY = 16 * 1024
ACTIONS = ("start", "stop", "restart")

# Containers que aparecem na lista, mas nunca podem ser parados por esta API.
# `autoheal` reinicia containers unhealthy; o proxy e o próprio agente são
# infraestrutura de administração.
PROTECTED = {"admin-agent", "docker-socket-proxy", "autoheal"}

# Serviços que exigem confirmação digitada no navegador (o servidor sempre
# exige o campo `confirm`, mas a UI reforça para estes).
CRITICAL = {
    "redis",
    "meilisearch",
    "solvearr",
    "homepage",
    "media-agent",
    "media-bff",
    "media-gateway",
}

DISPLAY_NAMES = {
    "torrent-indexer": "Torrent Indexer",
    "redis": "Redis",
    "meilisearch": "Meilisearch",
    "solvearr": "FlareSolverr (solvearr)",
    "qbittorrent": "qBittorrent",
    "sonarr": "Sonarr",
    "prowlarr": "Prowlarr",
    "bazarr": "Bazarr",
    "jellyfin": "Jellyfin",
    "stremio-server": "Stremio Server",
    "homepage": "Homepage",
    "gaming-agent": "Gaming Agent",
    "media-agent": "Media Agent",
    "media-bff": "Media BFF",
    "media-gateway": "Media Gateway",
    "radarr": "Radarr",
    "seerr": "Seerr",
    "autoheal": "Autoheal",
    "admin-agent": "Admin Agent",
    "docker-socket-proxy": "Docker Socket Proxy",
}

LISTEN_PORT = int(os.getenv("LISTEN_PORT", "8093"))
LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")
PASSWORD_FILE = os.getenv("ADMIN_PASSWORD_FILE", "/app/.admin_password")
DOCKER_URL = os.getenv("DOCKER_URL", "http://docker-socket-proxy:2375").rstrip("/")
COMPOSE_PROJECT = os.getenv("COMPOSE_PROJECT", "media").strip() or "media"
AUDIT_FILE = os.getenv("AUDIT_FILE", "/state/admin-audit.jsonl")
AUDIT_MAX_BYTES = int(os.getenv("AUDIT_MAX_BYTES", str(1024 * 1024)))

log = logging.getLogger("admin-agent")

_AUDIT_LOCK = threading.Lock()
_FAIL_LOCK = threading.Lock()
_FAILURES: dict[str, list[float]] = {}
_FAIL_WINDOW = 60.0
_FAIL_LIMIT = 5


class AdminError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [part.strip() for part in raw.split(",") if part.strip()]


def _networks() -> list[ipaddress._BaseNetwork]:
    result = []
    for value in _csv_env(
        "ADMIN_ALLOWED_NETWORKS",
        "127.0.0.0/8,::1/128",
    ):
        try:
            result.append(ipaddress.ip_network(value))
        except ValueError:
            log.warning("ADMIN_ALLOWED_NETWORKS inválido, ignorando: %s", value)
    if not result:
        result.append(ipaddress.ip_network("127.0.0.0/8"))
    return result


ALLOWED_NETWORKS = _networks()
ALLOWED_ORIGINS = _csv_env(
    "ADMIN_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def admin_password() -> str:
    """Lê a senha a cada request; trocar o arquivo não exige restart."""
    env_value = os.getenv("ADMIN_PASSWORD", "")
    if env_value:
        return env_value.strip()
    try:
        with open(PASSWORD_FILE, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def parse_health(status: str) -> str:
    match = re.search(r"\((?:health: )?(healthy|unhealthy|starting)\)", status or "")
    return match.group(1) if match else ""


def format_ports(ports) -> list[str]:
    result = []
    for item in ports or []:
        if not isinstance(item, dict):
            continue
        private = item.get("PrivatePort")
        public = item.get("PublicPort")
        kind = item.get("Type") or "tcp"
        if public:
            result.append(f"{public}->{private}/{kind}")
        elif private:
            result.append(f"{private}/{kind}")
    return sorted(set(result))[:8]


def display_name(service: str) -> str:
    return DISPLAY_NAMES.get(service) or service.replace("-", " ").replace("_", " ").title()


def docker_request(method: str, path: str, timeout: float = 45.0) -> tuple[int, bytes]:
    request = urllib.request.Request(
        DOCKER_URL + path,
        method=method,
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except Exception as error:  # noqa: BLE001 - vira erro HTTP controlado
        raise AdminError(503, "docker_unavailable", f"Docker proxy indisponível: {error}") from None


def docker_json(path: str, timeout: float = 10.0):
    status, body = docker_request("GET", path, timeout=timeout)
    if status != 200:
        raise AdminError(502, "docker_error", f"Docker respondeu {status}")
    try:
        return json.loads(body.decode("utf-8") or "[]")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdminError(502, "docker_error", f"Resposta inválida do Docker: {error}") from None


def media_containers() -> list[dict]:
    data = docker_json("/containers/json?all=1")
    if not isinstance(data, list):
        raise AdminError(502, "docker_error", "Docker não retornou uma lista de containers")
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        labels = item.get("Labels") or {}
        if labels.get("com.docker.compose.project") != COMPOSE_PROJECT:
            continue
        service = labels.get("com.docker.compose.service") or ""
        if not service:
            continue
        result.append(item)
    return result


def public_container(item: dict) -> dict:
    labels = item.get("Labels") or {}
    service = labels.get("com.docker.compose.service") or ""
    state = str(item.get("State") or "unknown")
    status = str(item.get("Status") or "")
    protected = service in PROTECTED
    return {
        "service": service,
        "name": display_name(service),
        "state": state,
        "status": status,
        "health": parse_health(status),
        "image": item.get("Image") or "",
        "ports": format_ports(item.get("Ports")),
        "protected": protected,
        "critical": service in CRITICAL,
        "can_start": not protected and state not in ("running", "paused", "restarting"),
        "can_stop": not protected and state in ("running", "paused", "restarting"),
        "can_restart": not protected,
    }


def list_services() -> list[dict]:
    services = [public_container(item) for item in media_containers()]
    services.sort(key=lambda service: (service["state"] != "running", service["name"].lower()))
    return services


def resolve_container(service: str) -> dict:
    for item in media_containers():
        labels = item.get("Labels") or {}
        if labels.get("com.docker.compose.service") == service:
            return item
    raise AdminError(404, "service_not_found", f"serviço não encontrado: {service}")


def perform_action(service: str, action: str) -> None:
    if action not in ACTIONS:
        raise AdminError(400, "invalid_action", f"ação inválida: {action}")
    if service in PROTECTED:
        raise AdminError(403, "protected_service", f"{service} é protegido e não pode ser alterado")
    item = resolve_container(service)
    container_id = str(item.get("Id") or "")
    if not container_id:
        raise AdminError(502, "docker_error", "container sem Id")
    path = f"/containers/{urllib.parse.quote(container_id, safe='')}/{action}"
    if action in ("stop", "restart"):
        path += "?t=30"
    status, body = docker_request("POST", path, timeout=45.0)
    if status in (204, 304):
        return
    detail = body.decode("utf-8", errors="replace").strip()[:240]
    if status == 404:
        raise AdminError(404, "container_not_found", "container sumiu antes da ação")
    raise AdminError(502, "docker_error", f"Docker respondeu {status}: {detail}")


def audit(event: str, client: str, **fields) -> None:
    record = {"ts": iso_now(), "event": event, "client": client}
    record.update(fields)
    line = json.dumps(record, ensure_ascii=False)
    with _AUDIT_LOCK:
        try:
            directory = os.path.dirname(AUDIT_FILE)
            if directory:
                os.makedirs(directory, exist_ok=True)
            if os.path.exists(AUDIT_FILE) and os.path.getsize(AUDIT_FILE) > AUDIT_MAX_BYTES:
                rotated = AUDIT_FILE + ".1"
                try:
                    os.remove(rotated)
                except OSError:
                    pass
                os.replace(AUDIT_FILE, rotated)
            with open(AUDIT_FILE, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError as error:
            log.warning("falha ao gravar auditoria: %s", error)


def read_audit(limit: int) -> list[dict]:
    try:
        with open(AUDIT_FILE, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return []
    items = []
    for line in lines[-limit:]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            items.append(value)
    items.reverse()
    return items


def rate_ok(client: str) -> bool:
    now = time.time()
    with _FAIL_LOCK:
        failures = [stamp for stamp in _FAILURES.get(client, []) if now - stamp < _FAIL_WINDOW]
        _FAILURES[client] = failures
        return len(failures) < _FAIL_LIMIT


def record_failure(client: str) -> None:
    with _FAIL_LOCK:
        _FAILURES.setdefault(client, []).append(time.time())


def clear_failures(client: str) -> None:
    with _FAIL_LOCK:
        _FAILURES.pop(client, None)


class AdminServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    server_version = f"admin-agent/{VERSION}"

    def log_message(self, *args):  # evita poluir o log a cada poll de 15s
        log.debug("%s - %s", self.client_address[0], args[0] if args else "")

    def _network_ok(self) -> bool:
        try:
            address = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return False
        return any(address in network for network in ALLOWED_NETWORKS)

    def _origin(self) -> str:
        return self.headers.get("Origin", "")

    def _origin_ok(self) -> bool:
        origin = self._origin()
        return not origin or origin in ALLOWED_ORIGINS

    def _cors_headers(self) -> dict[str, str]:
        origin = self._origin()
        if origin and origin in ALLOWED_ORIGINS:
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, X-Admin-Password",
                "Access-Control-Max-Age": "600",
                "Vary": "Origin",
            }
        return {}

    def _send(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, code: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(code, "application/json; charset=utf-8", body)

    def _guard(self) -> bool:
        if not self._network_ok():
            self._json(403, {"ok": False, "error": "rede não permitida"})
            return False
        if not self._origin_ok():
            self._json(403, {"ok": False, "error": "origem não permitida"})
            return False
        return True

    def _authorized(self) -> tuple[bool, int, str]:
        client = self.client_address[0]
        if not rate_ok(client):
            return False, 429, "muitas tentativas; aguarde 1 minuto"
        expected = admin_password()
        if not expected:
            return False, 503, "senha do admin-agent não configurada"
        provided = self.headers.get("X-Admin-Password", "")
        if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
            record_failure(client)
            audit("auth_failed", client, path=self.path)
            return False, 401, "senha inválida"
        clear_failures(client)
        return True, 200, ""

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0 or length > MAX_BODY:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return {}

    def do_OPTIONS(self):
        if not self._network_ok():
            self._json(403, {"ok": False, "error": "rede não permitida"})
            return
        if not self._origin_ok():
            self._json(403, {"ok": False, "error": "origem não permitida"})
            return
        self._send(204, "text/plain; charset=utf-8", b"")

    def do_GET(self):
        if not self._guard():
            return
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/health":
            self._json(200, {"ok": True, "version": VERSION})
            return

        if path in ("/admin/ping", "/admin/services", "/admin/audit"):
            ok, code, message = self._authorized()
            if not ok:
                self._json(code, {"ok": False, "error": message})
                return
            if path == "/admin/ping":
                self._json(200, {
                    "ok": True,
                    "version": VERSION,
                    "client": self.client_address[0],
                })
                return
            if path == "/admin/services":
                try:
                    services = list_services()
                except AdminError as error:
                    self._json(error.status, {"ok": False, "error": error.message})
                    return
                self._json(200, {
                    "ok": True,
                    "services": services,
                    "generated_at": iso_now(),
                })
                return
            query = urllib.parse.parse_qs(parsed.query)
            try:
                limit = int((query.get("limit") or ["20"])[0])
            except (TypeError, ValueError):
                limit = 20
            limit = max(1, min(200, limit))
            self._json(200, {"ok": True, "items": read_audit(limit)})
            return

        self._json(404, {"ok": False, "error": "rota não encontrada"})

    def do_POST(self):
        if not self._guard():
            return
        parsed = urllib.parse.urlsplit(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 4 or parts[0] != "admin" or parts[1] != "services":
            self._json(404, {"ok": False, "error": "rota não encontrada"})
            return

        service = urllib.parse.unquote(parts[2])
        action = parts[3]
        if action not in ACTIONS:
            self._json(400, {"ok": False, "error": f"ação inválida: {action}"})
            return

        ok, code, message = self._authorized()
        if not ok:
            self._json(code, {"ok": False, "error": message})
            return

        payload = self._read_json()
        if not isinstance(payload, dict):
            payload = {}
        confirm = str(payload.get("confirm") or "")
        if confirm != service:
            self._json(400, {
                "ok": False,
                "error": "confirmação inválida; envie {\"confirm\": \"<serviço>\"}",
            })
            return

        client = self.client_address[0]
        try:
            perform_action(service, action)
        except AdminError as error:
            audit("action", client, service=service, action=action, result="error", error=error.message)
            self._json(error.status, {"ok": False, "error": error.message})
            return
        audit("action", client, service=service, action=action, result="ok")
        self._json(200, {"ok": True, "service": service, "action": action})


def main() -> int:
    parser = argparse.ArgumentParser(description="admin-agent")
    parser.add_argument("--host", default=LISTEN_HOST)
    parser.add_argument("--port", type=int, default=LISTEN_PORT)
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log.info("admin-agent %s em %s:%s", VERSION, args.host, args.port)
    log.info("docker=%s projeto=%s", DOCKER_URL, COMPOSE_PROJECT)
    log.info("redes permitidas: %s", [str(network) for network in ALLOWED_NETWORKS])
    log.info("origens permitidas: %s", ALLOWED_ORIGINS)
    if not admin_password():
        log.warning("senha não configurada; rotas /admin responderão 503")

    server = AdminServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
