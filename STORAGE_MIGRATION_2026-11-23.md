# Storage Expansion & Migration — 2026-11-23

> Record of all changes made to the `MAD4R4` (Raspberry Pi 4, `192.168.1.10`) media stack on
> 2026-11-23. Source of truth for follow-up work.

---

## 1. Quick resume (paste into a new OpenCode chat)

The Raspberry Pi `MAD4R4` (`192.168.1.10`, user `wagner`, SSH key auth works with `ssh wagner@192.168.1.10`)
runs a Docker media stack (Jellyfin, Sonarr, Radarr, Bazarr, Prowlarr, qBittorrent, Seerr, Homepage dashboard,
torrent-indexer, etc.) defined in `/home/wagner/media-stack/docker-compose.yml` (Compose project `media`).

On 2026-11-23 the stack was expanded from a single 240 GB SSD to three drives behind a **powered USB 3.0 hub**:

| Device | Size | Filesystem / label | Mount | Purpose |
|---|---|---|---|---|
| SSD (original, `sda`) | 240 GB | `sda2` NTFS `PiMedia`, `sda4` ext4 `DockerData` | `/srv/PiMedia`, `/srv/docker-data` | configs + misc, Docker |
| New (JMS583) | 2 TB | ext4 `media` | `/srv/media` | media library |
| New (JMS583) | 640 GB | ext4 `downloads` | `/srv/downloads` | torrent downloads |

Key facts for context:
- `.env` (`/home/wagner/media-stack/.env`): `MEDIA_ROOT=/srv/media`, `DOWNLOAD_ROOT=/srv/downloads`, `CONFIG_ROOT=/srv/PiMedia/docker`, `PUID/PGID=1000`.
- The compose bind-mounts the 640 GB at `/media/downloads` *over* the 2 TB's `/media`, so **all container paths stay identical** (`/media/movies`, `/media/downloads`, etc.) — no `*arr`/Jellyfin config changes were needed.
- Because downloads and media are now on **different filesystems**, Sonarr/Radarr imports are **copies, not hardlinks** (accepted tradeoff).
- The `media-agent` (port 8097) gained `/migration/status` and `/imports/active` endpoints; the Homepage `custom.js` gained a migration progress bar and an "import copy in progress" display; the dashboard storage panel now lists 4 storage entries.
- Everything was verified healthy on 2026-11-23 (all 17 containers up, Jellyfin sees media, qBittorrent writes to the 640 GB, dashboard reachable on `:3000`).
- **Post-migration fix (2026-11-24):** the qBittorrent queue was deadlocked by dead torrents, so no new data was written even though the mounts were fine. Save path is `/media/downloads`, temp moved to `/media/downloads/incomplete`, and slow torrents no longer count in the queue limit. See section 9.


---

## 2. Root cause & hardware changes

- **Problem:** dashboard (Homepage, `:3000`) and indexer (`:8080`) were down. Root cause: the original SSD (JMicron
  USB bridge) kept dropping off the USB bus due to **USB over-current** when an unpowered 1.8 TB HDD was added to a
  second USB port. The SSD re-enumerated under a new device name (`sdb`→`sda`), breaking its mounts and crashing Docker.
- **Fix (hardware):** user added a **powered USB 3.0 hub** (Genesys Logic) and moved drives onto it. Over-current gone.
- The 640 GB drive was initially on the **old VIA USB 2.0 hub** (link speed 480); after replugging into the USB 3.0
  Genesys hub it now runs at **5000** (SuperSpeed). Both new drives are JMS583 enclosures and share a firmware serial
  (`DD564198838A1`) — that's why they were initially mistaken for a single device; they are two distinct drives
  (different partition tables at sector 0).

---

## 3. Filesystems created

Formatted both new drives to ext4 (GPT, no reserved blocks):

- `/dev/sdb1` → ext4, label `media`, UUID `cf85da7d-caf7-44c6-9f75-51d4b812e5c3`
- `/dev/sdc1` → ext4, label `downloads`, UUID `4b5b911b-aca7-41b4-93ce-0cf379c5876e`

`/etc/fstab` additions (by UUID, robust to device renumbering):

```
UUID=cf85da7d-caf7-44c6-9f75-51d4b812e5c3 /srv/media ext4 defaults,noatime,nofail 0 2
UUID=4b5b911b-aca7-41b4-93ce-0cf379c5876e /srv/downloads ext4 defaults,noatime,nofail 0 2
```

