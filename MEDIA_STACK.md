# Stack de mídia no Raspberry Pi — operação e decisões

> **Nota de segurança:** IPs, MACs, usuários e caminhos absolutos foram substituídos por placeholders. Os valores reais ficam no `.env`/config local, fora do git. A senha do WOL agora usa `GAMING_PASSWORD` no `.env`; `.gaming_password` é fallback legado. Veja `SECURITY_AUDIT.md`.

Última atualização: 2026-11-24

Documentos relacionados:

- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) — arquitetura e endpoints do `torrent-indexer`.
- [RASPBERRY_PI.md](RASPBERRY_PI.md) — host, Docker, build e operação no Pi.
- [SITE_STATUS.md](SITE_STATUS.md) — status dos sites/indexadores e testes.
- [deploy/raspberry/docker-compose.yml](deploy/raspberry/docker-compose.yml) — cópia versionada do compose.

Este documento é a fonte de verdade do stack de mídia que roda no Pi
`<os_user>` (<LAN_IP>). O `torrent-indexer` continua documentado no
`PROJECT_OVERVIEW.md`; aqui ficam os serviços de mídia, o dashboard, as
legendas, os perfis e as decisões operacionais.

> **Segredos:** não copie API keys, senhas ou tokens para este documento.
> Eles ficam nos arquivos indicados em cada serviço e não devem ir para o Git.
> As chaves usadas pelo Homepage ficam em
> `<CONFIG_ROOT>/homepage/{services.yaml,custom.js}`; as dos *arr ficam
> em `<CONFIG_ROOT>/<serviço>/config.xml`; a do Prowlarr em
> `<CONFIG_ROOT>/prowlarr/config.xml`; a do Bazarr em
> `<CONFIG_ROOT>/bazarr/config/config.yaml`; a do Seerr em
> `<CONFIG_ROOT>/seerr/settings.json`.

## 1. Serviços e portas

Compose: `<STACK_ROOT>/docker-compose.yml` (projeto Compose
`media`). `.env` na mesma pasta, não versionar.

| Serviço | Imagem | Porta no host | Config |
|---|---|---|---|
| `torrent-indexer` | `media/torrent-indexer:local` | `8080` → `7006` (UI/API, remoto) e `<LAN_IP>:8081` (métricas, LAN) | build local; binário `torrent-indexer-linux-arm64` |
| `redis` | `redis:alpine` | interna | volume `redis-data` |
| `meilisearch` | `getmeili/meilisearch` | interna | volume `meili-data` |
| `solvearr` | `ghcr.io/flaresolverr/flaresolverr` | interna (`8191`) | FlareSolverr 3.5.0 usado pelo indexer; 1024 MB + `shm_size: 1gb` |
| `qbittorrent` | `lscr.io/linuxserver/qbittorrent` | `<LAN_IP>:8082` (WebUI), `6881` TCP/UDP | `<CONFIG_ROOT>/qbittorrent` |
| `sonarr` | `lscr.io/linuxserver/sonarr` | `<LAN_IP>:8989` | `<CONFIG_ROOT>/sonarr2` |
| `prowlarr` | `lscr.io/linuxserver/prowlarr` | `<LAN_IP>:9696` | `<CONFIG_ROOT>/prowlarr` |
| `bazarr` | `linuxserver/bazarr` | `<LAN_IP>:6767` | `<CONFIG_ROOT>/bazarr` |
| `jellyfin` | `jellyfin/jellyfin` | `8096` (remoto) | `<CONFIG_ROOT>/jellyfin` + `jellyfin-cache` |
| `stremio-server` | `stremio/server` | `11470`, `12470` (remoto) | `<MEDIA_ROOT>/stremio-server` |
| `homepage` | `ghcr.io/gethomepage/homepage` | `3000` (remoto, modo adaptativo) | `<CONFIG_ROOT>/homepage` |
| `gaming-agent` | `python:3.12-alpine` (script local) | `<LAN_IP>:8100` (privado, LAN) e `8098` (público: status/WOL com senha) | `<CONFIG_ROOT>/gaming-agent` |
| `media-agent` | `python:3.12-alpine` (script local) | `8097` (LAN + Tailscale, allowlist de IP) | `<CONFIG_ROOT>/media-agent` |
| `media-bff` | `media-agent:local` (mesmo `/app`) | `https://<BFF_HOST>` (Cloudflare Tunnel) e `<LAN_IP>:8091` (app na LAN) / `<LAN_IP>:8092` (admin, só LAN) | volume `media-bff-state` |
| `media-gateway` | `python:3.12-alpine` (script local) | interna (`8099`, rede `media`) | `<CONFIG_ROOT>/media-gateway` |
| `docker-socket-proxy` | `tecnativa/docker-socket-proxy` | interna (`2375`, rede `admin-internal`) | proxy restrito do Docker; só o `admin-agent` acessa |
| `admin-agent` | `admin-agent:local` | `<LAN_IP>:8093` (LAN only) | login dedicado; lista/start/stop/restart dos containers; auditoria em `<CONFIG_ROOT>/admin-agent/state` |
| `radarr` | `lscr.io/linuxserver/radarr` | `<LAN_IP>:7878` | `<CONFIG_ROOT>/radarr` |
| `seerr` | `seerr/seerr` (sucessor do Jellyseerr) | `5055` (remoto) | `<CONFIG_ROOT>/seerr` |
| `autoheal` | `willfarrell/autoheal` | interna | reinicia containers marcados com `autoheal=true` quando ficam unhealthy |

Acesso: **8096 (Jellyfin), 5055 (Seerr), 8080 (indexer/UI), 3000 (Homepage),
11470/12470 (Stremio), 8098 (gaming: status/WOL com senha) e 8097
(media-agent: Pedidos/Legendas)** ficam acessíveis pelo Tailscale; Radarr,
Sonarr, Prowlarr, Bazarr, qBittorrent, métricas, o **8100 privado** do
gaming-agent, o `media-gateway` e o `admin-agent` (**8093**) ficam presos ao IP
`<LAN_IP>` (LAN). O
**8099** do BFF fica em `127.0.0.1` e só sai pelo Cloudflare Tunnel (`<BFF_HOST>`); o **8091** atende o app na LAN e o **8092**
de admin fica preso à LAN. O
Homepage detecta o host: no Tailscale esconde os cards de gestão, mas mantém as
abas Pedidos/Legendas via media-agent.

Limites de memória usados: Jellyfin 1536 MB; solvearr/FlareSolverr 1024 MB;
Sonarr/qBittorrent/Meilisearch 512 MB; Prowlarr/Bazarr/Radarr/Seerr/Homepage
384 MB; indexer/Stremio 256 MB; media-gateway 128 MB; Redis 192 MB;
gaming-agent 64 MB; media-agent 96 MB; autoheal 32 MB.

