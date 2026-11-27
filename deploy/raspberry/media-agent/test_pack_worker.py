#!/usr/bin/env python3
"""Testes do worker de packs por temporada (media-agent).

Rodam sem rede e sem tocar no Sonarr: cobrem filtro/ranking, completude,
política de tentativas e o banco de jobs/notificações.

    cd deploy/raspberry/media-agent
    python3 -m unittest test_pack_worker -v
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import media_agent as ma


def release(**overrides):
    base = {
        "guid": "guid-1",
        "indexerId": 3,
        "indexer": "1337x (Prowlarr)",
        "title": "Suits.S02.1080p.BluRay.x265-RARBG",
        "size": 11_570_000_000,
        "seeders": 77,
        "leechers": 2,
        "quality": {"quality": {"name": "Bluray-1080p"}},
        "qualityWeight": 1500,
        "fullSeason": True,
        "rejected": False,
        "downloadAllowed": True,
        "mappedSeasonNumber": 2,
        "mappedEpisodeNumbers": list(range(1, 17)),
        "tvdbId": 247808,
    }
    base.update(overrides)
    return base


class PackFilterTests(unittest.TestCase):
    def test_aceita_pack_completo(self):
        reasons = ma.pack_evaluate_release(release(), 2, tvdb_id=247808, expected_episodes=16)
        self.assertEqual(reasons, [])

    def test_recusa_episodio_solto(self):
        reasons = ma.pack_evaluate_release(release(fullSeason=False), 2)
        self.assertIn("nao_e_pack_temporada", reasons)

    def test_recusa_rejeitado_e_sem_download(self):
        self.assertIn("rejeitado_sonarr", ma.pack_evaluate_release(release(rejected=True), 2))
        self.assertIn(
            "download_nao_permitido",
            ma.pack_evaluate_release(release(downloadAllowed=False), 2),
        )

    def test_recusa_temporada_errada(self):
        reasons = ma.pack_evaluate_release(release(mappedSeasonNumber=17), 1)
        self.assertIn("temporada_incorreta:17", reasons)

    def test_recusa_multi_temporada(self):
        for title in (
            "Suits (2011) Season 1-9 S01-S09 Extras",
            "Suits COMPLETE S01 S02 S03",
            "Bleach (2004) S01 S08 (E001 E167)",
            "Suits.S01-S09.COMPLETE.SERIES.1080p",
        ):
            with self.subTest(title=title):
                reasons = ma.pack_evaluate_release(release(title=title), 2)
                self.assertIn("multi_temporada", reasons)

    def test_recusa_tvdb_divergente(self):
        reasons = ma.pack_evaluate_release(release(tvdbId=999), 2, tvdb_id=247808)
        self.assertIn("tvdb_divergente", reasons)

    def test_recusa_anime_com_mapeamento_quebrado(self):
        # 138 GB mapeados como 20 episódios de S1 = 6,9 GB/ep > teto 1080p.
        big = release(size=138_727_440_384, mappedEpisodeNumbers=list(range(1, 367)))
        reasons = ma.pack_evaluate_release(big, 1, expected_episodes=20)
        self.assertTrue(any(reason.startswith("tamanho_por_episodio:") for reason in reasons))

    def test_ranking_seeders_depois_qualidade(self):
        a = release(guid="a", seeders=10, qualityWeight=2000, size=5_000_000_000)
        b = release(guid="b", seeders=80, qualityWeight=1000, size=1_000_000_000)
        c = release(guid="c", seeders=10, qualityWeight=3000, size=1_000_000_000)
        accepted, _ = ma.pack_filter_releases([a, b, c], 2)
        self.assertEqual([item["guid"] for item in accepted], ["b", "c", "a"])

    def test_filtro_conta_recusados(self):
        accepted, skipped = ma.pack_filter_releases(
            [release(), release(guid="x", fullSeason=False), release(guid="y", rejected=True)],
            2,
        )
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(skipped), 2)
        self.assertIn("nao_e_pack_temporada", skipped[0]["reasons"])


class PackEpisodeStatsTests(unittest.TestCase):
    def _episode(self, number, hours, has_file=False, monitored=True):
        air = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")
        return {
            "seasonNumber": 1,
            "episodeNumber": number,
            "airDateUtc": air,
            "hasFile": has_file,
            "monitored": monitored,
        }

    def test_conta_exibidos_arquivos_e_futuros(self):
        episodes = [
            self._episode(1, -72, True),
            self._episode(2, -48, True),
            self._episode(3, -24, False),
            self._episode(4, 24, False),
            self._episode(5, 48, False),
        ]
        stats = ma.pack_episode_stats(episodes, 1)
        self.assertEqual(stats["aired"], 3)
        self.assertEqual(stats["files"], 2)
        self.assertEqual(stats["missing"], 1)
        self.assertEqual(stats["future"], 2)

    def test_ignora_outras_temporadas_e_especiais(self):
        episodes = [self._episode(1, -10, True)]
        special = dict(self._episode(1, -10, True), seasonNumber=0)
        other = dict(self._episode(1, -10, True), seasonNumber=2)
        stats = ma.pack_episode_stats(episodes + [special, other], 1)
        self.assertEqual(stats["episodeCount"], 1)

    def test_sem_data_conta_como_exibido(self):
        stats = ma.pack_episode_stats([{"seasonNumber": 1, "hasFile": True}], 1)
        self.assertEqual(stats["aired"], 1)

    def test_final_air_date_usa_o_ultimo_episodio(self):
        episodes = [self._episode(1, -24, True), self._episode(2, 240, False)]
        stats = ma.pack_episode_stats(episodes, 1)
        self.assertEqual(stats["finalAirDate"][:10], episodes[1]["airDateUtc"][:10])


class PackDbCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pack-test-")
        self._old_dir, self._old_db = ma.STATE_DIR, ma.STATE_DB
        ma.STATE_DIR = self.tmp
        ma.STATE_DB = os.path.join(self.tmp, "requests.db")
        ma._pack_episode_cache.clear()
        ma._pack_release_cache.clear()
        ma._db_init()

    def tearDown(self):
        ma.STATE_DIR, ma.STATE_DB = self._old_dir, self._old_db
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _job(self, key="tvdb:1:s1", status="queued", attempts=0, **extra):
        record = {
            "key": key,
            "tvdb_id": 1,
            "series_id": 10,
            "season": 1,
            "status": status,
            "attempts": attempts,
            "max_attempts": 3,
            "created_at": ma._now_iso(),
            "meta": {"title": "Suits"},
        }
        record.update(extra)
        return ma._pack_job_upsert(record)


class PackJobTests(PackDbCase):
    def test_key_e_upsert(self):
        self.assertEqual(ma._pack_key(247808, 2), "tvdb:247808:s2")
        job = self._job("tvdb:247808:s2")
        self.assertEqual(job["status"], "queued")
        updated = ma._pack_job_update("tvdb:247808:s2", status="searching", attempts=1)
        self.assertEqual(updated["status"], "searching")
        self.assertEqual(updated["attempts"], 1)

    def test_status_label_com_progresso(self):
        job = self._job(status="downloading")
        job = ma._pack_job_update(job["key"], meta_patch={"progress": 37})
        self.assertEqual(ma._pack_status_label(job), "Baixando 37%")

    def test_tentativa_falha_reagenda_em_6h(self):
        job = self._job(attempts=1, status="searching")
        updated = ma._pack_fail(job, "Sem pack completo")
        self.assertEqual(updated["status"], "queued")
        next_at = ma._parse_iso(updated["next_attempt_at"])
        delta = (next_at - datetime.now(timezone.utc)).total_seconds()
        self.assertAlmostEqual(delta / 3600, 6.0, delta=0.2)

    def test_terceira_falha_vira_no_pack(self):
        job = self._job(attempts=3, status="searching")
        updated = ma._pack_fail(job, "Sem pack completo")
        self.assertEqual(updated["status"], "no_pack")
        notes = ma.notifications_payload("u1")["notifications"]
        self.assertEqual(notes[0]["kind"], "pack_no_pack")
        self.assertEqual(notes[0]["action"], "retry_pack")

    def test_retry_zera_tentativas(self):
        job = self._job("tvdb:2:s1", status="no_pack", attempts=3)
        result = ma.pack_retry({"key": job["key"]})
        self.assertTrue(result["ok"])
        self.assertEqual(result["job"]["status"], "queued")
        self.assertEqual(result["job"]["attempt"], 0)
        self.assertIsNone(result["job"]["nextAttemptAt"])

    def test_fila_posicao(self):
        self._job("tvdb:1:s1", created_at="2026-01-01T00:00:00Z")
        self._job("tvdb:1:s2", season=2, created_at="2026-01-02T00:00:00Z")
        payload = ma.pack_jobs_payload({})
        positions = {job["key"]: job["queuePosition"] for job in payload["jobs"]}
        self.assertEqual(positions["tvdb:1:s1"], 1)
        self.assertEqual(positions["tvdb:1:s2"], 2)

    def test_ignorado_nao_aparece_por_padrao(self):
        self._job("tvdb:1:s1", status="ignored")
        self.assertEqual(ma.pack_jobs_payload({})["count"], 0)
        self.assertEqual(ma.pack_jobs_payload({"includeIgnored": "1"})["count"], 1)

    def test_recupera_busca_orfa_sem_gastar_tentativa(self):
        job = self._job(status="searching", attempts=2)
        with ma._pack_lock:
            ma._pack_running.pop(job["key"], None)
        self.assertGreaterEqual(ma._pack_recover_jobs(), 1)
        updated = ma._pack_job_get(job["key"])
        self.assertEqual(updated["status"], "queued")
        self.assertEqual(updated["attempts"], 1)
        self.assertIsNone(updated["next_attempt_at"])

    def test_nao_recupera_busca_em_andamento(self):
        job = self._job(status="searching", attempts=1)
        with ma._pack_lock:
            ma._pack_running[job["key"]] = object()
        try:
            ma._pack_recover_jobs()
        finally:
            with ma._pack_lock:
                ma._pack_running.pop(job["key"], None)
        self.assertEqual(ma._pack_job_get(job["key"])["status"], "searching")

    def test_dry_run_antigo_volta_para_fila_quando_desliga(self):
        job = self._job(
            status="pack_found", attempts=1, meta={"title": "HDM", "dryRun": True},
        )
        old = ma.PACK_WORKER_DRY_RUN
        ma.PACK_WORKER_DRY_RUN = False
        try:
            ma._pack_recover_jobs()
        finally:
            ma.PACK_WORKER_DRY_RUN = old
        updated = ma._pack_job_get(job["key"])
        self.assertEqual(updated["status"], "queued")
        self.assertEqual(updated["attempts"], 0)
        self.assertFalse(updated["meta"].get("dryRun"))

    def test_dry_run_nao_mexe_quando_ligado(self):
        job = self._job(
            status="pack_found", attempts=1, meta={"title": "HDM", "dryRun": True},
        )
        old = ma.PACK_WORKER_DRY_RUN
        ma.PACK_WORKER_DRY_RUN = True
        try:
            ma._pack_recover_jobs()
        finally:
            ma.PACK_WORKER_DRY_RUN = old
        self.assertEqual(ma._pack_job_get(job["key"])["status"], "pack_found")


class PackNotificationTests(PackDbCase):
    def test_dedupe_enquanto_nao_lido(self):
        first = ma._notify_create("pack_no_pack", "warning", key="tvdb:1:s1", title="Sem pack")
        second = ma._notify_create("pack_no_pack", "warning", key="tvdb:1:s1", title="Sem pack")
        self.assertEqual(first, second)

    def test_dedupe_solta_depois_de_lido(self):
        first = ma._notify_create("pack_no_pack", "warning", key="tvdb:1:s1", title="Sem pack")
        ma.notifications_mark_read(first, "u1")
        second = ma._notify_create("pack_no_pack", "warning", key="tvdb:1:s1", title="Sem pack")
        self.assertNotEqual(first, second)

    def test_leitura_por_usuario(self):
        note = ma._notify_create("pack_done", "success", key="tvdb:1:s1", title="Pack completo")
        payload = ma.notifications_payload("u1")
        self.assertEqual(payload["unread"], 1)
        self.assertFalse(payload["notifications"][0]["read"])
        ma.notifications_mark_read(note, "u1")
        self.assertEqual(ma.notifications_payload("u1")["unread"], 0)
        self.assertEqual(ma.notifications_payload("u2")["unread"], 1)

    def test_marcar_todos_como_lidos(self):
        ma._notify_create("pack_done", "success", key="a", title="A")
        ma._notify_create("pack_done", "success", key="b", title="B")
        ma.notifications_mark_all_read("u1")
        self.assertEqual(ma.notifications_payload("u1")["unread"], 0)

    def test_push_registrado(self):
        note = ma._notify_create("pack_done", "success", key="a", title="A")
        self.assertTrue(ma.notifications_mark_pushed(note, "u1")["ok"])
        row = ma._db_one(
            "SELECT * FROM notification_pushes WHERE notification_id = ? AND user_id = ?",
            (note, "u1"),
        )
        self.assertIsNotNone(row)


class PackDeviceTests(PackDbCase):
    def test_upsert_e_remove(self):
        self.assertTrue(ma.devices_upsert({
            "user_id": "u1", "device_id": "d1", "fcm_token": "tok-1", "platform": "android",
        })["ok"])
        ma.devices_upsert({
            "user_id": "u1", "device_id": "d1", "fcm_token": "tok-2", "platform": "android",
        })
        row = ma._db_one("SELECT * FROM devices WHERE user_id = ? AND device_id = ?", ("u1", "d1"))
        self.assertEqual(row["fcm_token"], "tok-2")
        self.assertEqual(ma.devices_remove("u1", "d1")["removed"], 1)
        self.assertIsNone(ma._db_one("SELECT * FROM devices WHERE user_id = ?", ("u1",)))

    def test_exige_token(self):
        self.assertFalse(ma.devices_upsert({"user_id": "u1", "device_id": "d1"})["ok"])


class PackOwnerTests(PackDbCase):
    def test_upsert_e_listagem(self):
        result = ma.pack_owners_upsert({
            "user_id": "u1", "tvdbId": 360295, "seasons": [1, 2],
            "tmdbId": 68507, "title": "His Dark Materials", "posterPath": "/x.jpg",
        })
        self.assertTrue(result["ok"])
        pairs = ma.pack_owners_payload("u1")["pairs"]
        self.assertEqual({pair["season"] for pair in pairs}, {1, 2})
        self.assertEqual(pairs[0]["tmdbId"], 68507)
        self.assertEqual(pairs[0]["title"], "His Dark Materials")

        ma.pack_owners_upsert({
            "user_id": "u1", "tvdbId": 360295, "seasons": [1],
            "tmdbId": 68507, "title": "HDM", "posterPath": "/y.jpg",
        })
        pairs = ma.pack_owners_payload("u1")["pairs"]
        self.assertEqual(len(pairs), 2)
        season1 = next(pair for pair in pairs if pair["season"] == 1)
        self.assertEqual(season1["title"], "HDM")
        self.assertEqual(season1["posterPath"], "/y.jpg")

    def test_exige_dados(self):
        self.assertFalse(ma.pack_owners_upsert({"user_id": "u1"})["ok"])


class PackJobEnsureTests(PackDbCase):
    def test_cria_queued_sem_sobrescrever(self):
        first = ma.pack_job_ensure({"tvdbId": 360295, "season": 1, "title": "HDM"})
        self.assertTrue(first["created"])
        self.assertEqual(first["job"]["status"], "queued")
        self.assertEqual(first["job"]["key"], "tvdb:360295:s1")

        second = ma.pack_job_ensure({"tvdbId": 360295, "season": 1})
        self.assertFalse(second["created"])
        self.assertEqual(second["job"]["key"], "tvdb:360295:s1")

    def test_ensure_grava_series_id_pelo_tvdb(self):
        original = ma._pack_series_by_tvdb
        ma._pack_series_by_tvdb = lambda tvdb_id, refresh=False: {"id": 11, "title": "HDM"}
        try:
            result = ma.pack_job_ensure({"tvdbId": 360295, "season": 1})
        finally:
            ma._pack_series_by_tvdb = original
        self.assertEqual(result["job"]["seriesId"], 11)

    def test_resolve_grava_series_id_do_job(self):
        job = self._job("tvdb:360295:s1", tvdb_id=360295, series_id=None)
        original = ma._pack_series_by_tvdb
        ma._pack_series_by_tvdb = lambda tvdb_id, refresh=False: {"id": 11}
        try:
            series, updated = ma._pack_resolve_series(job)
        finally:
            ma._pack_series_by_tvdb = original
        self.assertEqual(series["id"], 11)
        self.assertEqual(updated["series_id"], 11)


if __name__ == "__main__":
    unittest.main()
