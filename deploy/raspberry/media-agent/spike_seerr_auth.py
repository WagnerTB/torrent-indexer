#!/usr/bin/env python3
"""Spike da etapa 0 do PLANO_APP_NATIVO_JELLYFIN.

Valida, contra a instância que já está rodando, o que o BFF precisa saber antes
de implementar `/api/v1/session`:

  1. login no Jellyfin por usuário/senha (`/Users/AuthenticateByName`);
  2. `IsAdministrator` em `/Users/Me`;
  3. login por pessoa no Seerr (`POST /api/v1/auth/jellyfin`);
  4. atributos e validade do cookie `connect.sid`;
  5. se a sessão renova sozinha (rolling) ou expira num prazo fixo;
  6. se o cookie vê os mesmos pedidos que a API key de admin;
  7. opcionalmente, criar um pedido como a pessoa (cookie) e como admin
     (`X-Api-Key` + `userId`, o fallback do plano B).

Nada sensível é impresso: senha, token e valor do cookie aparecem mascarados.
Usa só a stdlib, como o media_agent.py. Não altera nenhum arquivo.

Exemplo (no Pi, em um shell com o .env carregado):

    JELLYFIN_URL=http://127.0.0.1:8096 \\
    SEERR_URL=http://127.0.0.1:5055 \\
    SEERR_CONFIG=/srv/PiMedia/config/seerr/settings.json \\
    SPIKE_USER=alguem SPIKE_PASS='...' \\
    python3 spike_seerr_auth.py

Saída: um bloco "VEREDITO" com o que foi confirmado. Código de saída 0 quando
os quatro checks essenciais passam, 1 quando algum falha, 2 em erro de uso.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPConnection, HTTPSConnection
from http.cookies import SimpleCookie
from urllib.parse import quote, urlsplit

JELLYFIN_CLIENT = "spike-etapa0"
JELLYFIN_HEADER = (
    f'MediaBrowser Client="{JELLYFIN_CLIENT}", Device="cli", '
    f'DeviceId="{JELLYFIN_CLIENT}", Version="0.1"'
)


def mask(value: str, keep: int = 0) -> str:
    """Nunca devolve o segredo. Só o tamanho, para dar confiança no diagnóstico."""
    if not value:
        return "(vazio)"
    if keep <= 0:
        return f"*** ({len(value)} chars)"
    return value[:keep] + "…" if len(value) > keep else value


def fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "sem expiração declarada"
    now = datetime.now(timezone.utc)
    delta = value - now
    total = int(delta.total_seconds())
    if total <= 0:
        return f"expirado em {value:%Y-%m-%d %H:%M}"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    return f"{value:%Y-%m-%d %H:%M} (em {days}d{hours}h)"


class HttpClient:
    """Cliente mínimo com controle explícito de cookies.

    Não usa cookiejar para poder inspecionar `HttpOnly`, `SameSite`, `Max-Age`
    e detectar renovação (rolling) a cada resposta.
    """

    def __init__(self, base_url: str, timeout: float, insecure: bool = False,
                 default_headers: dict | None = None):
        parts = urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError(f"URL inválida: {base_url!r}")
        self.scheme = parts.scheme
        self.host = parts.hostname
        self.port = parts.port or (443 if parts.scheme == "https" else 80)
        self.prefix = (parts.path or "").rstrip("/")
        self.timeout = timeout
        self.insecure = insecure
        self.default_headers = dict(default_headers or {})
        self.cookies: dict[str, str] = {}
        self.cookie_attrs: dict[str, dict] = {}
        self.last_set_cookies: list[str] = []

    def _connection(self):
        if self.scheme == "https":
            ctx = ssl.create_default_context()
            if self.insecure:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            return HTTPSConnection(self.host, self.port, timeout=self.timeout, context=ctx)
        return HTTPConnection(self.host, self.port, timeout=self.timeout)

    def request(self, method: str, path: str, body=None, headers=None):
        hdrs = {"Accept": "application/json", "User-Agent": JELLYFIN_CLIENT}
        hdrs.update(self.default_headers)
        hdrs.update(headers or {})
        if self.cookies:
            hdrs["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json"

        conn = self._connection()
        try:
            conn.request(method, self.prefix + path, body=payload, headers=hdrs)
            resp = conn.getresponse()
            raw = resp.read()
            status = resp.status
            raw_headers = resp.getheaders()
        finally:
            conn.close()

        self.last_set_cookies = [v for k, v in raw_headers if k.lower() == "set-cookie"]
        self._absorb_cookies(self.last_set_cookies)
        return status, raw.decode("utf-8", "replace")

    def _absorb_cookies(self, headers: list[str]) -> None:
        for header in headers:
            jar = SimpleCookie()
            try:
                jar.load(header)
            except Exception:
                continue
            for name, morsel in jar.items():
                self.cookies[name] = morsel.value
                attrs = {}
                for key, value in morsel.items():
                    # Morsel devolve "" para atributos não definidos. Só flags
                    # de verdade (HttpOnly/Secure) vêm como True.
                    if value == "" or value is None:
                        continue
                    attrs[key] = value
                self.cookie_attrs[name] = attrs

    def cookie_expiry(self, name: str) -> datetime | None:
        attrs = self.cookie_attrs.get(name) or {}
        now = datetime.now(timezone.utc)
        if "max-age" in attrs:
            try:
                return now + timedelta(seconds=int(attrs["max-age"]))
            except (TypeError, ValueError):
                pass
        if "expires" in attrs:
            try:
                parsed = parsedate_to_datetime(str(attrs["expires"]))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except (TypeError, ValueError):
                pass
        return None


def parse_json(text: str):
    try:
        return json.loads(text) if text else None
    except json.JSONDecodeError:
        return None


def api_error(status: int, text: str) -> str:
    data = parse_json(text)
    if isinstance(data, dict):
        message = data.get("message") or data.get("error") or ""
        if message:
            return f"HTTP {status}: {message}"
    snippet = (text or "").strip().replace("\n", " ")[:180]
    return f"HTTP {status}: {snippet or 'sem corpo'}"


def jellyfin_login(base: str, user: str, password: str, timeout: float, insecure: bool):
    http = HttpClient(base, timeout, insecure)
    status, text = http.request(
        "POST",
        "/Users/AuthenticateByName",
        body={"Username": user, "Pw": password},
        headers={"Authorization": JELLYFIN_HEADER},
    )
    if status != 200:
        return None, f"/Users/AuthenticateByName → {api_error(status, text)}"

    data = parse_json(text) or {}
    token = str(data.get("AccessToken") or "")
    if not token:
        return None, "login respondeu 200 sem AccessToken"

    status, text = http.request(
        "GET", "/Users/Me", headers={"X-Emby-Token": token, "Authorization": JELLYFIN_HEADER}
    )
    if status != 200:
        return None, f"/Users/Me → {api_error(status, text)}"

    me = parse_json(text) or {}
    policy = me.get("Policy") or {}
    return {
        "client": http,
        "token": token,
        "user_id": str(me.get("Id") or (data.get("User") or {}).get("Id") or ""),
        "name": str(me.get("Name") or user),
        "is_admin": bool(policy.get("IsAdministrator")),
        "server_id": str(data.get("ServerId") or ""),
    }, ""


def seerr_login(base: str, user: str, password: str, timeout: float, insecure: bool):
    http = HttpClient(base, timeout, insecure)
    status, text = http.request(
        "POST", "/api/v1/auth/jellyfin", body={"username": user, "password": password}
    )
    if status not in (200, 201):
        return None, f"/api/v1/auth/jellyfin → {api_error(status, text)}"

    profile = parse_json(text) or {}
    if "connect.sid" not in http.cookies:
        return None, "login aceito, mas nenhum cookie connect.sid foi definido"

    # Primeira leitura depois do login: se vier outro Set-Cookie, é rolling.
    before_expiry = http.cookie_expiry("connect.sid")
    attrs_before = dict(http.cookie_attrs.get("connect.sid") or {})
    status, text = http.request("GET", "/api/v1/auth/me")
    if status != 200:
        return None, f"/api/v1/auth/me → {api_error(status, text)}"

    me = parse_json(text) or profile
    renewed = any("connect.sid" in header for header in http.last_set_cookies)
    after_expiry = http.cookie_expiry("connect.sid")
    expiry_moved = (
        before_expiry is not None
        and after_expiry is not None
        and after_expiry > before_expiry
    )

    return {
        "client": http,
        "user_id": me.get("id"),
        "email": me.get("email") or "",
        "username": me.get("username") or me.get("displayName") or user,
        "permissions": me.get("permissions"),
        "cookie_attrs": dict(http.cookie_attrs.get("connect.sid") or attrs_before),
        "expiry": after_expiry,
        "rolling": renewed and (expiry_moved or before_expiry is None),
        "renewed_without_move": renewed and not expiry_moved and before_expiry is not None,
    }, ""


def read_api_key(path: str) -> str:
    if os.path.isdir(path):
        path = os.path.join(path, "settings.json")
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return str(((data.get("main") or {}).get("apiKey") or "")).strip()


def fetch_requests(http: HttpClient, take: int):
    status, text = http.request(
        "GET",
        f"/api/v1/request?take={take}&skip=0&filter=all&sort=added",
    )
    if status != 200:
        return None, api_error(status, text)
    data = parse_json(text) or {}
    return list(data.get("results") or []), ""


def request_summary(items) -> dict:
    people = {}
    for item in items:
        who = item.get("requestedBy") or {}
        name = who.get("displayName") or who.get("username") or who.get("email") or "desconhecido"
        people[name] = people.get(name, 0) + 1
    return people


def list_seerr_users(http: HttpClient):
    status, text = http.request("GET", "/api/v1/user?take=100&skip=0")
    if status != 200:
        return None, api_error(status, text)
    data = parse_json(text) or {}
    return list(data.get("results") or []), ""


def resolve_user_id(users, wanted: str):
    needle = wanted.strip().lower()
    for user in users:
        fields = [
            user.get("displayName"),
            user.get("username"),
            user.get("email"),
            user.get("jellyfinUserId"),
        ]
        for field in fields:
            if field is not None and str(field).strip().lower() == needle:
                return user.get("id"), ""
    names = ", ".join(
        str(u.get("displayName") or u.get("username") or u.get("id")) for u in users
    )
    return None, f"usuário {wanted!r} não encontrado no Seerr. Existentes: {names or '(nenhum)'}"


def search_seerr(http: HttpClient, term: str, language: str):
    status, text = http.request(
        "GET",
        f"/api/v1/search?query={quote(term)}&page=1&language={quote(language)}",
    )
    if status != 200:
        return None, api_error(status, text)
    data = parse_json(text) or {}
    return list(data.get("results") or []), ""


def create_request(client: HttpClient, spec: str, seasons, user_id, headers):
    try:
        media_type, ident = spec.split(":", 1)
        media_id = int(ident)
    except ValueError:
        return None, "formato inválido; use movie:<tmdbId> ou tv:<tvdbId>"
    if media_type not in ("movie", "tv"):
        return None, "tipo deve ser movie ou tv"

    body = {"mediaType": media_type, "mediaId": media_id}
    if media_type == "tv":
        body["seasons"] = seasons if seasons else "all"
    if user_id is not None:
        body["userId"] = user_id

    status, text = client.request(
        "POST", "/api/v1/request", body=body, headers=headers
    )
    if status not in (200, 201):
        return None, f"/api/v1/request → {api_error(status, text)}"
    return parse_json(text) or {}, ""


def line(label: str, value) -> None:
    print(f"  {label:<26} {value}")


def parse_seasons(raw: str):
    if not raw:
        return None
    if raw.strip().lower() == "all":
        return "all"
    out = []
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        out.append(int(piece))
    return out or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Spike da etapa 0: valida a sessão por pessoa no Seerr.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplo:\n"
            "  JELLYFIN_URL=http://127.0.0.1:8096 SEERR_URL=http://127.0.0.1:5055 \\\n"
            "  SEERR_CONFIG=/srv/PiMedia/config/seerr/settings.json \\\n"
            "  SPIKE_USER=alguem SPIKE_PASS='...' python3 spike_seerr_auth.py\n"
        ),
    )
    parser.add_argument("--jellyfin-url", default=os.getenv("JELLYFIN_URL", "http://127.0.0.1:8096"))
    parser.add_argument("--seerr-url", default=os.getenv("SEERR_URL", "http://127.0.0.1:5055"))
    parser.add_argument("--seerr-config", default=os.getenv("SEERR_CONFIG", "/seerr/settings.json"))
    parser.add_argument("--user", default=os.getenv("SPIKE_USER", ""))
    parser.add_argument("--password", default=os.getenv("SPIKE_PASS", ""))
    parser.add_argument(
        "--password-file",
        default=os.getenv("SPIKE_PASS_FILE", ""),
        help="lê a senha do arquivo (evita histórico de shell e ps); tem prioridade",
    )
    parser.add_argument("--timeout", type=float, default=float(os.getenv("SPIKE_TIMEOUT", "15")))
    parser.add_argument("--search", default="", help="termo opcional para testar /api/v1/search")
    parser.add_argument("--language", default="pt-BR")
    parser.add_argument(
        "--request",
        default="",
        help="cria um pedido real: movie:<tmdbId> ou tv:<tvdbId> (cuidado)",
    )
    parser.add_argument("--seasons", default="", help="temporadas para tv, ex.: 1,2 ou all")
    parser.add_argument(
        "--as-user",
        default="",
        help="cria o pedido com a API key + userId desse usuário (testa o plano B)",
    )
    parser.add_argument("--yes", action="store_true", help="não pedir confirmação")
    parser.add_argument("--json", action="store_true", help="saída legível por máquina")
    parser.add_argument("--insecure", action="store_true", help="ignorar TLS inválido (LAN)")
    return parser


def main(argv=None) -> int:
    # Containers e SSH frequentemente rodam com LANG=C/latin-1. Forçar UTF-8
    # evita UnicodeEncodeError justamente na hora de imprimir o diagnóstico.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)

    # Com --json, stdout fica reservado para o JSON; o diagnóstico vai ao stderr.
    real_stdout = sys.stdout
    if args.json:
        sys.stdout = sys.stderr

    if args.password_file:
        try:
            with open(args.password_file, encoding="utf-8") as handle:
                args.password = handle.read().rstrip("\n")
        except OSError as exc:
            print(f"erro: lendo --password-file: {exc}", file=sys.stderr)
            return 2

    if not args.user or not args.password:
        print(
            "erro: defina --user e --password/--password-file "
            "ou SPIKE_USER/SPIKE_PASS",
            file=sys.stderr,
        )
        return 2

    result = {
        "jellyfin": "",
        "seerr": "",
        "api_key": "",
        "cookie": "",
        "rolling": None,
        "requests_cookie": None,
        "requests_key": None,
        "people": {},
        "search": None,
        "request": None,
        "checks": {},
        "errors": [],
    }

    print("== Jellyfin ==")
    jf, error = jellyfin_login(
        args.jellyfin_url, args.user, args.password, args.timeout, args.insecure
    )
    if error:
        result["errors"].append(error)
        print(f"  falhou: {error}")
        result["checks"]["jellyfin_login"] = False
    else:
        result["jellyfin"] = "ok"
        result["checks"]["jellyfin_login"] = True
        result["checks"]["jellyfin_admin_flag"] = True
        line("login", "ok")
        line("user_id", jf["user_id"])
        line("nome", jf["name"])
        line("isAdmin", jf["is_admin"])
        line("token", mask(jf["token"]))
    print("== Seerr (por pessoa) ==")
    se, error = seerr_login(
        args.seerr_url, args.user, args.password, args.timeout, args.insecure
    )
    if error:
        result["errors"].append(error)
        print(f"  falhou: {error}")
        result["checks"]["seerr_per_user_login"] = False
        result["checks"]["seerr_cookie"] = False
        result["checks"]["seerr_rolling"] = False
    else:
        result["seerr"] = "ok"
        result["checks"]["seerr_per_user_login"] = True
        result["checks"]["seerr_cookie"] = True
        result["rolling"] = se["rolling"]
        result["checks"]["seerr_rolling"] = se["rolling"]
        line("login", "ok")
        line("seerr_user_id", se["user_id"])
        line("username", se["username"])
        line("cookie", "connect.sid presente")
        line("cookie_valor", mask(se["client"].cookies["connect.sid"]))
        attrs = se["cookie_attrs"]
        line("HttpOnly", bool(attrs.get("httponly")))
        line("Secure", bool(attrs.get("secure")))
        line("SameSite", attrs.get("samesite") or "(não definido)")
        line("Path", attrs.get("path") or "/")
        line("expira", fmt_dt(se["expiry"]))
        line("rolling", "sim" if se["rolling"] else "não")
        result["cookie"] = {
            "http_only": bool(attrs.get("httponly")),
            "secure": bool(attrs.get("secure")),
            "same_site": attrs.get("samesite") or "",
            "expiry": se["expiry"].isoformat() if se["expiry"] else None,
        }
        if se["renewed_without_move"]:
            line("aviso", "Set-Cookie repetido sem mudar o prazo; TTL fixo")

        # Visibilidade do cookie vs API key.
        try:
            key = read_api_key(args.seerr_config)
            result["api_key"] = "ok" if key else "vazia"
        except (OSError, json.JSONDecodeError) as exc:
            key = ""
            result["api_key"] = f"falhou: {exc}"
            result["errors"].append(f"lendo SEERR_CONFIG: {exc}")

        items_cookie, error = fetch_requests(se["client"], 100)
        if error:
            result["errors"].append(f"/api/v1/request (cookie) → {error}")
        else:
            result["requests_cookie"] = len(items_cookie)
            result["people"] = request_summary(items_cookie)

        if key:
            admin = HttpClient(
                args.seerr_url, args.timeout, args.insecure,
                default_headers={"X-Api-Key": key},
            )
            items_key, error = fetch_requests(admin, 100)
            if error:
                result["errors"].append(f"/api/v1/request (api key) → {error}")
            else:
                result["requests_key"] = len(items_key)

            users, error = list_seerr_users(admin)
            if error:
                result["errors"].append(f"/api/v1/user → {error}")

            print("== Seerr (API key, só leitura) ==")
            line("chave", mask(key))
            line("pedidos visíveis", result["requests_key"])
            if users is not None:
                line("usuários importados", len(users))
                for user in users[:8]:
                    label = user.get("displayName") or user.get("username") or "?"
                    line(f"  - {label}", f"id={user.get('id')} jf={user.get('jellyfinUserId')}")
        else:
            users = None

        print("== Atribuição ==")
        line("pedidos pelo cookie", result["requests_cookie"])
        line("pedidos pela API key", result["requests_key"])
        line("por pessoa (cookie)", json.dumps(result["people"], ensure_ascii=False))

        if args.search:
            items, error = search_seerr(se["client"], args.search, args.language)
            print("== Busca ==")
            if error:
                result["errors"].append(f"/api/v1/search → {error}")
                print(f"  falhou: {error}")
            else:
                result["search"] = len(items)
                line("termo", args.search)
                line("resultados", len(items))
                for item in items[:5]:
                    title = item.get("title") or item.get("name") or ""
                    line(f"  - {item.get('mediaType')}", f"{title} tmdb={item.get('id')}")

        if args.request:
            print("== Pedido de teste ==")
            media, ident = (args.request.split(":", 1) + [""])[:2]
            print(f"  ATENÇÃO: vai criar um pedido real ({media} {ident}) no Seerr.")
            if not args.yes:
                if not sys.stdin.isatty():
                    print("  abortado: confirme com --yes em ambiente não interativo")
                    result["errors"].append("pedido não confirmado")
                else:
                    answer = input("  digitar 'sim' para continuar: ").strip().lower()
                    if answer != "sim":
                        print("  abortado")
                        result["errors"].append("pedido não confirmado")
                        args.request = ""

            if args.request:
                seasons = parse_seasons(args.seasons)
                user_id = None
                headers = None
                target = "cookie da pessoa"
                if args.as_user:
                    if users is None:
                        result["errors"].append(
                            "precisa de SEERR_CONFIG válido para resolver --as-user"
                        )
                        target = ""
                    else:
                        user_id, error = resolve_user_id(users, args.as_user)
                        if error:
                            result["errors"].append(error)
                            print(f"  falhou: {error}")
                            target = ""
                        else:
                            headers = {"X-Api-Key": key}
                            target = f"API key + userId={user_id}"
                if target:
                    created, error = create_request(
                        se["client"], args.request, seasons, user_id, headers
                    )
                    if error:
                        result["errors"].append(error)
                        print(f"  falhou: {error}")
                    else:
                        result["request"] = {
                            "identidade": target,
                            "id": created.get("id"),
                            "status": created.get("status"),
                        }
                        line("identidade", target)
                        line("request_id", created.get("id"))
                        line("status", created.get("status"))

    essential = {
        "jellyfin_login": result["checks"].get("jellyfin_login") is True,
        "jellyfin_admin_flag": result["checks"].get("jellyfin_admin_flag") is True,
        "seerr_per_user_login": result["checks"].get("seerr_per_user_login") is True,
        "seerr_cookie": result["checks"].get("seerr_cookie") is True,
    }

    if args.json:
        result["essential"] = essential
        result["ok"] = all(essential.values())
        print(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            file=real_stdout,
        )
        return 0 if result["ok"] else 1

    print("\n=== VEREDITO ===")
    for name, passed in essential.items():
        print(f"  {'OK ' if passed else 'NAO'}  {name}")
    if result["rolling"] is not None:
        verdict = "rolling (renova a cada uso)" if result["rolling"] else "TTL fixo desde o login"
        print(f"  --  sessão do Seerr: {verdict}")
    if result["errors"]:
        print("  erros:")
        for error in result["errors"]:
            print(f"    - {error}")

    if all(essential.values()):
        print("\n  Plano C confirmado na prática. Próximo passo: etapa 1a (auth no BFF).")
        return 0
    print("\n  Plano C não confirmado. Avaliar o plano B (API key + userId).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