Mount points `/srv/media` and `/srv/downloads` are owned by `wagner:wagner` (PUID/PGID 1000).

---

## 4. Data migration (completed)

`rsync -a --remove-source-files` moved data off the SSD:

| Data | Source | Destination |
|---|---|---|
| downloads | `/srv/PiMedia/downloads` | `/srv/downloads` (166 GB) |
| movies | `/srv/PiMedia/movies` | `/srv/media/movies` (67 GB) |
| Suits | `/srv/PiMedia/Suits` | `/srv/media/Suits` (42 GB) |
| animes | `/srv/PiMedia/animes` | `/srv/media/animes` (9.8 GB) |
| series | `/srv/PiMedia/series` | `/srv/media/series` (empty) |
| stremio-server | `/srv/PiMedia/stremio-server` | `/srv/media/stremio-server` |

`/srv/PiMedia` now holds only configs (`docker/`) + misc files; it dropped from 87% used to ~13%.

> **Note:** the Suits hardlinks (between `downloads` and `Suits`) were broken during the move because they now live on
> two different drives; each hardlinked MKV became an independent copy.

---

## 5. Configuration changes

### `.env` (`/home/wagner/media-stack/.env`, backup `.env.bak.storage`)
- `MEDIA_ROOT=/srv/PiMedia` → `/srv/media`
- added `DOWNLOAD_ROOT=/srv/downloads`

### `docker-compose.yml` (backup `docker-compose.yml.bak.storage`)
- Added `- ${DOWNLOAD_ROOT}:/media/downloads` (and `:ro` for media-agent) to **qbittorrent, sonarr, bazarr, jellyfin, radarr, media-agent** — keeps `/media/downloads` stable across the split.
- Updated `media-agent` `STORAGE_CONFIG` to include the new `media` (2 TB, `/media`) and `downloads` (640 GB, `/media/downloads`) entries.
- Added `/srv/media/.migration-status.json:/migration/status.json:ro` to media-agent.

### `media-agent` (`/srv/PiMedia/docker/media-agent/media_agent.py`, rebuilt image `media-agent:local`)
- Added `GET /migration/status` → `migration_status()` (reads the migration status JSON).
- Added `GET /imports/active` → `active_imports()` + `_import_fmt()` (detects files actively growing in the media folders, i.e. an in-progress import copy, returning name/library/size/rate).

### Homepage dashboard (`/srv/PiMedia/docker/homepage/custom.js`, backup `custom.js.bak.storage`)
- Added `renderMigration()` — shows a "Migração de dados" progress bar (one-time migration; now idle).
- Added `renderImports()` — shows a "Copiando para a biblioteca" section listing files currently being copied into the library with size + rate (the ongoing torrent→import flow).

### systemd
- `media-stack.service` (staggered `docker compose up -d`) — unchanged, but note it has `RequiresMountsFor=/srv/PiMedia /srv/docker-data`.

---

## 6. Jellyfin auto-update (already present, unchanged)

- `jellyfin-refresh.sh` + `.jellyfin_key` exist in `/srv/PiMedia/docker/{radarr,sonarr2}/scripts/`.
- Custom Script "Jellyfin Refresh" fires on Import/Upgrade/Rename → `POST /Library/Media/Updated`, fallback `/Library/Refresh`.
- So Jellyfin should auto-update after imports; the new `/imports/active` feature adds **visibility** of the copy itself.

---

## 7. Verification (2026-11-23, all passed)

- All 17 containers `Up`/`healthy`.
- qBittorrent `/media/downloads` → `/dev/sdd1` (640 GB).
- Jellyfin `/media` → `/dev/sdb1` (2 TB), lists movies (Angel-A, City of God, Demon Slayer, …).
- Dashboard `:3000` and indexer `:8080` reachable.
- `media-agent` `/storage` shows 4 entries: Mídia 2TB, Downloads 640GB, SSD 01, Sistema.

> **Nota (2026-11-24):** essa verificação olhou mounts/containers, mas não o
> estado da fila do qBittorrent. Os downloads novos ficaram presos em
> `queuedDL` por causa de torrents mortos ocupando os 3 slots; ver seção 9.

---

## 8. OpenCode on the Pi (done)

OpenCode está instalado e rodando no Pi (`opencode serve --service`), usado
para operar o stack (inclusive esta correção via API do qBittorrent/Sonarr).

