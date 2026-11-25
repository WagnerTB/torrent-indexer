#!/usr/bin/env python3
"""Verifica o BFF por HTTPS público (ou localhost) sem precisar de senha.

Uso:
    python3 check_public.py https://<BFF_HOST>
    python3 check_public.py http://127.0.0.1:8099

O que confere:
  1. /api/v1/status responde 200 e {\"status\": \"ok\"};
  2. rotas protegidas respondem 401 sem token;
  3. /api/v1/session com token inválido responde 401 (prova que o BFF fala
     com o Jellyfin de verdade, não só que a porta abriu);
  4. /api/v1/admin/downloads não existe no listener público (404);
  5. a resposta vem com Cache-Control: no-store.

Só stdlib. Código de saída 0 quando todos os checks passam.
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
import urllib.parse


def call(base, method, path, body=None, token=None, timeout=12):
    url = base.rstrip("/") + path
    payload = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=payload, method=method)
    request.add_header("User-Agent", "FamiliaApp-check/0.1")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return (
                response.status,
                dict(response.headers),
                json.loads(raw) if raw else None,
                time.time() - started,
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return (
            exc.code,
            dict(exc.headers),
            json.loads(raw) if raw else None,
            time.time() - started,
        )


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="Confere o BFF publicado.")
    parser.add_argument("base", nargs="?", default="http://127.0.0.1:8099")
    parser.add_argument("--timeout", type=float, default=12.0)
    args = parser.parse_args(argv)

    base = args.base
    host = urllib.parse.urlsplit(base).hostname or base
    print(f"== BFF: {base}")

    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        print(f"  FALHA  DNS não resolve {host}: {exc}")
        print("  O domínio ainda não foi delegado ou a rota não existe.")
        return 1

    if base.startswith("https://"):
        try:
            context = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=args.timeout) as sock:
                with context.wrap_socket(sock, server_hostname=host) as tls:
                    print(f"  ok     TLS {tls.version()} {tls.cipher()[0]}")
        except OSError as exc:
            print(f"  FALHA  TLS: {exc}")
            return 1

    checks = []

    def check(name, condition, detail=""):
        checks.append(condition)
        print(f"  {'ok    ' if condition else 'FALHA '} {name}{(' — ' + detail) if detail else ''}")

    try:
        status, headers, data, elapsed = call(base, "GET", "/api/v1/status", timeout=args.timeout)
    except (urllib.error.URLError, OSError) as exc:
        print(f"  FALHA  conexão: {exc}")
        return 1

    check("status 200", status == 200, f"{status} em {elapsed*1000:.0f} ms")
    check("status ok", isinstance(data, dict) and data.get("status") == "ok",
          json.dumps(data)[:80] if data else "")
    check("Cache-Control: no-store",
          headers.get("Cache-Control") == "no-store", headers.get("Cache-Control", ""))

    status, _, data, _ = call(base, "GET", "/api/v1/me", timeout=args.timeout)
    check("me sem token → 401", status == 401,
          (data or {}).get("code", ""))
    check("me com erro padronizado", isinstance(data, dict) and "code" in data and "message" in data)

    status, _, data, _ = call(base, "GET", "/api/v1/house", timeout=args.timeout)
    check("house sem token → 401", status == 401, (data or {}).get("code", ""))

    status, _, data, _ = call(
        base, "POST", "/api/v1/session",
        {"access_token": "token-invalido-do-check", "device_id": "check-publico"},
        timeout=args.timeout,
    )
    check("session inválida → 401", status == 401, (data or {}).get("code", ""))
    check("Jellyfin alcançável pelo BFF",
          isinstance(data, dict) and data.get("code") == "invalid_token",
          (data or {}).get("code", ""))

    status, _, data, _ = call(base, "GET", "/api/v1/admin/downloads", timeout=args.timeout)
    check("admin ausente no público → 404", status == 404, (data or {}).get("code", ""))

    passed = all(checks)
    print(f"\n  {'TUDO OK' if passed else 'COM FALHAS'} ({sum(checks)}/{len(checks)})")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