O host também usa o watchdog de hardware do Pi (`/dev/watchdog0`, BCM2835,
timeout de 15 s) via `RuntimeWatchdogSec=15s` do systemd. O `autoheal` cobre
containers unhealthy; o watchdog cobre travamento total do sistema. Instalação:
`sudo sh deploy/raspberry/setup-watchdog.sh` (ver
[RASPBERRY_PI.md](RASPBERRY_PI.md#watchdog-de-hardware)).

## 2. Armazenamento e caminhos

Desde a migração de 2026-11-23 o stack usa três filesystems (detalhes em
[STORAGE_MIGRATION_2026-11-23.md](STORAGE_MIGRATION_2026-11-23.md)):

- Configs: `<CONFIG_ROOT>` (definido no `.env`; no Pi fica em `/srv/...`).
- Mídia (2 TB): `<MEDIA_ROOT>` montado como `/media` nos containers.
- Downloads (640 GB): `<DOWNLOAD_ROOT>` montado como `/media/downloads` em
  qBittorrent, Sonarr, Radarr, Bazarr, Jellyfin e media-agent (o mesmo caminho
  dentro de todos os containers).
- Biblioteca de séries: `<MEDIA_ROOT>/Suits` (a série Suits) e
  `<MEDIA_ROOT>/series` (séries novas adicionadas pelo Sonarr).
- Animes: `<MEDIA_ROOT>/animes`.
- Filmes: `<MEDIA_ROOT>/movies`.
- Docker/containerd: `<DOCKER_DATA_ROOT>` (o SSD; ver `RASPBERRY_PI.md`).
- qBittorrent: save path `/media/downloads` e temporários em
  `/media/downloads/incomplete` (mesmo disco). O temp antigo ficava em
  `/media/temp`, no disco de mídia.
- Fila do qBittorrent: 5 downloads ativos e 10 torrents ativos; torrents
  lentos (< 100 KiB/s) não contam no limite, para que um torrent morto não
  bloqueie os demais.
- Hardlinks: como downloads e biblioteca estão em filesystems diferentes, as
  importações do *arr são **cópias**, não hardlinks. Legendas também não são
  hardlinks.

## 3. Alinhamento Sonarr/Radarr/Bazarr/Jellyfin

O ponto que causou o problema inicial: o Bazarr gravava no folder de downloads
do Sonarr, mas o Jellyfin lia `/media/Suits`. Hoje:

- Sonarr: série Suits em `/media/Suits` (root `/media`); séries novas com root
  `/media/series`; animes com root `/media/animes`.
- Radarr: root `/media/movies`.
- Bazarr: lê/salva no mesmo caminho do Sonarr/Radarr; as legendas novas caem
  em `/media/Suits/Season 1`, `/media/series/...`, `/media/animes/...` e
  `/media/movies/...`.
- Jellyfin: bibliotecas
  - **Séries**: `/media/Suits` + `/media/series`
  - **Filmes**: `/media/movies`
  - **Animes**: `/media/animes`
- As bibliotecas Filmes/Animes/Séries estão com **monitoramento em tempo real**
  (`EnableRealtimeMonitor: true`). Até a migração de 2026-11-23 a biblioteca
  ficava em NTFS-3G (FUSE) e os eventos de criação/movimentação não chegavam ao
  Jellyfin; agora `<MEDIA_ROOT>` é ext4, então o realtime volta a ser viável. O
  scan agendado de **30 min** continua ativo como fallback.
- Se um filme/episódio recém-importado não aparecer, forçar o scan
  (Dashboard → Scheduled Tasks ou `POST /Library/Refresh`).
- Após baixar uma legenda nova o Jellyfin ainda pode precisar de um
  refresh/scan do item; o `-1s` do Suits é aplicado no arquivo pelo Bazarr, não
  no Jellyfin.

### 3.1 Correção da biblioteca do Jellyfin

- A biblioteca Séries apontava para `/media` (a raiz inteira), o que indexava
  `downloads`, `docker`, `filmes`, etc. e criava “séries” falsas.
- Foi corrigida para `/media/Suits` + `/media/series` via `options.xml` e
  `.mblink` (`Suits.mblink` e `series.mblink`), com backup em
  `<CONFIG_ROOT>/jellyfin/root/default/Séries/`.
- Uma biblioteca vazia `Séries2` criada durante a tentativa via API foi
  removida manualmente (backup em `/tmp/jf_series2_bak_*`).
- Há itens antigos órfãos de `/media/downloads` e `/media/docker` no banco do
  Jellyfin; eles não aparecem na árvore da biblioteca. Se voltarem a aparecer,
  rodar “Escanear todas as bibliotecas”/limpeza no Jellyfin.
- O histórico de reprodução dos episódios foi preservado pelo caminho
  `/media/Suits/Season 1/...`; o item de série pode ter sido recriado.

### 3.2 Hook de import do Radarr/Sonarr → Jellyfin

Como o realtime não funciona no FUSE, foi criado um hook para atualizar o
Jellyfin assim que o *arr importa/renomeia um arquivo:

- Conexão **Custom Script** chamada **Jellyfin Refresh** (id 1) no Radarr e no
  Sonarr, com **On Import**, **On Upgrade** e **On Rename**.
- Script: `/config/scripts/jellyfin-refresh.sh` dentro dos containers,
  gravado em `<CONFIG_ROOT>/{radarr,sonarr2}/scripts/`.
- A chave fica em `.jellyfin_key` no mesmo diretório (API key do Jellyfin
  `MediaImportHook`, criada em 2026-10-26; o valor não vai para os docs).
- O script chama `POST /Library/Media/Updated` com o caminho do arquivo; se
  falhar, chama `POST /Library/Refresh`.
- Teste do evento `Test`:
  `docker exec -e radarr_eventtype=Test media-radarr-1 /config/scripts/jellyfin-refresh.sh`
  (e o equivalente com `sonarr_eventtype=Test`).
- O scan de 30 min continua como fallback caso o hook não seja executado.

## 4. Prowlarr e indexadores

Prowlarr em `http://<LAN_IP>:9696`. App Profile **Standard** com
`minimumSeeders = 1`. Apps `Radarr` e `Sonarr` com `syncLevel: fullSync`.
O Prowlarr conversa com o `torrent-indexer` em `http://torrent-indexer:7006`.

| Indexador | URL/Prowlarr | Status em 2026-11-24 |
|---|---|---|
| Rede Torrent | `Torznab` `http://torrent-indexer:7006`, `apiPath=/api` | Funciona; no Radarr e Sonarr |
| Torrent dos Filmes | `apiPath=/api/torrent-dos-filmes` | Funciona; no Radarr e Sonarr |
| Starck Filmes | `apiPath=/api/starck-filmes` | Funciona; no Radarr e Sonarr (só filmes) |
| Baixarapido | `apiPath=/api/baixarapido` | Funciona; no Radarr e Sonarr |
| The Pirate Bay | nativo | Funciona; Radarr e Sonarr |
| Torrentio | nativo | Funciona; Radarr e Sonarr |
| 1337x | nativo | Funciona com o proxy FlareSolverr (`solvearr`); no Radarr e Sonarr |
| UIndex | nativo | Funciona via proxy FlareSolverr; no Radarr e Sonarr |
| YTS | nativo | Funciona; no Radarr (filmes) |
| BluDV | não adicionado | Cloudflare resolvido, mas o download usa gate `gate/go` → `promobr.online`/`x.gd`; retorna 0 |
| Comando Torrents | `apiPath=/api/comando_torrents` | Funciona com FlareSolverr oficial; no Radarr e Sonarr |
| Vaca Torrent | — | Descontinuado: `vaqueirofilmes.com` virou streaming e não expõe magnets |
| Filme Torrent | — | Só nome em `IndexerNames`; sem handler |
| Dodo Filmes | — | Não existe no código atual |

Resumo atual: **Radarr tem 11 indexadores** (1337x, Baixarapido, Comando,
Rede, Torrent dos Filmes, Starck, TPB, Torrentio, UIndex, YTS e o proxy
**PT-BR Alternate Titles**) e **Sonarr tem 9** (1337x, Baixarapido, Comando,
Rede, Torrent dos Filmes, Starck, TPB, Torrentio e UIndex), todos com
`minimumSeeders = 1`, exceto o proxy (0).

### 4.1 Torznab customizado no Prowlarr

Os indexadores brasileiros do `torrent-indexer` são adicionados como
**Generic Torznab** no Prowlarr:

- `baseUrl`: `http://torrent-indexer:7006`
- `apiKey`: vazio
- `appProfileId`: 1 (Standard)
- `apiPath`: `/api/<indexer>`
  - Rede Torrent: `/api` (o torrent-indexer usa `rede_torrent` como default)
  - Torrent dos Filmes: `/api/torrent-dos-filmes`
  - Starck Filmes: `/api/starck-filmes`
  - Comando Torrents: `/api/comando_torrents`
  - Baixarapido: `/api/baixarapido`

Após adicionar, rodar no Prowlarr o comando **ApplicationIndexerSync** e
conferir em Radarr/Sonarr → Settings → Indexers. O Prowlarr testa cada
indexador com uma busca e **recusa sincronizar** se o teste não retornar
resultado nas categorias configuradas.

O Sonarr perdeu Rede/1337x em uma sincronização porque o teste vazio usava o
fallback `q=2024`; o fallback do Torznab foi alterado para `q=a`, e o Rede
voltou. Em 2026-11-24 os dois apps estão com todos os indexadores esperados:
Radarr 11 e Sonarr 9. O 1337x foi recuperado depois de corrigir os proxies do
Prowlarr para `http://solvearr:8191/`; ele usa o proxy e pode levar ~110s na
primeira busca.

### 4.2 FlareSolverr oficial e Comando

- O serviço `solvearr` agora usa a imagem oficial
  `ghcr.io/flaresolverr/flaresolverr:latest` (3.5.0), com `mem_limit: 1024m` e
  `shm_size: 1gb`.
- `FLARESOLVERR_TIMEOUT_SECONDS=180`, `FLARESOLVERR_USE_SESSIONS=true` e
  `FLARESOLVERR_POOL_SIZE=2`. A primeira busca em um domínio novo pode levar
  ~80-120s para resolver o Cloudflare; as seguintes reaproveitam a sessão e o
  cache curto (30 min) e ficam rápidas.
- `Comando Torrents` passou a funcionar e foi adicionado ao Prowlarr e aos
  apps (id 6 no Radarr/Sonarr). A página “listão” (centenas de magnets) é
  ignorada para não travar a resposta.
- `BluDV`: o Cloudflare é resolvido, mas o link “Magnet-Link” vai para
  `gate/go` → `promobr.online` → `x.gd` e não expõe o magnet de forma
  automatizável; continua fora do Prowlarr.
- Os proxies do Prowlarr (`FlareSolverr` e `Solverr`) apontavam para
  `http://<LAN_IP>:8191/`; foram corrigidos para `http://solvearr:8191/`
  com timeout de 180s. Isso recuperou o 1337x e permitiu adicionar o UIndex.

## 5. Torrent-indexer: mudanças no Torznab

Arquivo alterado: `api/torznab.go`.

- Cada `<item>` agora tem `<category>` e o atributo `category`:
  - `2000` = Movies
  - `5000` = TV
  - A categoria é derivada de `Season`, `Episode` e `ReleaseType`; sem esses
    campos, considera filme.
- Mantém `seeders`, `peers`, `size`, `imdb`, `year` como atributos.
- O fallback quando `q` está vazio (usado pelo teste de sync do Prowlarr) passou
  de `2024` para `a`, para retornar TV e filmes.
- O `/api` continua aceitando `?indexer=<nome>` e `/api/<nome>`; o `min_seeds`
  da busca é respeitado pelo indexer.

Build/deploy (fora do Pi, sem compilar no Pi):

```bash
GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -trimpath \
  -ldflags "-s -w" -o torrent-indexer-linux-arm64 .
scp torrent-indexer-linux-arm64 \
  <user>@<LAN_IP>:<STACK_ROOT>/torrent-indexer/
```

No Pi:

```bash
cd <STACK_ROOT>
docker compose build torrent-indexer
docker compose up -d torrent-indexer
```

O binário antigo foi salvo em
`<STACK_ROOT>/torrent-indexer/torrent-indexer-linux-arm64.bak.*`.
O binário local de trabalho gerado nesta etapa é
`torrent-indexer-linux-arm64-new` (não versionado).

Teste de categorias:

```bash
curl -s 'http://<LAN_IP>:8080/indexers/bludv?q=minions'
curl -s 'http://<LAN_IP>:8080/indexers/baixarapido?q=matrix'
curl -s 'http://<LAN_IP>:8080/api/baixarapido?t=search&q=matrix' | grep category
curl -s 'http://<LAN_IP>:8080/api/rede_torrent?t=search&q=minions' | grep category
```

### 5.1 Coleta de domínios para novos indexadores

`CleanupTitleWebsites` registra domínios vistos no título original dos releases
em Redis, sem alterar a lista de indexadores automaticamente. Serve para
descobrir sites candidatos e revisar depois.

- Chave Redis: `torrent-indexer:domains` (hash; persiste no volume
  `redis-data`).
- Endpoint: `GET /domains?unknown=1&limit=100` (por padrão só desconhecidos;
  use `unknown=0` para ver todos).
- Cada item traz `domain`, `count`, `first_seen`, `last_seen`, `known`,
  `samples` (até 5 títulos) e `sources` (indexer de origem).
- `known=true` vem de `utils/commonWebsiteSLDs` (ex.: `vamostorrent.com`,
  `baixarapido.com`, `yts.mx`, `hidratorrents.org`). Os demais são candidatos.
- O título é apenas uma pista: pode ser release group, site de origem ou ruído.
  Só adicione um indexer depois de confirmar que o site tem busca/RSS e é
  automatizável.
- Opcional: defina `DOMAINS_REPORT_TOKEN` no container para exigir
  `X-Domains-Token` ou `?token=`.
- Exemplo:

```bash
curl -s 'http://<LAN_IP>:8080/domains?unknown=1&limit=100'
```

Também é possível consultar direto no Redis:

```bash
docker exec media-redis-1 redis-cli HGETALL torrent-indexer:domains
```

### 5.2 Como pedir a análise

Frase de atalho: **“analise os possíveis indexadores novos”**.

A fonte é `GET /domains?unknown=1&limit=500` (use `unknown=0` para incluir os
já conhecidos). Para cada domínio, verificar:

- se é site/tracker/indexer de verdade ou apenas release group, adware ou ruído
  do título;
- se tem busca/RSS/Torznab, login, Cloudflare ou magnet direto;
- se os `samples`/`sources` fazem sentido e se há seeders/qualidade;
- se vale criar um adapter em `api/<site>.go`, com URL de busca, paginação,
  seletores, categorias e testes.

Nada é adicionado automaticamente; a lista é só para triagem manual.

## 6. Perfis de qualidade, custom formats e Seerr

Custom formats (Radarr e Sonarr):

| ID | Nome | Regex | Uso |
|---|---|---|---|
| 1 | `PT-BR Dublado` | `(?i)\b(dublado|dublagem|nacional|pt[- ]?br|ptbr|portugu[eê]s|portugues|brazilian)\b` | +100 em `Dublado`/`Anime-Dublado`; -100 nos legendados |
| 2 | `English Dub` | `(?i)(english[ .-]?dub|dubbed|\bdub\b)` | -100 nos legendados; 0 nos dublados |
| 3 | `Dual Audio` | `(?i)\bdual\b` | +50 nos dublados; 0 em `Anime-Legendado`; -100 em `Legendado` |
| 4 | `Latino/Espanhol` | `(?i)\b(lat|latam|latino|latinoamericano|castellano|espanhol|español|spanish)\b` | -100 nos quatro perfis |

Perfis (4 por app, aplicado em 2026-11-02):

- **Radarr**
  - `Legendado` (id 7): PT-BR -100, English Dub -100, Dual -100,
    Latino -100; mínimo 0; cutoff 0.
  - `Dublado` (id 8): PT-BR +100, English Dub 0, Dual +50, Latino -100;
    mínimo 100; cutoff 100.
  - `Anime-Legendado` (id 9): PT-BR -100, English Dub -100, Dual 0,
    Latino -100; mínimo 0; cutoff 0.
  - `Anime-Dublado` (id 10): PT-BR +100, English Dub 0, Dual +50,
    Latino -100; mínimo 100; cutoff 100.
- **Sonarr**
  - `Legendado` (id 7): PT-BR -100, English Dub -100, Dual -100,
    Latino -100; mínimo 0; cutoff 0.
  - `Anime-Legendado` (id 8): PT-BR -100, English Dub -100, Dual 0,
    Latino -100; mínimo 0; cutoff 0.
  - `Dublado` (id 9): PT-BR +100, English Dub 0, Dual +50, Latino -100;
    mínimo 100; cutoff 100.
  - `Anime-Dublado` (id 10): PT-BR +100, English Dub 0, Dual +50,
    Latino -100; mínimo 100; cutoff 100.

Qualidade dos 4 perfis: 1080p (HDTV/WEB/BluRay) com fallback 720p
(HDTV/WEB/BluRay); sem Remux e sem 4K; `upgradeAllowed=true`, cutoff
`Bluray-1080p` (7).

No **Seerr**, os defaults continuam: Radarr `Legendado` (7), Sonarr
`Legendado` (7), anime `Anime-Legendado` (8). Para dublado, escolher
`Dublado` ou `Anime-Dublado` no pedido. Os perfis antigos `1-6` foram
excluídos após migrar os itens.

Se o dropdown do Seerr ainda mostrar os nomes antigos, abrir Settings →
Services → Radarr/Sonarr e clicar **Test/Save** uma vez.

> Histórico: o teste do Minions e o caso do Jack abaixo se referem aos perfis
> antigos (`Animação - Dublado` / `Séries - Dublado`), mantidos como registro.

Teste real (Minions 2015, perfil 8): 162 releases, 6 aceitos. Exemplos:

- `Minions 2015 1080p BluRay DUAL [Dublado] LAPUMiA` — TPB, 1 seed, CF 150.
- `Minions.2015.1080P-Dual-Lat` — Torrentio, 18 seeds, CF 50 (espanhol+inglês,
  **não** PT-BR).
- `Minions.2015.1080p.BluRay.Dual` — Torrentio, 6 seeds, CF 50.
- Três do Torrent dos Filmes (Dual), com `seeders` vazio no Radarr.

Os 156 rejeitados eram inglês-only, 4K/remux fora do perfil ou sem o score
mínimo. O `minSeeds = 1` filtra os de 0 seed; quando o indexador não informa
seeders (Torrent dos Filmes), o Radarr mostra vazio e aceita — para isso,
preferir Torrentio/TPB com seeders explícitos.

> Depois do ajuste de 2026-10-26 (mínimo 100 + Latino −100), os exemplos
> `Dual-Lat` e `Dual` puro (CF 50) seriam rejeitados; só releases com PT-BR
> explícito passariam. O CF `PT-BR Dublado` foi ampliado para reconhecer
> `brazilian`/`ptbr`, então os releases do torrent-indexer com
> `(brazilian, eng)` passam a pontuar 150 (PT-BR 100 + Dual 50). O Radarr
> confirmou isso nos resultados do Torrent dos Filmes para Minions.

### 6.1 Comportamento do “Dual Audio” (importante)

O CF `Dual Audio` é só `(?i)\bdual\b` e vale **+50** nos perfis dublados. Antes
do ajuste de 2026-10-26, o mínimo desses perfis era **50**: **qualquer** release
com “Dual” no nome passava, mesmo que o segundo áudio fosse espanhol. O CF
`PT-BR Dublado` (+100) só entra se o título tiver `dublado`, `pt-br`,
`português` etc.; ele não era obrigatório.

Caso The Nightmare Before Christmas (Jack): o arquivo
`El.extrano.mundo.de.Jack.1993.WEB-DL.1080p-Dual-Lat.mkv` tem faixas **spa**
(espanhol latino) e **eng**, nenhuma **por**. Como o nome tem `Dual`, ele
pontuou 50 e passou no antigo mínimo 50 do perfil `Animação - Dublado`.

Ajuste aplicado em 2026-10-26:
- mínimo dos perfis dublados subiu de 50 para **100**;
- CF negativo `Latino/Espanhol` (id 4) com **−100** nos perfis dublados.

Com mínimo 100: PT-BR puro = 100 (passa), PT-BR + Dual = 150 (passa),
Dual puro = 50 (falha), Dual-Lat = 50 − 100 = −50 (falha).

Busca feita logo depois do ajuste no Radarr: **154 releases, 0 aceitos**. O
release espanhol atual foi rejeitado (−50) e não havia release PT-BR nos
resultados da busca por título em inglês. No indexador direto (Rede Torrent)
existe `O Estranho Mundo de Jack (1993) BDrip 1080p Dublado dat2014`; numa
verificação posterior ele apareceu com **11 seeders**, mas o Radarr não o casa
na busca por título em inglês. O arquivo espanhol permanece até uma importação
manual ou uma busca por título alternativo.

O Radarr guarda os `alternateTitles` do TMDB, mas **não os usa na busca**:
o Prowlarr registra apenas `Nightmare Before Christmas 1993`. Buscar no Prowlarr
por `O Estranho Mundo de Jack` encontra o release PT-BR. Alterar `title` ou
`originalTitle` via API não funciona: o Radarr mantém o título do TMDB.

Proxy implementado em 2026-10-26 no container **`media-gateway`**: o indexer
**PT-BR Alternate Titles** no Radarr lê as traduções pt-BR do banco
(`MovieTranslations`, idiomas 18/30), busca os títulos alternativos no Prowlarr
e injeta o IMDb nos resultados. A busca do Jack retornou o release do Rede
Torrent com **score 100** e `accepted: true` no Radarr; a verificação
`/arr/check` retornou **1 aceito de 160**, mas ainda não foi baixado.

## 7. Seerr (sucessor do Jellyseerr)

- URL: `http://<LAN_IP>:5055`.
- Imagem: `seerr/seerr` (o Jellyseerr foi descontinuado em 2026-02-14 e o login
  Jellyfin antigo falha; o Seerr é o sucessor oficial).
- Config: `<CONFIG_ROOT>/seerr/settings.json` e `db/`.
- Servidores: Jellyfin `http://jellyfin:8096`; Sonarr `http://sonarr:8989`
  (root normal `/media/series`, anime `/media/animes`); Radarr
  `http://radarr:7878` (root `/media/movies`).
- Perfis ativos/defaults descritos na seção 6.
- O Seerr importa as bibliotecas do Jellyfin. A biblioteca **Animes** foi
  criada depois do setup; se ela não aparecer, usar
  **Settings → Jellyfin → Sync Libraries** e habilitar Animes.
- A barra de busca do Homepage aponta para
  `http://<LAN_IP>:5055/search?query=` (provider `custom`). O fluxo é:
  request no Seerr → Radarr/Sonarr → Prowlarr/qBittorrent → import →
  Jellyfin scan → Bazarr busca legenda.
- Requests do admin são auto-aprovados por padrão; se ficarem em *Pending*,
  aprovar em Requests ou ativar Auto-Approve no usuário.

## 8. Legendas (Bazarr) e o ajuste de -1s

Bazarr em `http://<LAN_IP>:6767`, config
`<CONFIG_ROOT>/bazarr/config/config.yaml`.

- Perfis: **PTBR** (`pb`, default para séries e filmes) e EN.
- Provedores habilitados: `opensubtitlescom` e `subf2m`.
  - OpenSubtitles.com usa a conta do usuário (username/senha no config; a API
    key do app é embutida no Bazarr). Conta gratuita: **20 downloads/dia**;
    sem conta: 5/dia; VIP: 1000/dia. O reset é 00:00 UTC.
  - Subf2m precisa de `user_agent`.
- `minimum_score` de séries: 70 (filmes: 70). O Bazarr escolhe a legenda de
  **maior score** (não a primeira) e pode fazer upgrade em até 7 dias.
- `use_subsync: true`: o ffsubsync sincroniza automaticamente depois do
  download. Offsets grandes (3–6s) são corrigidos; o resíduo de 1s não é
  detectado.
- CORS habilitado (`cors.enabled: true`) para o dashboard poder chamar a API.
- **Ajuste fino -1s (somente Suits/PT-BR):**
  - Script: `<CONFIG_ROOT>/bazarr/scripts/shift_subs.py`.
  - Pós-processamento no Bazarr:
    ```
    use_postprocessing: true
    postprocessing_cmd: '/lsiopy/bin/python3 /config/scripts/shift_subs.py {{subtitles}} -1000 /suits/ {{subtitles_language_code2}}'
    ```
  - O Bazarr roda o pós-processamento **depois** do sync; o script adianta
    1000 ms e só atua em caminho `/suits/` e idioma `pb`.
  - As legendas `.pt-BR` existentes de Suits foram deslocadas com backup
    `.bak.shift.*`.
  - **Não usar “Sincronizar existentes” no Suits** depois disso: ele pode
    re-sincronizar e desfazer o -1s. Baixar episódio novo continua normal
    (download → sync → pós-processamento).
  - O ajuste é exclusivo de Suits; filmes/animes não recebem o -1s.

### 8.1 Quota e fila no dashboard

- O `media-agent` expõe `GET /subs/quota`, que faz login na OpenSubtitles com
  as credenciais do Bazarr e retorna:
  `allowed_downloads`, `remaining_downloads`, `downloads_count`,
  `reset_time_utc`, `reset_time`, `level`, `vip`.
- A aba **Legendas** do Homepage mostra a quota, busca/filtro por episódio,
  série ou idioma, “Buscar pendentes” e “Sincronizar existentes”. Ele chama o
  proxy `/bazarr` do media-agent; a API key do Bazarr fica em `.bazarr_key` no
  servidor, não no `custom.js`.
- A fila é salva no `localStorage` do navegador (`subs_queue_v1`); o botão
  “Executar fila agora” aparece quando o reset chega. Ela também tenta rodar
  automaticamente quando o reset chega, com a aba aberta e visível; não roda em
  background com o navegador fechado.
- O painel usa o job real do Bazarr para dar feedback (“Legenda baixada” ou
  “Nao encontrada” + detalhe do provedor).
- Limite de segurança: se a quota não puder ser consultada, o painel usa
  trava de 5/dia.

## 9. Homepage (dashboard)

- URL LAN: `http://<LAN_IP>:3000`.
- URL Tailscale: `http://<TAILSCALE_IP>:3000`.
- Config viva: `<CONFIG_ROOT>/homepage/{settings,services,widgets,bookmarks}.yaml`,
  `custom.js` e `custom.css`.
- **Fonte do painel:** `deploy/homepage/src` (módulos ES) e
  `deploy/homepage/custom.css` (tema global). O `custom.js` do Pi é artefato de
  build; não edite o arquivo no servidor. Build:
  `cd deploy/homepage && npm install && npm run build`; o resultado é
  `dist/custom.js`. Detalhes em
  [deploy/homepage/README.md](deploy/homepage/README.md).
- Grupos: Filmes e Séries (Jellyfin, Stremio, Seerr), Media Services Status
  (Radarr, Sonarr, Prowlarr, Bazarr, qBittorrent), Gaming (PC Casa). O card do
  torrent-indexer foi removido do dashboard; o serviço continua rodando e
  exposto em `:8080`. O estilo e as colunas de cada grupo ficam em
  `settings.yaml` (`layout`), que também define a ordem dos grupos.
- `custom.js` adiciona:
  - barra de abas fixa no topo: **Início**, **Pedidos** e **Legendas**. A barra
    acompanha a largura do conteúdo e fica no topo também no celular;
  - **Início** mantém os cards, widgets e busca exatamente como estão;
  - **Pedidos** e **Legendas** mantêm o cabeçalho/widgets/busca no topo e
    escondem cards, bookmarks e rodapé para usar a área principal da página;
  - URLs por query string: `/?tab=pedidos` e `/?tab=legendas` (Início é `/`).
    Funcionam ao recarregar, compartilhar e no botão voltar. O Homepage não
    tem rotas `/pedidos` e `/legendas` — elas retornam 404 —, por isso não são
    usados caminhos reais sem um proxy na frente;
  - bloco recolhível **Como funciona** em Pedidos e Legendas;
  - aba **Pedidos** (todos os perfis do Radarr/Sonarr + Seerr): contadores por
    status, filtros contextuais (o select muda entre Ativos e Histórico), busca
    por título, botão **Filtros (N)** com modal central para tipo
    (Filme/Série/Anime), perfil e status, disponível em **Ativos e Histórico**
    (no Histórico vale para os registros já carregados), e **Abrir Seerr**. A
    lista de Ativos mostra 10 itens por página, do mais recente ao mais antigo,
    com navegação por páginas. Cada filme/série mostra status, perfil,
    progresso, tempo restante e último evento. Pedidos do Seerr que ainda não
    chegaram ao Radarr/Sonarr aparecem com o status/perfil do Seerr;
    recusados/falhos mostram o erro.
    O botão **Adicionar série/anime** busca no Sonarr/TVDB, mostra se a série
    já existe e permite escolher **Perfil**, **Pasta raiz** e **Tipo**: ao
    adicionar, nada é monitorado, e o modal de episódios permite escolher o que
    monitorar/buscar;
  - **Histórico**: layout compacto com data, título, tipo, origem, status,
    conclusão e ações; badges **Ativo/Arquivado**; filtro por origem
    (Seerr/Manual/Importado do Sonarr/Radarr-Sonarr); datas de pedidos
    Seerr-only marcadas como **(aprox.)** quando há `updatedAt` e
    **“concluído sem data”** quando não há; “Apagar arquivados carregados”
    mantém o escopo explícito; auto-refresh pausado para não perder
    paginação/scroll;
  - **Modal de episódios**: temporadas recolhíveis, seletor **Ir para
    temporada**, busca por número/título, filtro **Somente monitorados** /
    **Somente sem arquivo**, escopo de **Marcar não baixados**, confirmação
    com contagem e badge **Pedido** nos episódios já rastreados; acima de 20
    episódios o **Aplicar** também pede confirmação;
  - **Buscar original** pede confirmação explícita (muda para `Legendado` ou,
    em anime, `Anime-Legendado`, e o item sai dos perfis dublados);
  - aba **Legendas**: quota da OpenSubtitles, busca por série ou episódio,
    agrupamento por série, pendências, fila local (`localStorage`), feedback
    do Bazarr e sincronização de legendas existentes;
  - verificação de releases PT-BR no Radarr/Sonarr;
  - botão **Ligar PC** dentro do card **PC Casa** (status/WOL).
- `custom.js` detecta o host:
  - acessado por `<LAN_IP>`, `localhost` ou `127.0.0.1` = **modo local**:
    todos os cards, as abas Início/Pedidos/Legendas e o Gaming; o WOL usa o 8100
    privado, sem senha.
  - acessado por `<TAILSCALE_IP>` (ou outro host) = **modo remoto**: esconde os
    cards de gestão (Radarr, Sonarr, Bazarr, Prowlarr, qBittorrent), o grupo
    Atalhos e o grupo Media Services Status; mantém Jellyfin, Seerr, Stremio,
    **PC Casa/Gaming** e as abas **Pedidos** e **Legendas**. Essas abas usam o
    `media-agent` em `http://<host-atual>:8097`.
    O botão **Ligar PC** usa o endpoint público `:8098/gaming/wake` e pede a
    senha definida em `GAMING_PASSWORD` no `.env`; o status vem de
    `:8098/gaming/status` sem IP/MAC.
- Links: os serviços de gestão usam `http://<LAN_IP>:<porta>`; os remotos
  (Jellyfin/Seerr/Stremio) são reescritos pelo `custom.js` para o host
  atual. `siteMonitor` e widgets internos continuam usando nomes de container
  (`jellyfin:8096`, `sonarr:8989`, etc.).
- A barra de busca do topo é `provider: custom` apontando para a busca do
  Seerr; não é uma busca web genérica. O placeholder é ajustado para
  **“Buscar no Seerr...”** pelo `custom.js`.
- A chave do Bazarr saiu do `custom.js`: o painel Legendas usa o proxy
  `/bazarr` do media-agent, que guarda a chave em `.bazarr_key` no servidor.
  As chaves restantes ficam no `services.yaml` e são usadas pelo servidor do
  Homepage, não pelo navegador.
- `HOMEPAGE_ALLOWED_HOSTS: "*"`. O Homepage e o media-agent (`8097`) são
  expostos na LAN e no Tailscale; os demais serviços de gestão continuam
  presos ao IP da LAN.

### 9.1 Admin agent (containers, 2026-11-26)

- `admin-agent` em `<LAN_IP>:8093` (LAN only) e `docker-socket-proxy` na rede
  interna `admin-internal`, sem porta publicada.
- Aba **Admin** no Homepage (some no modo remoto/Tailscale), com login
  dedicado em `<HOME>/.config/admin-agent/password` (600) e CORS
  restrito às origens da LAN.
- Lista os containers do projeto `media` com estado, health, uptime, imagem e
  portas; ações `start`, `stop` e `restart` com confirmação. Serviços críticos
  exigem digitar o nome.
- Protegidos: `admin-agent`, `docker-socket-proxy` e `autoheal`.
- Não lê `docker-compose.yml`, `.env` nem arquivos de configuração; o socket
  do Docker fica somente no proxy.
- Auditoria em `<CONFIG_ROOT>/admin-agent/state/admin-audit.jsonl`; 5 falhas
  de senha por minuto bloqueiam o IP por 1 minuto.
- Código e instruções: `deploy/raspberry/admin-agent/`.

## 10. Gaming agent (PC da casa)

- Container `gaming-agent` (host network), só WOL/status: `8100` privado
  (**LAN only**, `LISTEN_HOST=<LAN_IP>`) e `8098` público (LAN + Tailscale).
- Script: `<CONFIG_ROOT>/gaming-agent/agent.py` (fora do Git); monta
  apenas o diretório `/app`. Não acessa Bazarr, Radarr, Sonarr ou Seerr.
- Endpoints:
  - `GET /status`: ping em `PC_IP` (Tailscale `<PC_TAILSCALE_IP>` e LAN
    `<PC_LAN_IP>`) e retorna `online`, `status`, `ips`, `mac`, `checked_at`.
  - `POST /wake` (e `GET /wake`): envia magic packet para
    `<MAC>`, portas 9/7, broadcast `<PC_LAN_IP>55` e
    `<PUBLIC_IP>`.
- O 8098 é público (LAN + Tailscale) e só aceita:
  - `GET /gaming/status`: `online`, `status`, `checked_at` (sem IP/MAC);
  - `POST /gaming/wake`: exige `X-Gaming-Password`; a senha vem de
    `GAMING_PASSWORD` no `.env`, com limite de 5 falhas/min.
- Para trocar a senha, edite `GAMING_PASSWORD` no `.env` e recrie/restart o
  container do `gaming-agent`. O navegador guarda a senha em `sessionStorage`
  depois do primeiro WOL bem-sucedido. `.gaming_password` é apenas fallback
  legado (`GAMING_PASSWORD_FILE`).
- O PC precisa de Wake-on-LAN habilitado na BIOS/placa e, de preferência, cabo
  Ethernet.
- `network_mode: host` + `cap_add: NET_RAW` no compose.
- O ping na LAN pode falhar se o firewall do Windows bloquear ICMP; nesse
  caso o status continua funcionando pelo IP Tailscale.

## 10.1 Media agent (Pedidos + Legendas)

- Container `media-agent` (host network) em `http://<host>:8097`
  (`LISTEN_HOST=0.0.0.0`). O `ALLOWED_NETWORKS` aceita LAN
  (`<LAN_SUBNET>`), Tailscale (`<TAILSCALE_RANGE>` e `<TAILSCALE_IPV6_RANGE>`) e
  loopback; fora disso retorna 403.
- Script: `<CONFIG_ROOT>/media-agent/media_agent.py`; a cópia versionada
  fica em `deploy/raspberry/media-agent/media_agent.py` e é copiada para
  `${CONFIG_ROOT}/media-agent` no deploy. Ele monta o
  `config.yaml` do Bazarr, os `config.xml` de Radarr/Sonarr, o config do Seerr
  (`/seerr/settings.json`) e a chave `<CONFIG_ROOT>/media-agent/.bazarr_key`
  (`BAZARR_KEY_FILE`). A `OS_API_KEY` (OpenSubtitles) vem do `.env`
  (`OS_API_KEY`) e não fica no `media_agent.py`. As API keys nunca vão para o
  navegador.
- Endpoints:
  - `GET /subs/quota`: quota real da OpenSubtitles (seção 8.1).
  - `GET /arr/pending`: todos os filmes e séries do Radarr/Sonarr (qualquer
    perfil), com `hasFile`, `profileId`, `profileName`, `seriesType` e
    `addedAt`. O frontend filtra por tipo/perfil/status e pagina de 10 em 10.
  - `GET /arr/pending?status=1`: mesma lista enriquecida com `status`
    (`downloaded`, `partial`, `downloading`, `queued`, `searching`, `error`,
    `missing`, `request_pending`, `request_approved`, `request_declined`,
    `request_failed`), fila do *arr (progresso/tempo restante/erro), último
    evento do histórico e comando de busca ativo. Consulta `/api/v3/queue`,
    `/api/v3/history` e `/api/v3/command` em paralelo e cruza com
    `/api/v1/request` do Seerr por TMDB (filmes) ou TVDB (séries). Pedidos do
    Seerr sem item correspondente no Radarr/Sonarr entram como itens
    somente-Seerr; `seerrError` é preenchido se o Seerr estiver indisponível,
    sem derrubar a lista do *arr.
  - `POST /arr/check` `{"kind":"movie|series","id":N}`: consulta
    `/api/v3/release` no *arr e retorna quantos releases foram aceitos.
  - `POST /arr/search` `{"kind","id"}`: dispara a busca no perfil atual.
  - `POST /arr/switch` `{"kind","id"}`: troca para `Legendado` (Radarr 7 /
    Sonarr 7) ou, se for anime (`seriesType`, pasta `/media/animes` ou perfil
    Anime-*), para `Anime-Legendado` (Radarr 9 / Sonarr 8); dispara a busca.
  - `GET /sonarr/options`: perfis de qualidade e pastas raiz do Sonarr.
  - `GET /sonarr/lookup?term=...`: busca séries no Sonarr/TVDB, marcando as que
    já existem e o perfil atual.
  - `POST /sonarr/add` `{"tvdbId","profileId","rootFolderPath","seriesType"}`:
    adiciona a série com `monitor: none` e dispara `RefreshSeries`; séries já
    existentes não têm o perfil alterado.
  - `GET /sonarr/episodes?seriesId=N`: temporadas/episódios com `monitored`,
    `hasFile` e `refreshing` (reconsulta enquanto o Sonarr importa os dados).
  - `POST /sonarr/episodes/monitor`
    `{"seriesId","episodeIds","monitored","unmonitorOthers","search"}`: marca
    os episódios escolhidos (e opcionalmente desmarca os demais) e dispara
    `EpisodeSearch` só neles.
  - `GET/PATCH /bazarr?path=/api/...`: proxy para a API do Bazarr; a
    `X-API-KEY` é adicionada no servidor a partir de `.bazarr_key`.

  - O proxy `/bazarr` aceita apenas `/api/episodes`, `/api/movies`,
    `/api/series`, `/api/subtitles`, `/api/system/jobs` e `/api/system/logs`;
    `/api/system/settings` e demais rotas sao bloqueadas (403).
    Aplicado no Pi em 2026-11-02.

  - `GET /arr/audio-check?kind=movie|series&id=N` e `?all=1`: valida o
    idioma do audio contra o perfil (`Legendado`=en, `Dublado`=pt,
    `Anime-Legendado`=ja). Usa ffprobe (idioma, titulo da faixa e faixa
    default) com fallback para `mediaInfo.audioLanguages`. Vereditos:
    `ok`, `ok-multi`, `unknown`, `wrong-default`, `mismatch`, `no-audio`,
    `no-file`. Arquivos sem tag (`und`) saem como `unknown` e precisam de
    conferencia manual. CLI: `python3 /app/media_agent.py --audio-check`.
    Aplicado no Pi em 2026-11-02 (ffprobe + volume `/media:ro`).

## 10.2 Media gateway (proxy de títulos alternativos)

- Container `media-gateway` separado, na rede `media`, **sem porta publicada**.
- `gateway.py` monta o banco do Radarr (`/radarr/radarr.db`) e o
  `config.xml` do Prowlarr, ambos somente leitura.
- Expõe `GET /torznab/api?t=...` em `http://media-gateway:8099`; o Radarr usa o
  indexer **PT-BR Alternate Titles** (`http://media-gateway:8099/torznab`,
  `apiPath=/api`, chave `alternate`, `minimumSeeders=0`).
- Lê `MovieTranslations` (idiomas 18/30 = pt-BR/Portugal), consulta os
  indexers brasileiros no Prowlarr e injeta o IMDb do filme nos resultados.
- Se não houver tradução/resultado, faz fallback com a query original no
  Prowlarr (necessário para o teste do Radarr); o Radarr deduplica.
- O XML devolve `downloadUrl` do Prowlarr com a API key; por isso o gateway
  fica interno (sem porta publicada). A única exposição é o Radarr/Prowlarr na
  rede Docker.

## 11. Jellyfin

- URL LAN: `http://<LAN_IP>:8096`; Tailscale:
  `http://<TAILSCALE_IP>:8096`.
- Bibliotecas: Séries (`/media/Suits`, `/media/series`), Filmes
  (`/media/movies`), Animes (`/media/animes`).
- Monitoramento em tempo real ligado nas três, mas **não efetivo** no mount
  FUSE/NTFS-3G; ver seção 3.
- Scan agendado a cada **30 min** desde 2026-10-26. O scan pode ser forçado em
  Dashboard → Scheduled Tasks → “Escanear a Biblioteca de Mídia” ou por
  `POST /Library/Refresh`.
- Import/upgrade/rename do Radarr e Sonarr chama o hook **Jellyfin Refresh**
  (`/config/scripts/jellyfin-refresh.sh`), que atualiza o item na hora via
  `/Library/Media/Updated`; ver seção 3.2.
- Caso Buddy (2026): o Radarr importou para
  `/media/movies/Buddy (2026)/...mkv`, mas o Jellyfin ficou com `MovieCount 0`
  até um refresh manual. O refresh importou Buddy e “O Estranho Mundo de Jack” e
  iniciou o watcher de `/media/movies`; antes ele só observava `/media/Suits`.
- O token de API usado nos scripts é lido da tabela `Devices` do banco do
  Jellyfin; não documentar o valor.
- Backups do `options.xml` da biblioteca em
  `root/default/Séries/options.xml.bak.*`.
- Atualizado para **12.4.0** em 2026-11-26 (imagem
  `jellyfin/jellyfin:12.4`). Backup completo em
  `<BACKUP_ROOT>/jellyfin-10.11.11-20261126-200235`; o plugin File
  Transformation foi removido antes da migração (não estava em uso) e o scan
  completo foi executado.
- No Jellyfin 12, `X-Emby-Token` é legado/desativado; usar
  `Authorization: MediaBrowser Token="..."`. O `media-bff` foi ajustado.

## 12. Fluxo de um pedido

1. Você pesquisa no Seerr e escolhe o perfil (`Legendado`, `Dublado`,
   `Anime-Legendado` ou `Anime-Dublado`).
2. O Seerr cria o request no Radarr/Sonarr.
3. O *arr adiciona o título, procura no Prowlarr e manda o release para o
   qBittorrent.
4. O qBittorrent baixa; o *arr importa para `/media/movies`, `/media/series`,
   `/media/animes` ou `/media/Suits`.
5. O Jellyfin detecta no próximo scan agendado (até 30 min, pois o realtime
   não funciona no FUSE) e o título aparece. Para aparecer na hora, forçar o
   scan.
6. O Bazarr sincroniza com o *arr, baixa a legenda PT-BR de maior score e
   aplica sync (e o -1s se for Suits).
7. No Seerr, o status vai para *Available*; no Jellyfin, o player mostra a
   faixa PT-BR.

## 13. Backups e rollback

- Compose: `<STACK_ROOT>/docker-compose.yml.bak.*`.
- Configs dos *arr/Bazarr/Jellyfin/Seerr/Homepage: arquivos `.bak.*` nos
  respectivos diretórios.
- Jellyfin `options.xml.bak.*`; `Séries2` e `media.mblink` antigos também
  foram guardados.
- Legendas de Suits: `*.pt-BR.srt.bak.shift.*`.
- Binário antigo do indexer:
  `<STACK_ROOT>/torrent-indexer/torrent-indexer-linux-arm64.bak.*`.
- Para reverter o indexer, copiar o `.bak` de volta e rodar
  `docker compose build torrent-indexer && docker compose up -d torrent-indexer`.
- Para reverter o Bazarr (inclusive pós-processamento), restaurar o
  `config.yaml.bak.*`, remover/renomear o `shift_subs.py` se necessário e
  reiniciar o container.
- As chaves/segredos não estão nos docs; se recriar um serviço, pegar as
  chaves nos arquivos de config ou recriar no Prowlarr/Seerr.

## 14. Segurança e rede

- Exposição pelo Tailscale: **Jellyfin 8096, Seerr 5055, torrent-indexer 8080,
  Homepage 3000, Stremio 11470/12470 e gaming 8098** (status/WOL com senha).
- LAN-only (bind em `<LAN_IP>`): Radarr 7878, Sonarr 8989, Prowlarr 9696,
  Bazarr 6767, qBittorrent WebUI 8082, métricas 8081, gaming-agent **8100
  privado**, `media-gateway` (este nem publica porta) e `admin-agent` **8093**.
  O peer do qBittorrent (6881) fica aberto para torrents.
- O `admin-agent` (8093) exige senha dedicada e allowlist da LAN; o
  `docker-socket-proxy` fica em rede interna, sem porta publicada. O agente
  não lê compose, `.env` nem configs, e a aba Admin some no modo remoto.
- O Homepage detecta o host: acesso por `<LAN_IP>` mostra tudo; acesso pelo
  IP do Tailscale esconde os cards de gestão, mas mantém Jellyfin, Seerr,
  Stremio, **PC Casa** (WOL com senha) e as abas **Pedidos/Legendas** via
  `media-agent:8097`.
- A chave do Bazarr saiu do `custom.js` e vive em `.bazarr_key` no servidor; as
  demais chaves ficam no `services.yaml` e são usadas pelo servidor do
  Homepage, não pelo navegador.
- O gaming-agent tem dois listeners, só de WOL/status: o 8100 privado (LAN,
  sem auth) e o 8098 público, que expõe `/gaming/status` (sem IP/MAC) e
  `/gaming/wake` (senha em `GAMING_PASSWORD` no `.env`, limite de 5 falhas/min).
- O media-agent (`8097`) aceita LAN e Tailscale via `ALLOWED_NETWORKS` e não
  tem autenticação: ele pode alterar perfis, adicionar séries, monitorar
  episódios e acessar o Bazarr. Trate o tailnet como confiável; para exposição
  pública use reverse proxy com HTTPS e auth.
- O `media-gateway` é interno; o XML devolve `downloadUrl` do Prowlarr com a
  API key, mas o container não tem porta publicada.
- Para exposição pública (fora do tailnet), usar reverse proxy com HTTPS e
  autenticação; o Homepage e o media-agent não têm auth (o gaming público usa
  senha só no WOL).
- Reservar IP fixo/DHCP para o Pi e manter o IP Tailscale `<TAILSCALE_IP>`
  estável; se ele mudar, atualizar `services.yaml`, `bookmarks.yaml`,
  `widgets.yaml` e `custom.js`.

## 15. Pendências e próximos passos

1. **Dashboard de filmes**: a seção “Filmes” no painel Legendas (Bazarr
   `/api/movies`, wanted, quota/fila) ainda não foi implementada; o usuário
   concordou em fazê-la.
2. **Seerr**: adicionar o widget do Seerr no Homepage com a API key; sincronizar
   a biblioteca **Animes** no Jellyfin pelo Seerr (Settings → Jellyfin →
   Sync Libraries).
3. **Sonarr**: já está com 9 indexadores (1337x, Baixarapido, Comando, Torrent
   dos Filmes, Starck, Rede, TPB, Torrentio e UIndex); validar se
   Comando/Torrent dos Filmes retornam TV dublada na prática. O Starck é só
   filmes.
4. **Indexadores**: Baixarapido implementado e adicionado ao Prowlarr/Radarr/
   Sonarr; Comando voltou (FlareSolverr oficial + sessão + timeout 180s).
   BluDV continua atrás do gate `promobr/x.gd`; Vaca Torrent foi descontinuado
   (`vaqueirofilmes.com`, sem magnets); XTerFilmes também usa gate de anúncio;
   Filme Torrent sem handler; Dodo não existe.
5. **Seeds**: o Torrent dos Filmes não informa seeders no Radarr (mostra
   vazio); preferir Torrentio/TPB quando for escolher manualmente. O
   `minSeeds=1` está no App Profile do Prowlarr e nos *arr.
6. **-1s**: válido só para Suits; não usar “Sincronizar existentes” no Suits
   para não desfazer. Para outro release/série, criar um pós-processamento
   próprio.
7. **Fila de legendas**: é do navegador; se quiser execução em background,
   criar um cron/serviço no agente.
8. **Docs**: atualizados em 2026-11-24 com o Baixarapido, o estado do Vaca
   Torrent (descontinuado), o XTerFilmes (gate de anúncio) e a recuperação do
   1337x/YTS/UIndex. Commit feito junto com o handler.
9. **Compose versionado**: o `deploy/raspberry/docker-compose.yml` foi
   atualizado em 2026-11-02 (media-agent com build, ffmpeg, `/media:ro` e
   128 MB); no Pi o build context é `<CONFIG_ROOT>/media-agent`.
10. **UI**: etapas 1, 0.5, 2, 3, 4, 5, 6 e 7 concluídas. O estado da
    sub-aba/filtros na URL e o tema claro seguem opcionais.
10. Itens órfãos de `/media/downloads` e `/media/docker` no banco do Jellyfin;
    limpar se aparecerem.
11. **Acesso externo**: Homepage e serviços já usam o IP Tailscale
    `<TAILSCALE_IP>`, e o WOL já está no card **PC Casa**. Se o IP Tailscale do Pi
    mudar, atualizar `services.yaml`, `bookmarks.yaml`, `widgets.yaml` e
    `custom.js`.
12. **Jellyfin/FUSE**: o realtime não recebe eventos no NTFS-3G; o scan de
    30 min cobre a importação e o hook **Jellyfin Refresh** atualiza na hora.
    Se o hook for desativado, o fallback é o scan de 30 min.
13. **Áudio PT-BR**: os perfis `Dublado`/`Anime-Dublado` exigem PT-BR
    (mínimo 100) e rejeitam `Latino/Espanhol`. O proxy **PT-BR Alternate
    Titles** no `media-gateway` segue disponível para achar releases
    brasileiros. O item do Jack está no perfil `Dublado` (8) com áudio PT;
    o painel **Pedidos** permite trocar para `Legendado` e buscar quando
    não houver PT-BR aceito.

14. **Decisão de idioma por IA (ideia futura)**: usar o **Motorola One
    Vision** sobrando como nó de identificação de idioma (LID), não como
    servidor Jellyfin. Motivo: o Pi 4 já fica em 90%+ no transcode de HEVC
    10-bit (Rare Exports) e não se quer adicionar carga. Setup: Termux +
    Python + ONNX Runtime com Silero LID/SpeechBrain VoxLingua107, ou
    whisper.cpp tiny; o `media-agent` extrai 60 s de áudio com ffmpeg e
    envia por Tailscale; o celular devolve o idioma provável. Resolve os
    `und` (Angel-A, Gran Turismo) sem ouvir manualmente. Limitações:
    acurácia probabilística, conteúdo sem fala (Flow), bateria/thermal,
    não serve para transcode; o celular já faz direct play HEVC 10-bit.
    Alternativa: LineageOS/e/OS + Termux/proot (postmarketOS não tem port
    para `kane`).

## 16. Comandos úteis

```bash
# Stack
cd <STACK_ROOT>
docker compose ps
docker compose up -d <serviço>
docker compose restart <serviço>
docker compose logs -f <serviço>

# Indexer (após copiar o binário ARM64)
docker compose build torrent-indexer
docker compose up -d torrent-indexer
curl -s http://<LAN_IP>:8080/

# Prowlarr: sincronizar apps depois de adicionar indexador
curl -s -X POST -H "X-Api-Key: <PROWLARR_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"name":"ApplicationIndexerSync"}' \
  http://<LAN_IP>:9696/api/v1/command

# Jellyfin 12+: forçar scan (token em <CONFIG_ROOT>/jellyfin/data/jellyfin.db)
curl -s -X POST -H 'Authorization: MediaBrowser Token="<JELLYFIN_TOKEN>"' \
  http://<LAN_IP>:8096/Library/Refresh

# Bazarr: status
curl -s -H "X-API-KEY: <BAZARR_API_KEY>" \
  http://<LAN_IP>:6767/api/system/status
```

### Redeploy do BFF (`media-bff`)

O diretório `<CONFIG_ROOT>/media-agent` é montado como `/app` (read-only) no container, e o compose real fica em `<STACK_ROOT>`. `<REPO_ROOT>` é o clone deste repositório no Pi. Dependendo do que mudou:

```bash
# 1) Só código (api_v1.py): restart reimporta o arquivo, sem recriar o container
cp <REPO_ROOT>/deploy/raspberry/media-agent/api_v1.py \
   <CONFIG_ROOT>/media-agent/api_v1.py
cd <STACK_ROOT>
docker compose restart media-bff
docker compose ps media-bff

# 2) Mudou o compose (env, portas, volumes): recria
cd <STACK_ROOT>
docker compose up -d media-bff
# se quiser forçar: docker compose up -d --force-recreate media-bff

# 3) Mudou a imagem (Dockerfile, media_agent.py, dependências): o media-bff
#    usa a mesma imagem `media-agent:local`
cd <STACK_ROOT>
docker compose build media-agent
docker compose up -d --force-recreate media-agent media-bff

# 4) Validar
curl -s http://<LAN_IP>:8091/api/v1/status
python3 <REPO_ROOT>/deploy/raspberry/media-agent/check_public.py http://<LAN_IP>:8091
docker logs --tail 30 media-media-bff-1
```

- O estado (chaves e sessões do Seerr) fica no volume `media-bff-state`: `restart` e `up -d` preservam. Só `docker compose down -v` apaga (todos precisariam vincular o Seerr de novo).
- `test_api_v1.py` roda no repo (`python3 -m unittest test_api_v1`), não no container.
- Rollback: `git show <commit>:deploy/raspberry/media-agent/api_v1.py > <CONFIG_ROOT>/media-agent/api_v1.py` e `docker compose restart media-bff`.

## 17. Histórico das implementações

### 2026-11-26

- Aba **Admin** LAN-only no Homepage com `admin-agent` e
  `docker-socket-proxy`; login dedicado, start/stop/restart e auditoria.
- Jellyfin atualizado de 10.11.11 para **12.4.0**; imagem fixada em
  `jellyfin/jellyfin:12.4`; backup completo e scan completo executados.
- Plugin File Transformation removido antes da migração (não estava em uso).
- `media-bff` ajustado para `Authorization: MediaBrowser Token="..."`;
  `test_api_v1.py` atualizado (67 testes).

### 2026-11-25

- BFF do app da família (`media-bff`): 38 testes, 3 listeners (8099 público preso a `127.0.0.1`, 8091 na LAN, 8092 admin), sessão do Seerr por pessoa com cookie cifrado no volume `media-bff-state`.
- `gaming-agent` passou de 8099 para 8100 (LAN); `8098` público inalterado.
- Jellyfin remoto via Tailscale Funnel; BFF público via Cloudflare Tunnel.

### 2026-11-02

- Perfis reduzidos a 4 por app: `Legendado`, `Dublado`, `Anime-Legendado` e
  `Anime-Dublado` (Radarr 7-10; Sonarr 7-10). Perfis `1-6` excluídos.
- Itens migrados: Buddy 4→7, Demon Slayer 7→9, Suits 6→7, Bleach 6→8;
  City of God, Minions e Nightmare mantidos em `Dublado` (8).
- Qualidade: 1080p (HDTV/WEB/BluRay) + fallback 720p; sem Remux/4K;
  `upgradeAllowed=true`, cutoff `Bluray-1080p` (7).
- `media-agent`: `/arr/audio-check` com ffprobe e volume `/media:ro`;
  proxy `/bazarr` com allowlist (`/api/system/settings` → 403);
  `arr_switch` distingue anime; tracking inclui `Anime-Dublado`; 128 MB.
- Homepage: `episodes.js` reconhece `Anime-Dublado` (10); bundle publicado
  em `/api/config/custom.js`.
- Seerr: nomes cacheados atualizados (`Legendado`/`Anime-Legendado`);
  IDs 7/7/8 mantidos.
- Redis: AOF corrompido corrigido com `redis-check-aof --fix`; backup em
  `/tmp/redis-backup/`.

### 2026-10-26


- Correção do Bazarr/OpenSubtitles (senha da conta, não API key), perfil PT-BR
  (`pb`, antes `pt`), `minimum_score` 70, CORS.
- Homepage (porta 3000) com cards, widgets e painel Legendas.
- Agente de mídia (hoje `media-agent`) + quota da OpenSubtitles
  (`/subs/quota`, 20/dia); o WOL ficou no `gaming-agent`.
- Alinhamento Sonarr/Bazarr/Jellyfin: Suits em `/media/Suits`, séries em
  `/media/series`, animes em `/media/animes`, filmes em `/media/movies`.
- Correção da biblioteca Jellyfin de `/media` para `/media/Suits` +
  `/media/series`; remoção da `Séries2`; realtime ligado (não efetivo no FUSE).
- Pós-processamento -1s para Suits/PT-BR (script + config do Bazarr; backups).
- Radarr + biblioteca Filmes no Jellyfin + Prowlarr/qBittorrent;
  Radarr 6 indexadores (Comando incluído; na época).
- Seerr (sucessor do Jellyseerr) na 5055, com Jellyfin/Sonarr/Radarr.
- 2026-11-24: **Baixarapido** implementado (`api/baixarapido.go`,
  `/api/baixarapido`) e adicionado ao Prowlarr/Radarr/Sonarr; proxies do
  Prowlarr corrigidos para `solvearr:8191`; **1337x**, **YTS** e **UIndex**
  associados; **Vaca Torrent** descontinuado (`vaqueirofilmes.com`, sem magnets);
  **XTerFilmes** avaliado e descartado por gate de anúncio.
- Perfis/custom formats: PT-BR Dublado, English Dub, Dual Audio; perfis
  Original/Dublado/Anime Japonês; defaults no Seerr.
- Torrent-indexer: categorias 2000/5000 no Torznab, atributo `category`,
  fallback `q=a`, reaproveitamento do `<category>`; binário ARM64 rebuildado e
  deployado.
- Prowlarr: Torrent dos Filmes e Starck Filmes adicionados como Torznab
  (`/api/...`) e sincronizados; BluDV/Comando/Vaca/Filme Torrent avaliados.
- Teste Minions 2015 no Radarr com o perfil Animação - Dublado: 6 releases
  aceitos (Dual), 156 rejeitados; seeds conferidos.
- Acesso externo via Tailscale: cards, bookmarks, busca e `custom.js` migrados
  para `<TAILSCALE_IP>`.
- WOL direto no card **PC Casa** (painel flutuante Gaming removido); status do
  PC testa Tailscale `<PC_TAILSCALE_IP>` + LAN `<PC_LAN_IP>`.
- Jellyfin: Buddy (2026) e O Estranho Mundo de Jack importados pelo Radarr não
  apareciam (`MovieCount 0`); o refresh manual importou os dois e iniciou o
  watcher de `/media/movies` (antes só `/media/Suits`). Intervalo do scan
  reduzido de 12h para 30 min; realtime não funciona no FUSE/NTFS-3G.
- Hook **Jellyfin Refresh** (Custom Script) no Radarr/Sonarr para On Import,
  On Upgrade e On Rename, com `/Library/Media/Updated` e fallback de refresh.
- Áudio: o perfil **Animação - Dublado** aceitou `Dual-Lat` (espanhol + inglês)
  porque `Dual Audio` valia 50 e o mínimo era 50; o perfil não exigia PT-BR. O
  arquivo do Jack tem faixas `spa` e `eng`, nenhuma `por`. Ajustado em
  2026-10-26: mínimo 100 + CF `Latino/Espanhol` −100; a busca do Jack deu
  154 releases, 0 aceitos. O release PT-BR do Rede Torrent apareceu depois com
  11 seeders, mas o Radarr não o casa pelo título em inglês; o arquivo espanhol
  permanece.
- Homepage: painel **Pedidos** (todos os perfis + Seerr) com proxy no
  media-agent; lista pendências, mostra a contagem no botão, tem filtros por
  tipo/perfil/status com paginação de 10 itens, verifica releases aceitos e
  troca para Original + busca. Teste do Jack: `Nenhum PT-BR aceito (154
  release(s) analisados)` com o botão **Buscar original**.
- FlareSolverr: `solvearr` trocado para a imagem oficial 3.5.0, 1024 MB,
  `shm_size: 1gb`, sessões e timeout 180s. **Comando Torrents** voltou e foi
  adicionado ao Prowlarr/Radarr/Sonarr (6 indexadores cada, na época); a página “listão”
  é ignorada. BluDV continua atrás do gate `promobr/x.gd`.
- CF `PT-BR Dublado` ampliado para reconhecer `brazilian`/`ptbr`; releases do
  torrent-indexer com `(brazilian, eng)` passaram a pontuar 150. No Radarr,
  Minions do Torrent dos Filmes apareceram aceitos (antes o `Dual` puro ficava
  em 50 e era rejeitado).
- Proxy **PT-BR Alternate Titles** no `gaming-agent` + indexer Torznab no
  Radarr: lê `MovieTranslations` (pt-BR/Portugal) do banco do Radarr, busca os
  títulos alternativos no Prowlarr e injeta o IMDb. O release PT-BR do Jack
  apareceu com score 100 e `accepted: true`; ainda não foi baixado.
- Proxy movido para o container **media-gateway** (rede `media`, sem porta
  publicada).
- Media e gaming separados: `gaming-agent` ficou só com status/WOL;
  `media-agent` (`8097`) cuida de Pedidos/Legendas (Radarr, Sonarr, Seerr,
  Bazarr e quota OpenSubtitles).
- Homepage com modo local/remoto: acesso por `<LAN_IP>` mostra gestão;
  acesso pelo Tailscale mostra Jellyfin/Seerr/Stremio + PC Casa e as abas
  Pedidos/Legendas.
- Portas de gestão presas ao IP `<LAN_IP>`; Jellyfin, Seerr, indexer,
  Homepage, Stremio, **gaming 8098** (status/WOL com senha) e **media-agent
  8097** (Pedidos/Legendas) continuam no
  Tailscale.
- Chave do Bazarr movida para `.bazarr_key` no servidor; `custom.js` sem segredo.
- Gaming público: 8098 expõe só `/gaming/status` (sem IP/MAC) e
  `/gaming/wake` com `X-Gaming-Password`; senha em `GAMING_PASSWORD` no `.env`
  e limite de 5 falhas/min. O 8100 privado continua LAN-only.