- Acesso LAN: `http://192.168.1.10:4096` (com senha).
- Acesso remoto: Tailscale (`100.93.44.13`) ou `opencode pair --remote`.
- Cuidado com RAM: o stack usa ~2,5 GB dos 3,7 GB; rode um comando por vez em
  operações pesadas (builds, scans).

---

## 9. Correção pós-migração — fila do qBittorrent (2026-11-24)

**Sintoma:** pedidos no Seerr/Radarr/Sonarr funcionavam (eventos `grabbed`), o
dashboard mostrava "Baixando"/"Sem arquivo", mas nada aparecia em
`/srv/downloads` e o volume ficava em ~165 GB.

**Causa:** fila do qBittorrent saturada, não os caminhos.

- `queueing_enabled=true`, `max_active_downloads=3` e
  `dont_count_slow_torrents=false`.
- Os 3 slots estavam presos em His Dark Materials mortos (2 `stalledDL` com 0
  seeds + 1 `metaDL`); os outros 12 downloads ficavam `queuedDL` para sempre,
  inclusive The Wild Robot (563 seeds).
- Nada saía de 0%, então nenhum arquivo era escrito — "nada no caminho do
  qBittorrent" era consequência.
- Já vinha de antes da migração: último import concluído em 2026-11-18; os
  grabs do HDM travaram em 2026-11-22.

**Problema secundário:** `Session\TempPath=/media/temp/media/incomplete`
(caminho duplicado) mandava os parciais para o disco de mídia (2 TB) e, ao
concluir, o qBittorrent copiava tudo de volta para `/media/downloads`.

**Aplicado (API do qBittorrent):**

| Ajuste | Antes | Depois |
|---|---|---|
| `IgnoreSlowTorrentsForQueueing` | false | **true** |
| `MaxActiveDownloads` | 3 | **5** |
| `MaxActiveTorrents` | 5 | **10** |
| `SlowTorrentsDownloadRate` | 2 KiB/s | **100 KiB/s** |
| `TempPath` | `/media/temp/media/incomplete` | **`/media/downloads/incomplete`** |

- Criado `/srv/downloads/incomplete` (`abc:users`, 775).
- Removidos + blocklistados 4 episódios HDM mortos no Sonarr (E01, E02, E07,
  E08); em 13:41 outro cleanup removeu também E05/E06 (E03/E04 já tinham sido
  importados).
- O resume guarda `qBt-downloadPath` por torrent: quem foi adicionado antes da
  mudança continua usando o temp antigo até concluir; os novos já nascem em
  `/media/downloads/incomplete` (verificado).
- As chaves legadas `Downloads\SavePath` / `Downloads\TempPath` foram removidas
  do `qBittorrent.conf` com o container parado; após reiniciar, não voltaram.

**Validação:**

- Wild Robot saiu de `queuedDL` e baixou a 3,8 MB/s (563 seeds); importou no
  Radarr em 2026-11-24 16:50 UTC.
- 6 downloads ativos, ~13–16 MB/s no pico.
- Fim a fim: HDM E03/E04 concluíram → moveram para `/media/downloads` → Sonarr
  importou em `/srv/media/series/His Dark Materials/Season 1/` → Bazarr aplicou
  `.pt-BR.srt`.
- LOTR Fellowship importou no Radarr às 17:29 UTC.
- O temp antigo (`/srv/media/temp`) ainda tem os parciais da leva antiga; há uma
  limpeza automática agendada que remove apenas diretórios vazios.

**Resíduos removidos:**

- Sonarr: `RemotePathMapping` órfão (host `192.168.1.10`) e root folder
  `/media/downloads` sem uso.
- qBittorrent: chaves legadas citadas acima.
- Repo: `__pycache__` e arquivo `0`; `deploy/raspberry` e docs sincronizados
  com o Pi.

**Pendências:**

- `media-stack.service` só exige `/srv/PiMedia` e `/srv/docker-data` no
  `RequiresMountsFor`; incluir `/srv/media` e `/srv/downloads` evita subir a
  stack com um disco novo ausente.
- O `deploy/homepage/src` do repo não tem `renderMigration`/`renderImports`, que
  existem no `custom.js` servido pelo Pi (artefato editado direto no Pi).
  Sincronizar a fonte quando possível.
- HDM E05/E06 ficaram sem arquivo após o cleanup de 13:41; o Sonarr deve
  reprocurar no RSS.
