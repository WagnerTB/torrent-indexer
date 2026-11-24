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

---

## 8. OpenCode on the Pi (next step, not yet done)

Goal: run OpenCode on the Pi and drive it from Android.

- Install OpenCode on the Pi (single binary; Bun provides `linux-arm64` — verify the installer picks arm64).
- Run as an always-on host: `opencode serve --hostname 0.0.0.0 --port 4096` (set `OPENCODE_PASSWORD` for a fixed password).
- Access from Android:
  - LAN: browser → `http://192.168.1.10:4096` + password.
  - Remote: `opencode pair --remote` (OpenTunnel, E2E encrypted) or QR scan from the OpenCode app.
- Caveats: Pi RAM is already tight from the media stack (watch headroom); keep it password-protected / tunneled.
