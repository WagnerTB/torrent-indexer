#!/usr/bin/env python3
"""Cliente isolado do VPS Controller (Oracle) usado pelo BFF da família.

O controlador é externo e NUNCA é chamado pelo app. As credenciais
(Cloudflare Access + tokens de leitura/inicialização) ficam só aqui, no
processo do BFF, e nunca são devolvidas nas respostas, logs ou estado.

Rotas externas usadas:
    GET  /health
    GET  /status   (token de leitura)
    POST /wake     (token de inicialização)

Somente o BFF chama `/wake`, e somente depois de uma ação explícita do app
(`POST /api/v1/vps/wake`). Nenhuma rotina automática usa o token de wake.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPSConnection
from urllib.parse import urlsplit

log = logging.getLogger("vps_controller")

DEFAULT_URL = "https://controle.wtbsrv.com.br"
VALID_STATES = (
    "online",
    "stopped",
    "starting",
    "checking",
    "transitioning",
    "running_unhealthy",
    "unavailable",
    "unknown",
)
MAX_BODY = 256 * 1024


class VpsControllerError(Exception):
    """Falha normalizada do controlador (sem segredos na mensagem)."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int = 502,
        retry_after: float | None = None,
        upstream_status: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retry_after = retry_after
        self.upstream_status = upstream_status


@dataclass(frozen=True)
class VpsControllerConfig:
    base_url: str = DEFAULT_URL
    client_id: str = ""
    client_secret: str = ""
    read_token: str = ""
    wake_token: str = ""
    timeout: float = 8.0
    cache_ttl: float = 2.0

    @classmethod
    def from_env(cls) -> "VpsControllerConfig":
        return cls(
            base_url=(os.getenv("VPS_CONTROLLER_URL") or DEFAULT_URL).strip(),
            client_id=(os.getenv("CF_ACCESS_CLIENT_ID") or "").strip(),
            client_secret=(os.getenv("CF_ACCESS_CLIENT_SECRET") or "").strip(),
            read_token=(os.getenv("VPS_CONTROLLER_READ_TOKEN") or "").strip(),
            wake_token=(os.getenv("VPS_CONTROLLER_WAKE_TOKEN") or "").strip(),
            timeout=float(os.getenv("VPS_CONTROLLER_TIMEOUT", "8")),
            cache_ttl=float(os.getenv("VPS_CONTROLLER_CACHE_TTL", "2")),
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.base_url
            and self.client_id
            and self.client_secret
            and self.read_token
        )

    @property
    def wake_configured(self) -> bool:
        return self.configured and bool(self.wake_token)


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = str(value).strip()
    return text or None


