#!/usr/bin/env python3
"""Testes do BFF /api/v1 contra Jellyfin e Seerr falsos.

Roda sem rede externa, sem tocar no Pi e sem senha real:

    cd deploy/raspberry/media-agent
    python3 -m unittest test_api_v1 -v

Cada teste sobe servidores em portas efêmeras (127.0.0.1:0) e um diretório
temporário para o estado.
"""

import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import api_v1

USER = {"Id": "u-user", "Name": "Wagner", "Policy": {"IsAdministrator": False}}
ADMIN = {"Id": "u-admin", "Name": "admin", "Policy": {"IsAdministrator": True}}
TOKENS = {"jf-user": USER, "jf-admin": ADMIN}
SEERR_COOKIE = "cookie-secret-do-seerr"


class _Base(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send(self, status, payload, headers=()):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        size = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(size) if size else b""
        return json.loads(raw) if raw else {}


class FakeJellyfin(_Base):
    me_calls = 0

    def do_POST(self):
        body = self._body()
        if self.path != "/Users/AuthenticateByName":
            return self._send(404, {"message": "not found"})
        if not (self.headers.get("Authorization") or "").startswith("MediaBrowser"):
            return self._send(401, {"message": "sem header MediaBrowser"})
        username, password = body.get("Username"), body.get("Pw")
        if (username, password) == ("wagner", "segredo"):
            token, user = "jf-user", USER
        elif (username, password) == ("admin", "adminpw"):
            token, user = "jf-admin", ADMIN
        else:
            return self._send(401, {"message": "credenciais inválidas"})
        return self._send(200, {"User": user, "AccessToken": token, "ServerId": "srv"})

    def do_GET(self):
        if self.path != "/Users/Me":
            return self._send(404, {"message": "not found"})
        FakeJellyfin.me_calls += 1
        user = TOKENS.get(self.headers.get("X-Emby-Token"))
        if user is None:
            return self._send(401, {"message": "token inválido"})
        return self._send(200, user)


class FakeSeerr(_Base):
    requests_status = 200
    last_cookie = None
    login_calls = 0
    include_tv_request = False
    last_request_body = None
    request_status = 201
    request_payload = None

    TV_PAYLOADS = {
        37680: {
            "id": 37680,
            "name": "Homens de Terno",
            "posterPath": "/suits.jpg",
            "backdropPath": "/suits-b.jpg",
            "firstAirDate": "2011-06-23",
            "originalLanguage": "en",
            "externalIds": {"tvdbId": 247808},
            "keywords": [{"id": 10909, "name": "lawyer"}],
            "genres": [{"id": 18, "name": "Drama"}],
            "seasons": [
                {"seasonNumber": 0, "name": "Especiais", "episodeCount": 4, "airDate": "2011-01-01"},
                {"seasonNumber": 1, "name": "Temporada 1", "episodeCount": 12, "airDate": "2011-06-23"},
                {"seasonNumber": 2, "name": "Temporada 2", "episodeCount": 16, "airDate": "2012-06-14"},
            ],
            "mediaInfo": {
                "id": 1, "status": 4, "tvdbId": 247808,
                "seasons": [
                    {"seasonNumber": 1, "status": 5},
                    {"seasonNumber": 2, "status": 1},
                ],
            },
        },
        30984: {
            "id": 30984,
            "name": "Bleach",
            "posterPath": "/bleach.jpg",
            "firstAirDate": "2004-10-05",
            "originalLanguage": "ja",
            "externalIds": {"tvdbId": 74796},
            "keywords": [{"id": 210024, "name": "anime"}],
            "genres": [{"id": 16, "name": "Animation"}],
            "seasons": [
                {"seasonNumber": 1, "name": "Temporada 1", "episodeCount": 20, "airDate": "2004-10-05"},
            ],
            "mediaInfo": {
                "id": 2, "status": 1, "tvdbId": 74796,
                "seasons": [{"seasonNumber": 1, "status": 1}],
            },
        },
    }

    TV_REQUEST = {
        "id": 40,
        "status": 1,
        "type": "tv",
        "requestedBy": {
            "id": 2, "displayName": "Wagner",
            "jellyfinUserId": "u-user", "jellyfinUsername": "Wagner",
        },
        "seasons": [{"id": 1, "seasonNumber": 1, "status": 1}],
        "media": {
            "id": 10, "mediaType": "tv", "tmdbId": 37680, "tvdbId": 247808, "status": 1,
        },
    }

    def do_POST(self):
        body = self._body()
        FakeSeerr.last_request_body = body
        if self.path == "/api/v1/auth/jellyfin":
            FakeSeerr.login_calls += 1
            if (body.get("username"), body.get("password")) != ("wagner", "segredo"):
                return self._send(401, {"message": "INVALID_CREDENTIALS"})
            return self._send(
                200,
                {"id": 1, "username": "Wagner", "permissions": 2},
                [("Set-Cookie", f"connect.sid={SEERR_COOKIE}; Path=/; HttpOnly; "
                                "SameSite=Lax; Max-Age=2592000")],
            )
        if self.path == "/api/v1/request":
            FakeSeerr.last_cookie = self.headers.get("Cookie")
            if FakeSeerr.last_cookie != f"connect.sid={SEERR_COOKIE}":
                return self._send(401, {"message": "não autenticado"})
            if FakeSeerr.request_status != 201:
                return self._send(
                    FakeSeerr.request_status,
                    FakeSeerr.request_payload or {"message": "erro"},
                )
            return self._send(201, {"id": 99, "status": 1, "echo": body})
        return self._send(404, {"message": "not found"})

    def do_GET(self):
        if self.path.startswith("/api/v1/search?"):
            FakeSeerr.last_cookie = self.headers.get("Cookie")
            if FakeSeerr.last_cookie != f"connect.sid={SEERR_COOKIE}":
                return self._send(401, {"message": "não autenticado"})
            return self._send(200, {"page": 1, "totalPages": 1, "results": [
                {"id": 603, "mediaType": "movie", "title": "Matrix", "mediaInfo": None},
            ]})
        if self.path.startswith("/api/v1/request"):
            FakeSeerr.last_cookie = self.headers.get("Cookie")
            if FakeSeerr.requests_status != 200:
                return self._send(FakeSeerr.requests_status, {"message": "sessão expirada"})
            if FakeSeerr.last_cookie != f"connect.sid={SEERR_COOKIE}":
                return self._send(401, {"message": "não autenticado"})
            if "take=100" in self.path:
                return self._send(200, {
                    "pageInfo": {"pages": 1, "results": 1},
                    "results": [FakeSeerr.TV_REQUEST],
                })
            results = [{
                "id": 7,
                "requestedBy": {"displayName": "Wagner"},
                "media": {"id": 1, "mediaType": "movie", "tmdbId": 603, "status": 5},
            }]
            if FakeSeerr.include_tv_request:
                results.append(FakeSeerr.TV_REQUEST)
            return self._send(200, {
                "pageInfo": {"pages": 1, "results": len(results)},
                "results": results,
            })
        if self.path == "/api/v1/movie/603":
            FakeSeerr.last_cookie = self.headers.get("Cookie")
            if FakeSeerr.last_cookie != f"connect.sid={SEERR_COOKIE}":
                return self._send(401, {"message": "não autenticado"})
            return self._send(200, {
                "id": 603, "title": "Matrix", "posterPath": "/matrix.jpg",
            })
        if self.path.startswith("/api/v1/tv/"):
            FakeSeerr.last_cookie = self.headers.get("Cookie")
            if FakeSeerr.last_cookie != f"connect.sid={SEERR_COOKIE}":
                return self._send(401, {"message": "não autenticado"})
            tmdb_id = api_v1.to_int(self.path.rstrip("/").rsplit("/", 1)[-1].split("?")[0])
            payload = FakeSeerr.TV_PAYLOADS.get(tmdb_id)
            if payload:
                return self._send(200, payload)
            return self._send(200, {
                "id": 1399, "name": "Serie", "posterPath": "/serie.jpg",
            })
        if self.path.startswith("/api/v1/discover/movies"):
            FakeSeerr.last_cookie = self.headers.get("Cookie")
            if FakeSeerr.last_cookie != f"connect.sid={SEERR_COOKIE}":
                return self._send(401, {"message": "não autenticado"})
            return self._send(200, {"results": [
                {"id": 603, "title": "Matrix", "posterPath": "/m.jpg",
                 "backdropPath": "/mb.jpg", "overview": "...",
                 "releaseDate": "1999-03-31", "voteAverage": 8.7, "mediaInfo": None},
            ]})
        if self.path.startswith("/api/v1/discover/tv"):
            FakeSeerr.last_cookie = self.headers.get("Cookie")
            if FakeSeerr.last_cookie != f"connect.sid={SEERR_COOKIE}":
                return self._send(401, {"message": "não autenticado"})
            return self._send(200, {"results": [
                {"id": 1399, "name": "Serie", "posterPath": "/s.jpg",
                 "backdropPath": "/sb.jpg", "firstAirDate": "2011-04-17",
                 "voteAverage": 8.4, "mediaInfo": None},
            ]})
        return self._send(404, {"message": "not found"})


class FakeGaming(_Base):
    def do_GET(self):
        if self.path == "/status":
            return self._send(200, {
                "online": False,
                "status": "Desligado",
                "ips": {"192.168.1.2": False},
                "mac": "AA:BB:CC:DD:EE:FF",
                "checked_at": "2026-11-25T00:00:00+0000",
            })
        return self._send(404, {"message": "not found"})

    def do_POST(self):
        if self.path == "/wake":
            return self._send(200, {
                "ok": True,
                "ips": {"192.168.1.2": False},
                "mac": "AA:BB:CC:DD:EE:FF",
            })
        return self._send(404, {"message": "not found"})


def start(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class FakeMediaAgent(_Base):
    last = {}
    owner_pairs = []

    PACK_JOBS = [
        {
            "key": "tvdb:247808:s1", "tvdbId": 247808, "seriesId": 2, "season": 1,
            "status": "downloading", "statusLabel": "Baixando 42%", "attempt": 1,
            "maxAttempts": 3, "nextAttemptAt": None, "queuePosition": None,
            "title": "Suits", "releaseTitle": "Suits S01 1080p BluRay x265",
            "sizeGb": 11.5, "seeders": 50, "quality": "Bluray-1080p",
            "aired": 12, "files": 5, "missing": 7, "audioStatus": None,
            "progress": 42, "dryRun": False, "error": "",
            "updatedAt": "2026-11-25T23:00:00Z",
        },
        {
            "key": "tvdb:247808:s2", "tvdbId": 247808, "seriesId": 2, "season": 2,
            "status": "queued", "statusLabel": "Na fila para procura", "attempt": 0,
            "maxAttempts": 3, "nextAttemptAt": None, "queuePosition": 1,
            "title": "Suits", "releaseTitle": "", "sizeGb": None, "seeders": None,
            "quality": None, "aired": 16, "files": 0, "missing": 16,
            "audioStatus": None, "progress": None, "dryRun": False, "error": "",
            "updatedAt": "2026-11-25T23:00:00Z",
        },
        {
            "key": "tvdb:999:s1", "tvdbId": 999, "seriesId": 9, "season": 1,
            "status": "no_pack", "statusLabel": "Sem pack completo", "attempt": 3,
            "maxAttempts": 3, "nextAttemptAt": None, "queuePosition": None,
            "title": "Outra", "releaseTitle": "", "sizeGb": None, "seeders": None,
            "quality": None, "aired": 10, "files": 0, "missing": 10,
            "audioStatus": None, "progress": None, "dryRun": False,
            "error": "Sem pack completo", "updatedAt": "2026-11-25T23:00:00Z",
        },
        {
            "key": "tvdb:360295:s1", "tvdbId": 360295, "seriesId": 11, "season": 1,
            "status": "queued", "statusLabel": "Na fila para procura", "attempt": 0,
            "maxAttempts": 3, "nextAttemptAt": None, "queuePosition": 2,
            "title": "His Dark Materials", "releaseTitle": "", "sizeGb": None,
            "seeders": None, "quality": None, "aired": 8, "files": 2, "missing": 6,
            "audioStatus": None, "progress": None, "dryRun": True, "error": "",
            "updatedAt": "2026-11-25T23:40:00Z",
        },
    ]

    NOTIFICATIONS = [
        {"id": 11, "kind": "pack_done", "severity": "success", "key": "tvdb:247808:s1",
         "tvdbId": 247808, "seriesId": 2, "season": 1, "title": "Pack completo",
         "message": "Suits T1 completa (12/12).", "action": "open_request",
         "payload": {}, "createdAt": "2026-11-25T23:00:00Z", "read": False},
        {"id": 12, "kind": "pack_no_pack", "severity": "warning", "key": "tvdb:999:s1",
         "tvdbId": 999, "seriesId": 9, "season": 1, "title": "Sem pack completo",
         "message": "Outra T1 sem pack.", "action": "retry_pack",
         "payload": {}, "createdAt": "2026-11-25T22:00:00Z", "read": False},
    ]

    def do_GET(self):
        if self.path == "/status":
            return self._send(200, {
                "ok": True,
                "generatedAt": "2026-11-24T22:00:00Z",
                "host": {"hostname": "teste"},
                "uptime": {"label": "23h 52m"},
                "cpu": {"percent": 18.6, "cores": 4, "load1": 0.6, "load5": 0.3, "load15": 0.4},
                "memory": {"percent": 67, "usedLabel": "2.5 GB", "availableLabel": "1.2 GB",
                           "totalLabel": "3.7 GB", "swapPercent": 64},
                "temperature": {"celsius": 47.7, "status": "ok"},
                "voltage": {"throttled": 0},
            })
        if self.path == "/storage":
            return self._send(200, {"ok": True, "items": [
                {"id": "media", "label": "Mídia 2TB", "percent": 9,
                 "usedLabel": "157.1 GB", "freeLabel": "1.6 TB", "totalLabel": "1.8 TB"},
            ]})
        if self.path == "/subs/quota":
            return self._send(200, {"ok": True, "data": {
                "allowed_downloads": 20, "downloads_count": 5, "remaining_downloads": 15,
                "level": "Sub leecher", "reset_time": "01 hours", "reset_time_utc": "2026-11-24T23:59:59Z",
                "vip": False, "username": "conta-secreta", "user_id": 1412817,
            }})
        if self.path.startswith("/arr/pending"):
            return self._send(200, {"ok": True, "seerrError": "", "items": [
                {"key": "movie:tmdb:1", "kind": "movie", "id": 1, "title": "Filme", "year": 2020,
                 "tmdbId": 603, "status": "error", "profileId": 7, "profileName": "Legendado",
                 "lastError": "", "queue": {"progress": 79, "timeleft": "108.13:20:52",
                                            "error": "stalled", "failed": True},
                 "seerr": {"requestedBy": "teste"}},
            ]})
        if self.path.startswith("/bazarr?"):
            if "movies/wanted" in self.path:
                return self._send(200, {"data": [], "total": 0})
            if "episodes/wanted" in self.path:
                return self._send(200, {"data": [
                    {"seriesTitle": "Bleach", "episode_number": "17x41",
                     "episodeTitle": "GOD", "sonarrEpisodeId": 601,
                     "missing_subtitles": [{"name": "Portuguese (Brazil)", "code2": "pb"}]},
                ], "total": 1})
            return self._send(404, {"message": "not found"})
        if self.path.startswith("/pack-jobs"):
            jobs = list(FakeMediaAgent.PACK_JOBS)
            if "tvdbId=247808" in self.path:
                jobs = [job for job in jobs if job["tvdbId"] == 247808]
            elif "tvdbId=999" in self.path:
                jobs = [job for job in jobs if job["tvdbId"] == 999]
            elif "tvdbId=360295" in self.path:
                jobs = [job for job in jobs if job["tvdbId"] == 360295]
            return self._send(200, {"ok": True, "jobs": jobs, "count": len(jobs)})
        if self.path.startswith("/pack-owners"):
            return self._send(200, {
                "ok": True,
                "pairs": FakeMediaAgent.owner_pairs,
            })
        if self.path.startswith("/notifications"):
            items = [dict(item) for item in FakeMediaAgent.NOTIFICATIONS]
            if "user_id=u-admin" in self.path:
                for item in items:
                    item["read"] = False
            return self._send(200, {
                "ok": True,
                "notifications": items,
                "unread": sum(1 for item in items if not item["read"]),
            })
        if self.path.startswith("/sonarr/series"):
            return self._send(200, {"ok": True, "series": {
                "id": 2, "tvdbId": 247808, "title": "Suits",
                "seasons": [{"seasonNumber": 1, "monitored": True}],
            }})
        return self._send(404, {"message": "not found"})

    def do_POST(self):
        body = self._body()
        FakeMediaAgent.last[self.path.split("?")[0]] = body
        if self.path == "/requests/hide":
            return self._send(200, {"ok": True, "updated": 1, "hidden": True})
        if self.path in ("/arr/search", "/arr/switch"):
            return self._send(200, {"ok": True, "profile": 9})
        if self.path.startswith("/pack-jobs/retry"):
            return self._send(200, {"ok": True, "job": {"status": "queued"}})
        if self.path.startswith("/pack-jobs/accept-single"):
            return self._send(200, {"ok": True, "episode": {"episodeNumber": 8}})
        if self.path.startswith("/pack-jobs/ensure"):
            return self._send(200, {"ok": True, "created": True, "job": {"status": "queued"}})
        if self.path.startswith("/pack-owners"):
            return self._send(200, {"ok": True})
        if self.path.startswith("/sonarr/season/monitor"):
            return self._send(200, {"ok": True, "monitored": 12})
        if self.path.startswith("/notifications/read"):
            return self._send(200, {"ok": True})
        if self.path.startswith("/devices"):
            return self._send(200, {"ok": True})
        return self._send(404, {"message": "not found"})

    def do_DELETE(self):
        FakeMediaAgent.last[self.path] = {}
        if self.path.startswith("/devices/"):
            return self._send(200, {"ok": True, "removed": 1})
        return self._send(404, {"message": "not found"})


def http(method, url, body=None, token=None, timeout=5):
    payload = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=payload, method=method)
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, (json.loads(raw) if raw else None)


class BffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="bff-test-")
        cls.jellyfin, cls.jellyfin_url = start(FakeJellyfin)
        cls.seerr, cls.seerr_url = start(FakeSeerr)
        cls.media, cls.media_url = start(FakeMediaAgent)
        cls.gaming, cls.gaming_url = start(FakeGaming)

        cls.cfg = api_v1.Config(
            jellyfin_url=cls.jellyfin_url,
            seerr_url=cls.seerr_url,
            state_dir=cls.tmp,
            token_ttl=3600,
            jellyfin_cache_ttl=300,
            negative_cache_ttl=30,
            timeout=5,
            allowed_networks=(api_v1.ipaddress.ip_network("127.0.0.0/8"),),
            media_agent_url=cls.media_url,
            gaming_url=cls.gaming_url,
            rate_limit_session=1000,
            rate_limit_default=1000,
        )
        cls.services = api_v1.Services(cls.cfg)
        cls.public, cls.public_url = api_v1.make_server(cls.services, public=True, port=0)
        cls.admin, cls.admin_url = api_v1.make_server(cls.services, public=False, port=0)
        for server in (cls.public, cls.admin):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        for server in (cls.public, cls.admin):
            server.shutdown()
            server.server_close()
        cls.jellyfin.shutdown()
        cls.seerr.shutdown()
        cls.media.shutdown()
        cls.gaming.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        FakeSeerr.requests_status = 200
        FakeSeerr.last_cookie = None
        FakeSeerr.include_tv_request = False
        FakeSeerr.last_request_body = None
        FakeSeerr.request_status = 201
        FakeSeerr.request_payload = None
        FakeMediaAgent.last = {}
        FakeMediaAgent.owner_pairs = []
        FakeJellyfin.me_calls = 0
        self.services.auth._cache.clear()
        self.services.store.delete("u-user", "dev-1")
        self.services.store.delete("u-admin", "dev-admin")

    # ---- helpers --------------------------------------------------------

    def login(self, device="dev-1", token="jf-user"):
        status, data = http(
            "POST", f"{self.public_url}/api/v1/session",
            {"access_token": token, "device_id": device},
        )
        self.assertEqual(status, 200, data)
        return data["token"], data

    def link(self, bff_token, device="dev-1"):
        return http(
            "POST", f"{self.public_url}/api/v1/session/seerr",
            {"username": "wagner", "password": "segredo", "device_id": device},
            token=bff_token,
        )

    # ---- testes ---------------------------------------------------------

    def test_status_sem_auth(self):
        status, data = http("GET", f"{self.public_url}/api/v1/status")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")

    def test_head_status(self):
        status, data = http("HEAD", f"{self.public_url}/api/v1/status")
        self.assertEqual(status, 200)
        self.assertIsNone(data)

    def test_rota_inexistente_404(self):
        status, data = http("GET", f"{self.public_url}/api/v1/nao-existe")
        self.assertEqual(status, 404)
        self.assertEqual(data["code"], "not_found")

    def test_session_token_invalido(self):
        status, data = http(
            "POST", f"{self.public_url}/api/v1/session",
            {"access_token": "token-que-nao-existe", "device_id": "dev-1"},
        )
        self.assertEqual(status, 401)
        self.assertEqual(data["code"], "invalid_token")
        self.assertIn("message", data)

    def test_session_sem_device(self):
        status, data = http(
            "POST", f"{self.public_url}/api/v1/session",
            {"access_token": "jf-user"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(data["code"], "device_id_required")

    def test_session_e_me(self):
        token, data = self.login()
        self.assertFalse(data["seerr_linked"])
        self.assertFalse(data["user"]["is_admin"])

        status, me = http("GET", f"{self.public_url}/api/v1/me", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(me["user"]["name"], "Wagner")
        self.assertEqual(me["device_id"], "dev-1")
        self.assertFalse(me["seerr_linked"])

    def test_me_sem_token(self):
        status, data = http("GET", f"{self.public_url}/api/v1/me")
        self.assertEqual(status, 401)
        self.assertEqual(data["code"], "unauthorized")

    def test_token_adulterado(self):
        token, _ = self.login()
        body, signature = token.rsplit(".", 1)
        fake = body + ".x" + signature[1:]
        status, data = http("GET", f"{self.public_url}/api/v1/me", token=fake)
        self.assertEqual(status, 401)
        self.assertEqual(data["code"], "invalid_session")

    def test_link_seerr_e_cookie_cifrado(self):
        token, _ = self.login()
        status, data = self.link(token)
        self.assertEqual(status, 200, data)
        self.assertTrue(data["seerr_linked"])

        path = os.path.join(self.tmp, "v1_sessions.json")
        with open(path, encoding="utf-8") as handle:
            raw = handle.read()
        self.assertNotIn(SEERR_COOKIE, raw, "cookie do Seerr não pode ficar em claro")
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

        status, me = http("GET", f"{self.public_url}/api/v1/me", token=token)
        self.assertTrue(me["seerr_linked"])
        self.assertIsNotNone(me["seerr_expires_at"])

    def test_cookie_sobrevive_a_restart(self):
        token, _ = self.login()
        self.link(token)

        outro = api_v1.Services(self.cfg)
        got = outro.store.get("u-user", "dev-1")
        self.assertIsNotNone(got)
        self.assertEqual(got[0], SEERR_COOKIE)

    def test_link_com_senha_errada(self):
        token, _ = self.login()
        status, data = http(
            "POST", f"{self.public_url}/api/v1/session/seerr",
            {"username": "wagner", "password": "errada", "device_id": "dev-1"},
            token=token,
        )
        self.assertEqual(status, 401)
        self.assertEqual(data["code"], "seerr_invalid_credentials")

    def test_pedidos_usa_cookie_da_pessoa(self):
        token, _ = self.login()
        self.link(token)
        status, data = http("GET", f"{self.public_url}/api/v1/requests", token=token)
        self.assertEqual(status, 200, data)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(FakeSeerr.last_cookie, f"connect.sid={SEERR_COOKIE}")

    def test_pedidos_enriquece_titulo_e_poster(self):
        token, _ = self.login()
        self.link(token)
        status, data = http("GET", f"{self.public_url}/api/v1/requests", token=token)
        self.assertEqual(status, 200, data)
        media = data["results"][0]["media"]
        self.assertEqual(media["title"], "Matrix")
        self.assertEqual(media["posterPath"], "/matrix.jpg")

    def test_pedidos_traz_status_da_arr(self):
        token, _ = self.login()
        self.link(token)
        status, data = http("GET", f"{self.public_url}/api/v1/requests", token=token)
        self.assertEqual(status, 200, data)
        arr = data["results"][0]["media"]["arr"]
        self.assertEqual(arr["key"], "movie:tmdb:1")
        self.assertEqual(arr["status"], "error")
        self.assertEqual(arr["progress"], 79)
        self.assertEqual(arr["id"], 1)

    def test_esconder_pedido(self):
        token, _ = self.login()
        status, data = http(
            "POST", f"{self.public_url}/api/v1/requests/hide",
            {"key": "movie:tmdb:1"}, token=token,
        )
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"])

    def test_trocar_perfil(self):
        token, _ = self.login()
        status, data = http(
            "POST", f"{self.public_url}/api/v1/requests/profile",
            {"kind": "series", "id": 1399, "profile": "legendado"}, token=token,
        )
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"])

    def test_pedidos_sem_vincular(self):
        token, _ = self.login()
        status, data = http("GET", f"{self.public_url}/api/v1/requests", token=token)
        self.assertEqual(status, 409)
        self.assertEqual(data["code"], "seerr_not_linked")

    def test_seerr_expirado_vira_401(self):
        token, _ = self.login()
        self.link(token)
        FakeSeerr.requests_status = 401
        status, data = http("GET", f"{self.public_url}/api/v1/requests", token=token)
        self.assertEqual(status, 401)
        self.assertEqual(data["code"], "seerr_session_expired")

    def test_criar_pedido(self):
        token, _ = self.login()
        self.link(token)
        status, data = http(
            "POST", f"{self.public_url}/api/v1/requests",
            {"media_type": "tv", "media_id": 1399, "seasons": [1, 2]},
            token=token,
        )
        self.assertEqual(status, 201, data)
        self.assertEqual(data["echo"]["seasons"], [1, 2])
        self.assertEqual(data["echo"]["mediaType"], "tv")

    def test_criar_pedido_com_perfil(self):
        token, _ = self.login()
        self.link(token)
        status, data = http(
            "POST", f"{self.public_url}/api/v1/requests",
            {"media_type": "movie", "media_id": 603, "profile": "dublado"},
            token=token,
        )
        self.assertEqual(status, 201, data)
        self.assertEqual(data["echo"]["profileId"], 8)

    def test_search(self):
        token, _ = self.login()
        self.link(token)
        status, data = http(
            "GET", f"{self.public_url}/api/v1/search?q=matrix", token=token
        )
        self.assertEqual(status, 200, data)
        self.assertEqual(data["results"][0]["title"], "Matrix")
        self.assertEqual(FakeSeerr.last_cookie, f"connect.sid={SEERR_COOKIE}")

    def test_discover(self):
        token, _ = self.login()
        self.link(token)
        status, data = http("GET", f"{self.public_url}/api/v1/discover", token=token)
        self.assertEqual(status, 200, data)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["items"][0]["mediaType"], "movie")
        self.assertEqual(data["items"][0]["title"], "Matrix")
        self.assertEqual(data["items"][1]["mediaType"], "tv")

    def test_search_sem_termo(self):
        token, _ = self.login()
        self.link(token)
        status, data = http("GET", f"{self.public_url}/api/v1/search", token=token)
        self.assertEqual(status, 400)
        self.assertEqual(data["code"], "query_required")

    def test_search_sem_vincular(self):
        token, _ = self.login()
        status, data = http(
            "GET", f"{self.public_url}/api/v1/search?q=matrix", token=token
        )
        self.assertEqual(status, 409)
        self.assertEqual(data["code"], "seerr_not_linked")

    def test_criar_pedido_invalido(self):
        token, _ = self.login()
        self.link(token)
        status, data = http(
            "POST", f"{self.public_url}/api/v1/requests",
            {"media_type": "serie", "media_id": 1},
            token=token,
        )
        self.assertEqual(status, 400)
        self.assertEqual(data["code"], "invalid_media_type")

    def test_logout_remove_vinculo(self):
        token, _ = self.login()
        self.link(token)
        status, data = http(
            "POST", f"{self.public_url}/api/v1/session/logout", {}, token=token
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["removed"])

        status, data = http("GET", f"{self.public_url}/api/v1/requests", token=token)
        self.assertEqual(status, 409)
        self.assertEqual(data["code"], "seerr_not_linked")

    def test_cookie_nao_vaza_na_resposta(self):
        token, data = self.login()
        self.link(token)
        status, body = http("GET", f"{self.public_url}/api/v1/me", token=token)
        self.assertNotIn(SEERR_COOKIE, json.dumps(body))
        self.assertNotIn(SEERR_COOKIE, json.dumps(data))

    def test_cache_de_validacao(self):
        self.login()
        self.login()
        self.assertEqual(FakeJellyfin.me_calls, 1)

    def test_cache_negativo(self):
        http(
            "POST", f"{self.public_url}/api/v1/session",
            {"access_token": "jf-revogado", "device_id": "dev-1"},
        )
        http(
            "POST", f"{self.public_url}/api/v1/session",
            {"access_token": "jf-revogado", "device_id": "dev-1"},
        )
        self.assertEqual(FakeJellyfin.me_calls, 1)

    # ---- casa / legendas / downloads -----------------------------------

    def test_house(self):
        token, _ = self.login()
        status, data = http("GET", f"{self.public_url}/api/v1/house", token=token)
        self.assertEqual(status, 200, data)
        self.assertEqual(data["host"]["name"], "teste")
        self.assertEqual(data["cpu"]["cores"], 4)
        self.assertFalse(data["throttled"])
        self.assertEqual(data["storage"][0]["label"], "Mídia 2TB")

    def test_house_sem_auth(self):
        status, data = http("GET", f"{self.public_url}/api/v1/house")
        self.assertEqual(status, 401)
        self.assertEqual(data["code"], "unauthorized")

    def test_services(self):
        token, _ = self.login()
        status, data = http("GET", f"{self.public_url}/api/v1/services", token=token)
        self.assertEqual(status, 200, data)
        por_id = {item["id"]: item for item in data["services"]}
        self.assertTrue(por_id["jellyfin"]["ok"], por_id["jellyfin"])
        self.assertTrue(por_id["seerr"]["ok"], por_id["seerr"])
        self.assertIn("radarr", por_id)
        self.assertIn("qbittorrent", por_id)

    def test_services_sem_auth(self):
        status, data = http("GET", f"{self.public_url}/api/v1/services")
        self.assertEqual(status, 401)
        self.assertEqual(data["code"], "unauthorized")

    def test_pc_status(self):
        token, _ = self.login()
        status, data = http("GET", f"{self.public_url}/api/v1/pc", token=token)
        self.assertEqual(status, 200, data)
        self.assertFalse(data["online"])
        self.assertEqual(data["status"], "Desligado")
        self.assertNotIn("mac", data)
        self.assertNotIn("ips", data)

    def test_pc_wake(self):
        token, _ = self.login()
        status, data = http("POST", f"{self.public_url}/api/v1/pc/wake", {}, token=token)
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"])

    def test_pc_sem_auth(self):
        status, data = http("GET", f"{self.public_url}/api/v1/pc")
        self.assertEqual(status, 401)
        self.assertEqual(data["code"], "unauthorized")

    def test_subs_queue(self):
        token, _ = self.login()
        status, data = http("GET", f"{self.public_url}/api/v1/subs/queue", token=token)
        self.assertEqual(status, 200, data)
        self.assertEqual(len(data["items"]), 1)
        item = data["items"][0]
        self.assertEqual(item["title"], "Bleach")
        self.assertEqual(item["episode"], "17x41")
        self.assertIn("Portuguese (Brazil)", item["languages"])

    def test_media_agent_fora(self):
        cfg = api_v1.Config(
            jellyfin_url=self.jellyfin_url,
            seerr_url=self.seerr_url,
            state_dir=self.tmp,
            timeout=2,
            media_agent_url="http://127.0.0.1:1",
            rate_limit_session=1000,
            rate_limit_default=1000,
        )
        services = api_v1.Services(cfg)
        server, url = api_v1.make_server(services, public=True, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            token, _ = services.signer.issue("u-1", "Wagner", "dev-1", False)
            status, data = http("GET", f"{url}/api/v1/house", token=token)
            self.assertEqual(status, 503)
            self.assertEqual(data["code"], "media_agent_unavailable")
        finally:
            server.shutdown()
            server.server_close()

    def test_subs_quota_esconde_conta(self):
        token, _ = self.login()
        status, data = http("GET", f"{self.public_url}/api/v1/subs/quota", token=token)
        self.assertEqual(status, 200, data)
        self.assertEqual(data["remaining_downloads"], 15)
        blob = json.dumps(data)
        self.assertNotIn("conta-secreta", blob)
        self.assertNotIn("1412817", blob)

    def test_downloads_inexistente_no_publico(self):
        token, _ = self.login(token="jf-admin")
        status, data = http("GET", f"{self.public_url}/api/v1/admin/downloads", token=token)
        self.assertEqual(status, 404)
        self.assertEqual(data["code"], "not_found")

    def test_downloads_admin(self):
        token, _ = self.login(token="jf-admin")
        status, data = http("GET", f"{self.admin_url}/api/v1/admin/downloads", token=token)
        self.assertEqual(status, 200, data)
        self.assertEqual(data["items"][0]["progress"], 79)
        self.assertEqual(data["items"][0]["eta"], "108.13:20:52")
        self.assertEqual(data["items"][0]["requested_by"], "teste")

    def test_downloads_exige_admin(self):
        token, _ = self.login()
        status, data = http("GET", f"{self.admin_url}/api/v1/admin/downloads", token=token)
        self.assertEqual(status, 403)
        self.assertEqual(data["code"], "admin_required")

    def test_rate_limit_no_login(self):
        cfg = api_v1.Config(
            jellyfin_url=self.jellyfin_url,
            seerr_url=self.seerr_url,
            state_dir=self.tmp,
            timeout=5,
            media_agent_url=self.media_url,
            rate_limit_session=3,
            rate_limit_default=1000,
        )
        services = api_v1.Services(cfg)
        server, url = api_v1.make_server(services, public=True, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            codes = [
                http("POST", f"{url}/api/v1/session",
                     {"access_token": "jf-user", "device_id": "dev-rl"})[0]
                for _ in range(4)
            ]
            self.assertEqual(codes[:3], [200, 200, 200])
            self.assertEqual(codes[3], 429)
        finally:
            server.shutdown()
            server.server_close()

    # ---- admin (D6) -----------------------------------------------------

    def test_admin_inexistente_no_publico(self):
        token, _ = self.login(token="jf-admin")
        status, data = http("GET", f"{self.public_url}/api/v1/admin/ping", token=token)
        self.assertEqual(status, 404)
        self.assertEqual(data["code"], "not_found")

    def test_admin_exige_administrador(self):
        token, _ = self.login()
        status, data = http("GET", f"{self.admin_url}/api/v1/admin/ping", token=token)
        self.assertEqual(status, 403)
        self.assertEqual(data["code"], "admin_required")

    def test_admin_ok_na_lan(self):
        cfg = api_v1.Config(
            jellyfin_url=self.jellyfin_url,
            seerr_url=self.seerr_url,
            state_dir=self.tmp,
            timeout=5,
            allowed_networks=(api_v1.ipaddress.ip_network("127.0.0.0/8"),),
        )
        services = api_v1.Services(cfg)
        server, url = api_v1.make_server(services, public=False, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            token, _ = services.signer.issue("u-admin", "admin", "dev-admin", True)
            status, data = http("GET", f"{url}/api/v1/admin/ping", token=token)
            self.assertEqual(status, 200, data)
            self.assertTrue(data["ok"])
        finally:
            server.shutdown()
            server.server_close()

    def test_admin_bloqueado_fora_da_lan(self):
        cfg = api_v1.Config(
            jellyfin_url=self.jellyfin_url,
            seerr_url=self.seerr_url,
            state_dir=self.tmp,
            timeout=5,
            allowed_networks=(api_v1.ipaddress.ip_network("10.0.0.0/8"),),
        )
        services = api_v1.Services(cfg)
        server, url = api_v1.make_server(services, public=False, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            token, _ = services.signer.issue("u-admin", "admin", "dev-admin", True)
            status, data = http("GET", f"{url}/api/v1/admin/ping", token=token)
            self.assertEqual(status, 403)
            self.assertEqual(data["code"], "admin_lan_only")
        finally:
            server.shutdown()
            server.server_close()


    # ---- packs por temporada (Fase 2) ----------------------------------

    def test_tv_temporadas_normalizadas(self):
        token, _ = self.login()
        self.link(token)
        status, data = http("GET", f"{self.public_url}/api/v1/tv/37680", token=token)
        self.assertEqual(status, 200, data)
        self.assertEqual(data["tvdbId"], 247808)
        self.assertEqual(data["title"], "Homens de Terno")
        self.assertFalse(data["anime"])
        seasons = {season["seasonNumber"]: season for season in data["seasons"]}
        self.assertNotIn(0, seasons)
        self.assertEqual(seasons[1]["status"], "available")
        self.assertTrue(seasons[1]["requested"])
        self.assertEqual(seasons[2]["status"], "missing")
        self.assertFalse(seasons[2]["requested"])

    def test_tv_anime(self):
        token, _ = self.login()
        self.link(token)
        status, data = http("GET", f"{self.public_url}/api/v1/tv/30984", token=token)
        self.assertEqual(status, 200, data)
        self.assertTrue(data["anime"])
        self.assertEqual(data["tvdbId"], 74796)

    def test_pedido_anime_usa_perfis_8_e_10(self):
        for profile, expected in (("legendado", 8), ("dublado", 10)):
            with self.subTest(profile=profile):
                token, _ = self.login()
                self.link(token)
                status, data = http(
                    "POST", f"{self.public_url}/api/v1/requests",
                    {"media_type": "tv", "media_id": 30984, "seasons": [1],
                     "profile": profile},
                    token=token,
                )
                self.assertEqual(status, 201, data)
                self.assertEqual(data["echo"]["profileId"], expected)
                self.assertIn("/sonarr/season/monitor", FakeMediaAgent.last)

    def test_pedido_serie_comum_dublado_perfil_9(self):
        token, _ = self.login()
        self.link(token)
        status, data = http(
            "POST", f"{self.public_url}/api/v1/requests",
            {"media_type": "tv", "media_id": 37680, "seasons": [1],
             "profile": "dublado"},
            token=token,
        )
        self.assertEqual(status, 201, data)
        self.assertEqual(data["echo"]["profileId"], 9)

    def test_pedidos_traz_pack(self):
        FakeSeerr.include_tv_request = True
        token, _ = self.login()
        self.link(token)
        status, data = http("GET", f"{self.public_url}/api/v1/requests", token=token)
        self.assertEqual(status, 200, data)
        pedido = next(
            item for item in data["results"]
            if item["media"]["mediaType"] == "tv"
        )
        media = pedido["media"]
        self.assertEqual(media["pack"]["key"], "tvdb:247808:s1")
        self.assertEqual(media["pack"]["status"], "downloading")
        self.assertEqual(media["pack"]["statusLabel"], "Baixando 42%")
        temporadas = {job["season"] for job in media["packs"]}
        self.assertEqual(temporadas, {1})
        self.assertNotIn(999, [job["tvdbId"] for job in media["packs"]])

    def test_temporada_parcial_usa_fallback(self):
        FakeSeerr.request_status = 202
        FakeSeerr.request_payload = {"message": "No seasons available to request"}
        token, _ = self.login()
        self.link(token)
        status, data = http(
            "POST", f"{self.public_url}/api/v1/requests",
            {"media_type": "tv", "media_id": 37680, "seasons": [1],
             "profile": "legendado"},
            token=token,
        )
        self.assertEqual(status, 201, data)
        self.assertTrue(data.get("fallback"))
        self.assertIn("/sonarr/season/monitor", FakeMediaAgent.last)
        self.assertIn("/pack-jobs/ensure", FakeMediaAgent.last)
        self.assertEqual(FakeMediaAgent.last["/pack-owners"]["user_id"], "u-user")
        self.assertEqual(FakeMediaAgent.last["/pack-owners"]["seasons"], [1])

    def test_202_sem_serie_vira_409(self):
        FakeSeerr.request_status = 202
        FakeSeerr.request_payload = {"message": "No seasons available to request"}
        token, _ = self.login()
        self.link(token)
        status, data = http(
            "POST", f"{self.public_url}/api/v1/requests",
            {"media_type": "tv", "media_id": 1399, "seasons": [1]},
            token=token,
        )
        self.assertEqual(status, 409, data)
        self.assertEqual(data["code"], "no_seasons_available")

    def test_requests_inclui_pack_local(self):
        FakeMediaAgent.owner_pairs = [{
            "tvdbId": 360295, "season": 1, "tmdbId": 68507,
            "title": "His Dark Materials", "posterPath": "/hdm.jpg",
        }]
        token, _ = self.login()
        self.link(token)
        status, data = http("GET", f"{self.public_url}/api/v1/requests", token=token)
        self.assertEqual(status, 200, data)
        cards = [
            item for item in data["results"]
            if (item.get("media") or {}).get("tvdbId") == 360295
        ]
        self.assertEqual(len(cards), 1, data)
        media = cards[0]["media"]
        self.assertEqual(media["name"], "His Dark Materials")
        self.assertEqual(media["posterPath"], "/hdm.jpg")
        self.assertEqual(media["pack"]["key"], "tvdb:360295:s1")
        self.assertEqual(media["pack"]["status"], "queued")

    def test_retry_pack(self):
        token, _ = self.login()
        status, data = http(
            "POST", f"{self.public_url}/api/v1/requests/retry",
            {"key": "tvdb:247808:s1"}, token=token,
        )
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"])
        self.assertEqual(
            FakeMediaAgent.last["/pack-jobs/retry"],
            {"key": "tvdb:247808:s1"},
        )

    def test_accept_single(self):
        token, _ = self.login()
        status, data = http(
            "POST", f"{self.public_url}/api/v1/requests/accept-single",
            {"tvdbId": 247808, "season": 1}, token=token,
        )
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"])
        self.assertEqual(
            FakeMediaAgent.last["/pack-jobs/accept-single"],
            {"tvdbId": 247808, "season": 1},
        )

    def test_accept_single_sem_alvo(self):
        token, _ = self.login()
        status, data = http(
            "POST", f"{self.public_url}/api/v1/requests/accept-single",
            {}, token=token,
        )
        self.assertEqual(status, 400)
        self.assertEqual(data["code"], "pack_target_required")

    def test_notifications_filtra_por_usuario(self):
        token, _ = self.login()
        self.link(token)
        status, data = http("GET", f"{self.public_url}/api/v1/notifications", token=token)
        self.assertEqual(status, 200, data)
        self.assertEqual([item["id"] for item in data["notifications"]], [11])
        self.assertEqual(data["unread"], 1)

    def test_notifications_admin_ve_tudo(self):
        token, _ = self.login(device="dev-admin", token="jf-admin")
        self.link(token, device="dev-admin")
        status, data = http("GET", f"{self.public_url}/api/v1/notifications", token=token)
        self.assertEqual(status, 200, data)
        self.assertEqual(len(data["notifications"]), 2)

    def test_notification_mark_read(self):
        token, _ = self.login()
        status, data = http(
            "POST", f"{self.public_url}/api/v1/notifications/read",
            {"id": 11}, token=token,
        )
        self.assertEqual(status, 200, data)
        self.assertEqual(
            FakeMediaAgent.last["/notifications/read"],
            {"id": 11, "user_id": "u-user"},
        )

    def test_notification_mark_all_read(self):
        token, _ = self.login()
        status, data = http(
            "POST", f"{self.public_url}/api/v1/notifications/read-all",
            {}, token=token,
        )
        self.assertEqual(status, 200, data)
        self.assertEqual(
            FakeMediaAgent.last["/notifications/read-all"],
            {"user_id": "u-user"},
        )

    def test_devices_registrar_e_remover(self):
        token, _ = self.login()
        status, data = http(
            "POST", f"{self.public_url}/api/v1/devices",
            {"fcm_token": "tok-1", "platform": "android"}, token=token,
        )
        self.assertEqual(status, 200, data)
        self.assertEqual(
            FakeMediaAgent.last["/devices"],
            {"user_id": "u-user", "device_id": "dev-1",
             "fcm_token": "tok-1", "platform": "android"},
        )
        status, data = http(
            "DELETE", f"{self.public_url}/api/v1/devices/dev-1", token=token,
        )
        self.assertEqual(status, 200, data)
        self.assertIn("/devices/u-user/dev-1", FakeMediaAgent.last)

    def test_pack_action_sem_auth(self):
        status, data = http(
            "POST", f"{self.public_url}/api/v1/requests/retry", {"key": "x"}
        )
        self.assertEqual(status, 401)


class SecretBoxTest(unittest.TestCase):
    def test_roundtrip_e_nonces_diferentes(self):
        box = api_v1.SecretBox(b"k" * 32)
        a, b = box.seal(b"segredo"), box.seal(b"segredo")
        self.assertNotEqual(a, b)  # nonce novo a cada selagem
        self.assertEqual(box.open(a), b"segredo")
        self.assertEqual(box.open(b), b"segredo")

    def test_adulteracao_detectada(self):
        box = api_v1.SecretBox(b"k" * 32)
        blob = bytearray(box.seal(b"segredo"))
        blob[20] ^= 1
        with self.assertRaises(api_v1.ApiError) as ctx:
            box.open(bytes(blob))
        self.assertEqual(ctx.exception.code, "corrupt_state")

    def test_chave_errada_nao_abre(self):
        one, two = api_v1.SecretBox(b"a" * 32), api_v1.SecretBox(b"b" * 32)
        with self.assertRaises(api_v1.ApiError):
            two.open(one.seal(b"segredo"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
