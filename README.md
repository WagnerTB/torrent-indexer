# torrent-indexer

[![](https://dcbadge.limes.pink/api/server/7wqNywmpQW)](https://discord.gg/7wqNywmpQW)
[![Sponsor](https://img.shields.io/badge/Sponsor-❤-ff69b4?style=for-the-badge&logo=github)](https://github.com/sponsors/felipemarinho97)

This is a simple torrent indexer that can be used to index torrents from HTML pages. It is written in Golang and uses Redis as a cache.

## Documentation

- **[SETUP.md](SETUP.md)** — step-by-step setup for a new machine: local indexer, Raspberry Pi stack, secrets, and the Homepage build.
- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) — architecture, endpoints, configuration and current state.
- [MEDIA_STACK.md](MEDIA_STACK.md) — media stack on the Pi (Radarr/Sonarr/Prowlarr/Bazarr/Jellyfin/Seerr/Homepage/agents).
- [SITE_STATUS.md](SITE_STATUS.md) — per-site status, known issues and validation results.
- [RASPBERRY_PI.md](RASPBERRY_PI.md) — Raspberry Pi 4 migration notes and checklist.
- [deploy/homepage/README.md](deploy/homepage/README.md) — Homepage `custom.js` source, build and deploy.
- [UI_AUDIT.md](UI_AUDIT.md) — UI plan, decisions and implementation status.
- [SECURITY_AUDIT.md](SECURITY_AUDIT.md) — security audit, secrets handling and rotation notes.

## Test it

Visit [https://torrent-indexer.darklyn.org/](https://torrent-indexer.darklyn.org/) to test it.

## Supported sites

- [comando-torrents](https://comando.la/)
- [bludv](https://bludvfilmes2.xyz/) - **downloads are currently behind an ad gate**; automatic extraction may return no results. See [SITE_STATUS.md](SITE_STATUS.md).
- [torrent-dos-filmes](https://torrentdosfilmes.se/)
- [starck-filmes](https://starckfilmes-v27.com/)
- [rede-torrent](https://redestorrents.com/)
- [vaca-torrent](https://vacatorrentmov.com/) - **currently unavailable**: the domain redirects to an unrelated site. See [SITE_STATUS.md](SITE_STATUS.md).

## Deploy

For the full walkthrough (local, Raspberry Pi, secrets, Homepage), see
**[SETUP.md](SETUP.md)**.

If you have Docker + Docker Compose installed, the indexer-only stack is:

```bash
git clone https://github.com/felipemarinho97/torrent-indexer.git
cd torrent-indexer
cp .env.example .env
# edit .env and set MEILI_MASTER_KEY (e.g. openssl rand -base64 32)
docker compose up -d --build
```

The server will be available at [http://localhost:8080/](http://localhost:8080/).
The root compose is intentionally simple (no persistent volumes). For the
Raspberry Pi media stack with persistent volumes and memory limits, use the
template in [deploy/raspberry/](deploy/raspberry/) and follow
[SETUP.md](SETUP.md#4-caminho-b--stack-completa-no-raspberry-pi).

## Configuration

You can configure the server using the following environment variables:
  
- `PORT`: (optional) The port that the server will listen to. Default: `7006`
- `METRICS_PORT`: (optional) The port that the metrics server will listen to. Default: `8081`
- `LOG_LEVEL`: (optional) The log level. Default: `1` (info). 
  - Possible values: `0` (debug), `1` (info), `2` (warn), `3` (error)
- `LOG_FORMAT`: (optional) The log format. Can be "json" or default to console logger.
- `FLARESOLVERR_ADDRESS`: (optional) The address of the FlareSolverr instance. Required for Cloudflare-protected indexers (`comando_torrents` and `bludv`). Default: `N/A`
- `FLARESOLVERR_TIMEOUT_SECONDS`: (optional) Timeout for flaresolverr requests. Default: `30` (the Pi uses `180` for Comando).
- `FLARESOLVERR_POOL_SIZE`: (optional) Number of FlareSolverr sessions in the pool. Default: `5`
- `FLARESOLVERR_USE_SESSIONS`: (optional) Reuse FlareSolverr sessions. Default: `false`; set `true` when the official FlareSolverr solves Cloudflare more reliably with a session (the Pi uses `true`).
- `REQUEST_TIMEOUT_MILLISECONDS`: (optional) Timeout for external scraping requests. Default: `5000`
- `MEILISEARCH_ADDRESS`: (optional) The address of the MeiliSearch instance. Default: `N/A`
- `MEILISEARCH_KEY`: (optional) The API key of the MeiliSearch instance. Default: `N/A`
- `REDIS_HOST`: (optional) The address of the Redis instance. Default: `localhost`
- `REDIS_PASSWORD`: (optional) The password of the Redis instance. Default: `N/A`
- `SHORT_LIVED_CACHE_EXPIRATION` (optional) The expiration time of the short-lived cache in duration format. Default: `30m`
    - This cache is used to cache homepage or search results.
    - Example: `30m`, `1h`, `1h30m`, `1h30m30s`
- `LONG_LIVED_CACHE_EXPIRATION` (optional) The expiration time of the long-lived cache in duration format. Default: `7d`
    - This cache is used to store the torrent webpages (posts). You can set it to a higher value because the torrent pages are not updated frequently.

### Extra Configuration
- `FALLBACK_TITLE_ENABLED`: (optional) Enable the fallback title post-processor that sets the title to "[UNSAFE] {original_title}" (Page title) if the title is empty. Default: `false`
    - This is useful for sites that do not have a title for some torrents, but can lead to misleading titles.
- `MAGNET_METADATA_API_ENABLED`: (optional) Enable the magnet metadata API. (deploy instrucitons [here](https://github.com/felipemarinho97/magnet-metadata-api)) Default: `false`
- `MAGNET_METADATA_API_ADDRESS`: (optional) The address of your magnet metadata API. Default: `N/A`
- `MAGNET_METADATA_API_TIMEOUT_SECONDS`: (optional) The timeout for the magnet metadata API requests in seconds. Default: `10`
- `INDEXER_<NAME>_URL`: (optional) Set a custom URL for the indexer. Where the "NAME" will be always uppercase indexer key with underscores. ex: `INDEXER_DODO_FILMES_URL=https://my-proxied-dodo-url.org`
- In the included `docker-compose.yml`, `MEILISEARCH_KEY` is set from `MEILI_MASTER_KEY` in your local `.env`.

### Secrets and local configuration

Do not commit real secrets, private IPs or WOL/MAC data.

- **Root `.env`:** copy `.env.example` to `.env` and set `MEILI_MASTER_KEY` (`openssl rand -base64 32`). The same key is used by the indexer and Meilisearch.
- **Raspberry Pi stack:** copy `deploy/raspberry/.env.example` to `.env` on the host and fill `MEILI_MASTER_KEY`, `LAN_IP`, `TAILSCALE_IP`, `ALLOWED_NETWORKS`, `PC_IP`, `PC_MAC`, `LAN_BROADCAST`, `MEDIA_ROOT` and `CONFIG_ROOT`.
- **WOL:** the password comes from `GAMING_PASSWORD` in `.env` (outside Git). `PC_IP`/`PC_MAC`/`LAN_BROADCAST` also come from `.env`; the agent still supports `.gaming_password` as a legacy fallback.
- `.env`, `.env.*` (except `.env.example`), `.gaming_password`, `.bazarr_key`, `requests.db`, `state/` and `*.local.md` are ignored by Git.
- The runbooks (`PROJECT_OVERVIEW.md`, `SITE_STATUS.md`, `RASPBERRY_PI.md`, `MEDIA_STACK.md`) use placeholders such as `<LAN_IP>` and `<TAILSCALE_IP>`. The files with real values are kept locally as `*.local.md` and are ignored.
- See **[SECURITY_AUDIT.md](SECURITY_AUDIT.md)** for the audit, false positives and key-rotation notes.

## Integrating with Jackett

You can integrate this indexer with Jackett by adding a new Torznab custom indexer. Here is an example of how to do it for the `bludv` indexer:

```yaml
---
id: bludv_indexer
name: BluDV Indexer
description: "BluDV - Custom indexer on from torrent-indexer"
language: pt-BR
type: public
encoding: UTF-8
links:
  - http://localhost:8080/

caps:
  categorymappings:
    - { id: Movie, cat: Movies, desc: "Movies" }
    - { id: TV, cat: TV, desc: "TV" }

  modes:
    search: [q]
    tv-search: [q, season, ep]
    movie-search: [q]
  allowrawsearch: true

settings: []

search:
  paths:
    - path: "indexers/bludv?filter_results=true&q={{ .Keywords }}"
      response:
        type: json

  keywordsfilters:
    - name: tolower

  rows:
    selector: $.results
    count:
      selector: $.count

  fields:
    _id:
      selector: title
    download:
      selector: magnet_link
    title:
      selector: title
    description:
      selector: original_title
    details:
      selector: details
    infohash:
      selector: info_hash
    date:
      selector: date
    size:
      selector: size
    seeders:
      selector: seed_count
    leechers:
      selector: leech_count
    imdb:
      selector: imdb
    category_is_tv_show:
      selector: title
      filters:
        - name: regexp
          args: "\\b(S\\d+(?:E\\d+)?)\\b"
    category:
      text: "{{ if .Result.category_is_tv_show }}TV{{ else }}Movie{{ end }}"
# json engine n/a
```

## Integrating with Prowlarr

You can integrate this indexer with Prowlarr by adding a custom definition. See [Adding a custom YML definition](https://wiki.servarr.com/prowlarr/indexers#adding-a-custom-yml-definition).

```yaml
---
id: torrent-indexer
name: Torrent Indexer
description: "Indexing Brazilian Torrent websites into structured data. github.com/felipemarinho97/torrent-indexer"
language: pt-BR
type: public
encoding: UTF-8
links:
  - http://localhost:8080/

caps:
  categories:
    Movies: Movies
    TV: TV

  modes:
    search: [q]
    tv-search: [q, season]
    movie-search: [q]

settings:
  - name: indexer
    type: select
    label: Indexer
    default: bludv
    options:
      search: Torrent-Indexer Cache
      bludv: BLUDV
      comando_torrents: Comando Torrents
      torrent-dos-filmes: Torrent dos Filmes
      starck-filmes: Starck Filmes
      rede_torrent: Rede Torrent
      vaca_torrent: Vaca Torrent

search:
  paths:
    - path: "{{ if eq .Config.indexer \"search\" }}/search{{ else }}/indexers/{{ .Config.indexer }}{{ end }}"
      response:
        type: json
  inputs:
    filter_results: "true"
    q: "{{ .Keywords }}"
  keywordsfilters:
    - name: tolower
    - name: re_replace
      args: ["(?i)(S0)(\\d{1,2})$", "temporada $2"]
    - name: re_replace
      args: ["(?i)(S)(\\d{1,3})$", "temporada $2"]

  rows:
    selector: $.results
    count:
      selector: $.count

  fields:
    download:
      selector: magnet_link
    title:
      selector: title
    description:
      selector: original_title
    details:
      selector: details
    infohash:
      selector: info_hash
    date:
      selector: date
    size:
      selector: size
    seeders:
      selector: seed_count
    leechers:
      selector: leech_count
    imdb:
      selector: imdb
    category_is_tv_show:
      selector: title
      filters:
        - name: regexp
          args: "\\b(S\\d+(?:E\\d+)?)\\b"
    category:
      text: "{{ if .Result.category_is_tv_show }}TV{{ else }}Movies{{ end }}"
```


## Mirrors

- N/A

### Community Mirrors

If you're running a public instance of torrent-indexer and would like to share it with the community, please open a **Merge Request** adding your instance to this list!

**Requirements for community mirrors:**
- Must be publicly accessible
- Should have reasonable uptime
- Include geographic location information
- Provide contact information for maintenance issues

# Warning

The instance running at [https://torrent-indexer.darklyn.org/](https://torrent-indexer.darklyn.org/) is my personal instance and it is not guaranteed to be up all the time. Also, for better availability, I recommend deploying your own instance because the Cloudflare protection may block requests from indexed sites if too many requests are made in a short period of time from the same IP.

If I notice that the instance is being used a lot, I may block requests from Jackett/Prowlarr to avoid overloading the server. I can also redirect your requests to a fake instance without prior notice. Consider yourself warned.

## If you cannot self-host

**If you really need to use my [instance](https://torrent-indexer.darklyn.org) continuously without the risk of being IP blocked, please subscribe to my [GitHub Sponsors](https://github.com/sponsors/felipemarinho97) (any tier) and let me know about your support ❤️ via [Discord](https://discord.gg/7wqNywmpQW).**