def _seconds(value, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number < 0:
        return default
    return number


def _int_seconds(value, default: int) -> int:
    number = _seconds(value, default)
    return int(round(number if number is not None else default))


def _bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


def normalize_status(payload, *, result: str | None = None) -> dict:
    """Transforma a resposta do controlador no contrato estável do BFF."""
    if not isinstance(payload, dict):
        raise VpsControllerError(
            "bad_response",
            "O controlador respondeu em formato inesperado.",
        )

    raw_state = payload.get("state", payload.get("status", "unknown"))
    state = str(raw_state or "").strip().lower()
    if state not in VALID_STATES:
        state = "unknown"

    jellyfin_raw = payload.get("jellyfin_online")
    jellyfin_online = (
        _bool(jellyfin_raw) if jellyfin_raw is not None else state == "online"
    )
    if state in ("stopped", "starting", "checking", "transitioning",
                 "running_unhealthy", "unavailable"):
        # O estado do controlador manda; evita "online" contraditório.
        jellyfin_online = bool(jellyfin_raw) if jellyfin_raw is not None else False

    poll_after = _int_seconds(payload.get("poll_after_seconds"), 5)
    poll_after = max(2, min(poll_after, 120))
    retry_after = _int_seconds(payload.get("retry_after_seconds"), 0)
    retry_after = max(0, min(retry_after, 3600))

    return {
        "ok": True,
        "state": state,
        "jellyfin_online": jellyfin_online,
        "health_checked_at": _text(payload.get("health_checked_at")),
        "oci_state": _text(payload.get("oci_state")),
        "oci_checked_at": _text(payload.get("oci_checked_at")),
        "oci_error": _text(payload.get("oci_error")),
        "last_start_at": _text(payload.get("last_start_at")),
        "last_start_result": _text(payload.get("last_start_result")),
        "retry_after_seconds": retry_after,
        "wake_enabled": _bool(payload.get("wake_enabled"), True),
        "poll_after_seconds": poll_after,
        "result": _text(result if result is not None else payload.get("result")),
        "controller_online": True,
    }


def unavailable_payload(exc: VpsControllerError) -> dict:
    """Resposta segura para o app quando o controlador não pôde ser lido."""
    return {
        "ok": False,
        "state": "unknown",
        "jellyfin_online": False,
        "health_checked_at": None,
        "oci_state": None,
        "oci_checked_at": None,
        "oci_error": None,
        "last_start_at": None,
        "last_start_result": None,
        "retry_after_seconds": int(exc.retry_after or 0),
        "wake_enabled": False,
        "poll_after_seconds": 15,
        "result": None,
        "controller_online": False,
        "error_code": exc.code,
        "message": exc.message,
    }


class VpsController:
    """Cliente com cache curto, cooldown e serialização de wake.

    - GET /status pode ter cache de poucos segundos (padrão 2 s) e é
      compartilhado entre chamadas concorrentes do BFF.
    - POST /wake nunca é automático, é serializado e respeita o cooldown
      devolvido pelo controlador (`retry_after_seconds`/`Retry-After`).
    """

    def __init__(self, cfg: VpsControllerConfig):
        self.cfg = cfg
        self._status_lock = threading.Lock()
        self._wake_lock = threading.Lock()
        self._cached: tuple[float, dict] | None = None
        self._wake_blocked_until = 0.0

        parts = urlsplit(cfg.base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("VPS_CONTROLLER_URL inválida")
        self._scheme = parts.scheme
        self._host = parts.hostname
        self._port = parts.port or (443 if parts.scheme == "https" else 80)
        self._prefix = (parts.path or "").rstrip("/")

    # ---- HTTP ---------------------------------------------------------

    def _request(self, method: str, path: str, token: str) -> tuple[int, list, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "family-bff/vps-controller",
            "CF-Access-Client-Id": self.cfg.client_id,
            "CF-Access-Client-Secret": self.cfg.client_secret,
            "Authorization": f"Bearer {token}",
        }
        wait = max(1.0, float(self.cfg.timeout))
        if self._scheme == "https":
            conn = HTTPSConnection(self._host, self._port, timeout=wait)
        else:
            conn = HTTPConnection(self._host, self._port, timeout=wait)
        try:
            conn.request(method, self._prefix + path, headers=headers)
            response = conn.getresponse()
            raw = response.read(MAX_BODY + 1)
            if len(raw) > MAX_BODY:
                raise VpsControllerError(
                    "bad_response",
                    "O controlador respondeu com conteúdo grande demais.",
                )
            return response.status, response.getheaders(), raw.decode("utf-8", "replace")
        except VpsControllerError:
            raise
        except Exception as exc:  # noqa: BLE001 - vira erro normalizado
            # Não loga headers, URL completa, token ou credenciais.
            log.warning("controlador inacessível (%s): %s", type(exc).__name__, exc)
            raise VpsControllerError(
                "unavailable",
                "Controlador da VPS indisponível.",
                http_status=503,
            ) from None
        finally:
            conn.close()

    @staticmethod
    def _json(text: str):
        try:
            return json.loads(text) if text else None
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _retry_after(raw_headers, payload) -> float | None:
        for key, value in raw_headers or []:
            if key.lower() == "retry-after":
                parsed = _seconds(value)
                if parsed is not None:
                    return parsed
        if isinstance(payload, dict):
            parsed = _seconds(payload.get("retry_after_seconds"))
            if parsed is not None:
                return parsed
        return None

    def _raise_for_status(self, status: int, payload, raw_headers, *, wake: bool) -> None:
        retry_after = self._retry_after(raw_headers, payload)
        body = payload if isinstance(payload, dict) else {}
        code = str(body.get("code") or body.get("result") or "").strip().lower()
        if status in (401, 403):
            raise VpsControllerError(
                "auth_failed",
                "O controlador recusou as credenciais do BFF.",
                http_status=502,
                upstream_status=status,
            )
        if status == 429:
            raise VpsControllerError(
                "rate_limited",
                "Muitas solicitações ao controlador; aguarde.",
                http_status=429,
                retry_after=retry_after or 30,
                upstream_status=status,
            )
        if wake and ("capacity" in code or "quota" in code or "limit" in code):
            raise VpsControllerError(
                "capacity_unavailable",
                "A Oracle não tem capacidade para iniciar a VPS agora.",
                http_status=503,
                retry_after=retry_after or 60,
                upstream_status=status,
            )
        if wake and status in (409, 422):
            raise VpsControllerError(
                "wake_rejected",
                body.get("message") or "O controlador recusou a inicialização.",
                http_status=409,
                retry_after=retry_after,
                upstream_status=status,
            )
        if status >= 500:
            raise VpsControllerError(
                "unavailable",
                "Controlador da VPS indisponível.",
                http_status=503,
                retry_after=retry_after,
                upstream_status=status,
            )
        raise VpsControllerError(
            "bad_response",
            "O controlador respondeu em formato inesperado.",
            http_status=502,
            upstream_status=status,
        )

    # ---- API pública do BFF --------------------------------------------

    def status(self) -> dict:
        if not self.cfg.configured:
            raise VpsControllerError(
                "not_configured",
                "Integração com o controlador da VPS não configurada.",
                http_status=503,
            )

        now = time.monotonic()
        with self._status_lock:
            if self._cached and self._cached[0] > now:
                return dict(self._cached[1])

            status, raw_headers, text = self._request("GET", "/status", self.cfg.read_token)
            payload = self._json(text)
            if status != 200:
                self._raise_for_status(status, payload, raw_headers, wake=False)
            normalized = normalize_status(payload)
            self._cached = (time.monotonic() + max(self.cfg.cache_ttl, 0.0), normalized)
            return dict(normalized)

    def wake(self) -> dict:
        if not self.cfg.configured:
            raise VpsControllerError(
                "not_configured",
                "Integração com o controlador da VPS não configurada.",
                http_status=503,
            )
        if not self.cfg.wake_configured:
            raise VpsControllerError(
                "wake_disabled",
                "A inicialização da VPS não está configurada no BFF.",
                http_status=503,
            )

        with self._wake_lock:
            now = time.monotonic()
            if now < self._wake_blocked_until:
                remaining = max(1, int(round(self._wake_blocked_until - now)))
                raise VpsControllerError(
                    "cooldown",
                    f"Aguarde {remaining}s antes de tentar novamente.",
                    http_status=429,
                    retry_after=remaining,
                )

            status, raw_headers, text = self._request("POST", "/wake", self.cfg.wake_token)
            payload = self._json(text)
            if status not in (200, 201, 202):
                retry_after = self._retry_after(raw_headers, payload)
                if status == 429 and retry_after:
                    self._wake_blocked_until = time.monotonic() + retry_after
                self._raise_for_status(status, payload, raw_headers, wake=True)

            normalized = normalize_status(payload)
            if not normalized.get("wake_enabled", True):
                # O controlador pode recusar wake mesmo respondendo 200.
                result = str(normalized.get("result") or "").lower()
                if result in ("disabled", "wake_disabled", "blocked"):
                    self._wake_blocked_until = time.monotonic() + max(
                        normalized.get("retry_after_seconds") or 30, 5
                    )
                    raise VpsControllerError(
                        "wake_disabled",
                        "A inicialização da VPS está desativada no controlador.",
                        http_status=409,
                        retry_after=normalized.get("retry_after_seconds") or 30,
                    )

            result = str(normalized.get("result") or "").lower()
            cooldown = normalized.get("retry_after_seconds") or 0
            if result == "already_online":
                cooldown = min(cooldown, 5) if cooldown else 2
            elif cooldown <= 0:
                cooldown = 8
            self._wake_blocked_until = time.monotonic() + max(0, cooldown)
            # O estado devolvido pelo wake é mais novo que o cache de /status.
            self._cached = (time.monotonic() + max(self.cfg.cache_ttl, 0.0), normalized)
            return dict(normalized)
