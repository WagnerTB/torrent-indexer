# Stack de mídia no Raspberry Pi — operação e decisões

> **Nota de segurança:** IPs, MACs, usuários e caminhos absolutos foram substituídos por placeholders. Os valores reais ficam no `.env`/config local, fora do git. A senha do WOL agora usa `GAMING_PASSWORD` no `.env`; `.gaming_password` é fallback legado. Veja `SECURITY_AUDIT.md`.

Última atualização: 2026-10-26

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
> `<MEDIA_ROOT>/docker/homepage/{services.yaml,custom.js}`; as dos *arr ficam
> em `<MEDIA_ROOT>/docker/<serviço>/config.xml`; a do Prowlarr em
> `<MEDIA_ROOT>/docker/prowlarr/config.xml`; a do Bazarr em
> `<MEDIA_ROOT>/docker/bazarr/config/config.yaml`; a do Seerr em
> `<MEDIA_ROOT>/docker/seerr/settings.json`.

## 1. Serviços e portas

Compose: `<STACK_ROOT>/docker-compose.yml` (projeto Compose
`media`). `.env` na mesma pasta, não versionar.

| Serviço | Imagem | Porta no host | Config |
|---|---|---|---|
| `torrent-indexer` | `media/torrent-indexer:local` | `8080` → `7006` (UI/API, remoto) e `<LAN_IP>:8081` (métricas, LAN) | build local; binário `torrent-indexer-linux-arm64` |
| `redis` | `redis:alpine` | interna | volume `redis-data` |
| `meilisearch` | `getmeili/meilisearch` | interna | volume `meili-data` |
| `solvearr` | `ghcr.io/flaresolverr/flaresolverr` | interna (`8191`) | FlareSolverr 3.5.0 usado pelo indexer; 1024 MB + `shm_size: 1gb` |
| `qbittorrent` | `lscr.io/linuxserver/qbittorrent` | `<LAN_IP>:8082` (WebUI), `6881` TCP/UDP | `<MEDIA_ROOT>/docker/qbittorrent` |
| `sonarr` | `lscr.io/linuxserver/sonarr` | `<LAN_IP>:8989` | `<MEDIA_ROOT>/docker/sonarr2` |
| `prowlarr` | `lscr.io/linuxserver/prowlarr` | `<LAN_IP>:9696` | `<MEDIA_ROOT>/docker/prowlarr` |
| `bazarr` | `linuxserver/bazarr` | `<LAN_IP>:6767` | `<MEDIA_ROOT>/docker/bazarr` |
| `jellyfin` | `jellyfin/jellyfin` | `8096` (remoto) | `<MEDIA_ROOT>/docker/jellyfin` + `jellyfin-cache` |
| `stremio-server` | `stremio/server` | `11470`, `12470` (remoto) | `<MEDIA_ROOT>/stremio-server` |
| `homepage` | `ghcr.io/gethomepage/homepage` | `3000` (remoto, modo adaptativo) | `<MEDIA_ROOT>/docker/homepage` |
| `gaming-agent` | `python:3.12-alpine` (script local) | `<LAN_IP>:8099` (privado, LAN) e `8098` (público: status/WOL com senha) | `<MEDIA_ROOT>/docker/gaming-agent` |
| `media-agent` | `python:3.12-alpine` (script local) | `8097` (LAN + Tailscale, allowlist de IP) | `<MEDIA_ROOT>/docker/media-agent` |
| `media-gateway` | `python:3.12-alpine` (script local) | interna (`8099`, rede `media`) | `<MEDIA_ROOT>/docker/media-gateway` |
| `radarr` | `lscr.io/linuxserver/radarr` | `<LAN_IP>:7878` | `<MEDIA_ROOT>/docker/radarr` |
| `seerr` | `seerr/seerr` (sucessor do Jellyseerr) | `5055` (remoto) | `<MEDIA_ROOT>/docker/seerr` |

Acesso: **8096 (Jellyfin), 5055 (Seerr), 8080 (indexer/UI), 3000 (Homepage),
11470/12470 (Stremio), 8098 (gaming: status/WOL com senha) e 8097
(media-agent: Pedidos/Legendas)** ficam acessíveis pelo Tailscale; Radarr,
Sonarr, Prowlarr, Bazarr, qBittorrent, métricas, o **8099 privado** do
gaming-agent e o `media-gateway` ficam presos ao IP `<LAN_IP>` (LAN). O
Homepage detecta o host: no Tailscale esconde os cards de gestão, mas mantém as
abas Pedidos/Legendas via media-agent.

Limites de memória usados: Jellyfin 1536 MB; solvearr/FlareSolverr 1024 MB;
Sonarr/qBittorrent/Meilisearch 512 MB; Prowlarr/Bazarr/Radarr/Seerr/Homepage
384 MB; indexer/Stremio 256 MB; media-gateway 128 MB; Redis 192 MB;
gaming-agent 64 MB; media-agent 96 MB.

## 2. Armazenamento e caminhos

- Mídia: `<MEDIA_ROOT>` montado como `/media` nos containers.
- Downloads do qBittorrent: `<MEDIA_ROOT>/downloads`.
- Biblioteca de séries: `<MEDIA_ROOT>/Suits` (a série Suits) e
  `<MEDIA_ROOT>/series` (séries novas adicionadas pelo Sonarr).
- Animes: `<MEDIA_ROOT>/animes`.
- Filmes: `<MEDIA_ROOT>/movies`.
- Configs: `<MEDIA_ROOT>/docker/<serviço>`.
- Docker/containerd: `<DOCKER_DATA_ROOT>` (o SSD; ver `RASPBERRY_PI.md`).
- Hardlinks: os MKVs de Suits existem em `/media/downloads/...` e em
  `/media/Suits/Season 1`; são o mesmo inode. Legendas **não** são hardlinks.

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
  (`EnableRealtimeMonitor: true`), mas o monitor não funciona de forma confiável
  no `<MEDIA_ROOT>`: o volume é FUSE/`fuseblk` (NTFS-3G) e os eventos de
  criação/movimentação não chegam ao Jellyfin. Na prática, o Jellyfin depende do
  scan agendado. Em 2026-10-26 o intervalo de “Escanear a Biblioteca de Mídia”
  foi reduzido de 12h para **30 min**.
- Se um filme/episódio recém-importado não aparecer, forçar o scan
  (Dashboard → Scheduled Tasks ou `POST /Library/Refresh`). O scan também
  reinicia o watcher das pastas, mas o watcher continua sem receber eventos no
  FUSE.
- Após baixar uma legenda nova o Jellyfin ainda pode precisar de um
  refresh/scan do item; o `-1s` do Suits é aplicado no arquivo pelo Bazarr, não
  no Jellyfin.

### 3.1 Correção da biblioteca do Jellyfin

- A biblioteca Séries apontava para `/media` (a raiz inteira), o que indexava
  `downloads`, `docker`, `filmes`, etc. e criava “séries” falsas.
- Foi corrigida para `/media/Suits` + `/media/series` via `options.xml` e
  `.mblink` (`Suits.mblink` e `series.mblink`), com backup em
  `<MEDIA_ROOT>/docker/jellyfin/root/default/Séries/`.
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
  gravado em `<MEDIA_ROOT>/docker/{radarr,sonarr2}/scripts/`.
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

| Indexador | URL/Prowlarr | Status em 2026-10-26 |
|---|---|---|
| Rede Torrent | `Torznab` `http://torrent-indexer:7006`, `apiPath=/api` | Funciona; no Radarr e Sonarr |
| Torrent dos Filmes | `apiPath=/api/torrent-dos-filmes` | Funciona; no Radarr e Sonarr |
| Starck Filmes | `apiPath=/api/starck-filmes` | Funciona; no Radarr e Sonarr (só filmes) |
| The Pirate Bay | nativo | Funciona; Radarr e Sonarr |
| Torrentio | nativo | Funciona; Radarr e Sonarr |
| 1337x | nativo | Falha no Radarr por FlareSolverr/Cloudflare |
| BluDV | não adicionado | Cloudflare resolvido, mas o download usa gate `gate/go` → `promobr.online`/`x.gd`; retorna 0 |
| Comando Torrents | `apiPath=/api/comando_torrents` | Funciona com FlareSolverr oficial; no Radarr e Sonarr |
| Vaca Torrent | — | Domínio morto |
| Filme Torrent | — | Só nome em `IndexerNames`; sem handler |
| Dodo Filmes | — | Não existe no código atual |

Resumo atual: **Radarr tem 7 indexadores** (Comando, Rede, Torrent dos Filmes,
Starck, TPB, Torrentio e o proxy **PT-BR Alternate Titles**) e **Sonarr tem 6**
(Comando, Rede, Torrent dos Filmes, Starck, TPB, Torrentio), todos com
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

Após adicionar, rodar no Prowlarr o comando **ApplicationIndexerSync** e
conferir em Radarr/Sonarr → Settings → Indexers. O Prowlarr testa cada
indexador com uma busca e **recusa sincronizar** se o teste não retornar
resultado nas categorias configuradas.

O Sonarr perdeu Rede/1337x em uma sincronização porque o teste vazio usava o
fallback `q=2024`; o fallback do Torznab foi alterado para `q=a`, e o Rede
voltou. Em 2026-10-26 Comando, Torrent dos Filmes e Starck aparecem no Sonarr
(6 indexadores), mas o Starck é só filmes. O 1337x continua fora do
Radarr/Sonarr e depende do FlareSolverr.

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
curl -s 'http://<LAN_IP>:8080/api/rede_torrent?t=search&q=minions' | grep category
```

## 6. Perfis de qualidade, custom formats e Seerr

Custom formats (Radarr e Sonarr):

| ID | Nome | Regex | Uso |
|---|---|---|---|
| 1 | `PT-BR Dublado` | `(?i)\b(dublado|dublagem|nacional|pt[- ]?br|ptbr|portugu[eê]s|portugues|brazilian)\b` | positivo no perfil dublado, negativo no original/anime |
| 2 | `English Dub` | `(?i)(english[ .-]?dub|dubbed|\bdub\b)` | negativo no original/anime |
| 3 | `Dual Audio` | `(?i)\bdual\b` | aceita releases “Dual” nos perfis dublados |
| 4 | `Latino/Espanhol` | `(?i)\b(lat|latam|latino|latinoamericano|castellano|espanhol|español|spanish)\b` | negativo nos perfis dublados |

Perfis:

- **Radarr**
  - `Filmes - Original` (id 7): PT-BR −100, English −100, Dual 0; mínimo 0.
  - `Animação - Dublado` (id 8): PT-BR 100, English 0, Dual 50, Latino
    −100; mínimo 100; cutoff 100.
- **Sonarr**
  - `Séries - Original` (id 7): PT-BR −100, English −100, Dual 0; mínimo 0.
  - `Anime - Japonês` (id 8): PT-BR −100, English −100, Dual 0; mínimo 0.
  - `Séries - Dublado` (id 9): PT-BR 100, English 0, Dual 50, Latino −100;
    mínimo 100; cutoff 100.

No **Seerr**, os defaults são: Radarr `Filmes - Original` (7), Sonarr
`Séries - Original` (7), anime `Anime - Japonês` (8). Para animação dublada,
escolher no pedido `Animação - Dublado` (filme) ou `Séries - Dublado` (série).
Se o dropdown não listar os perfis novos, abrir Settings → Services →
Radarr/Sonarr e clicar **Test/Save** uma vez para recarregar.

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
- Config: `<MEDIA_ROOT>/docker/seerr/settings.json` e `db/`.
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
`<MEDIA_ROOT>/docker/bazarr/config/config.yaml`.

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
  - Script: `<MEDIA_ROOT>/docker/bazarr/scripts/shift_subs.py`.
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
- A aba **Legendas** do Homepage mostra a quota, busca/filtro por episódio ou
  série, “Buscar todas pendentes” e “Sincronizar existentes”. Ele chama o proxy
  `/bazarr` do media-agent; a API key do Bazarr fica em `.bazarr_key` no
  servidor, não no `custom.js`.
- A fila é salva no `localStorage` do navegador (`subs_queue_v1`); o botão
  “Executar fila agora” aparece quando o reset chega. Ela não roda em
  background com o navegador fechado.
- O painel usa o job real do Bazarr para dar feedback (“Legenda baixada” ou
  “Nao encontrada” + detalhe do provedor).
- Limite de segurança: se a quota não puder ser consultada, o painel usa
  trava de 5/dia.

## 9. Homepage (dashboard)

- URL LAN: `http://<LAN_IP>:3000`.
- URL Tailscale: `http://<TAILSCALE_IP>:3000`.
- Config: `<MEDIA_ROOT>/docker/homepage/{settings,services,widgets,bookmarks}.yaml`
  e `custom.js`.
- Grupos: Filmes e Séries (Jellyfin, Stremio, Seerr), Media Services Status
  (Radarr, Sonarr, Prowlarr, Bazarr, qBittorrent), Gaming (PC Casa). O card do
  torrent-indexer foi removido do dashboard; o serviço continua rodando e
  exposto em `:8080`. O estilo e as colunas de cada grupo ficam em
  `settings.yaml` (`layout`), que também define a ordem dos grupos.
- `custom.js` adiciona:
  - barra de abas fixa no topo: **Home**, **Pedidos** e **Legendas**. A barra
    acompanha a largura do conteúdo e fica no topo também no celular;
  - **Home** mantém os cards, widgets e busca exatamente como estão;
  - **Pedidos** e **Legendas** mantêm o cabeçalho/widgets/busca no topo e
    escondem cards, bookmarks e rodapé para usar a área principal da página;
  - URLs por query string: `/?tab=pedidos` e `/?tab=legendas` (Home é `/`).
    Funcionam ao recarregar, compartilhar e no botão voltar. O Homepage não
    tem rotas `/pedidos` e `/legendas` — elas retornam 404 —, por isso não são
    usados caminhos reais sem um proxy na frente;
  - aba **Pedidos** (perfis dublados + Seerr): contadores por status, filtro
    por situação (inclui **No Seerr**) e busca por título. Cada filme/série
    mostra se está baixado, parcial, baixando, na fila, procurando, com erro ou
    sem arquivo, além de progresso, tempo restante e último evento do
    Radarr/Sonarr. Pedidos do Seerr pendentes/aprovados que ainda não chegaram
    ao Radarr/Sonarr aparecem com o status do Seerr e o perfil solicitado;
    pedidos recusados ou que falharam mostram o erro de forma explícita.
    O botão **Adicionar série/anime** busca no Sonarr/TVDB, mostra se a série
    já existe e permite escolher perfil (Original, Anime - Japonês ou
    Séries - Dublado), pasta raiz e tipo; ao adicionar, nada é monitorado, e o
    painel lista temporadas/episódios para marcar só os desejados e buscar
    apenas esses;
  - aba **Legendas**: quota da OpenSubtitles, busca por série ou episódio,
    agrupamento por série, pendências, fila local (`localStorage`), feedback
    do Bazarr e sincronização de legendas existentes;
  - verificação de releases PT-BR no Radarr/Sonarr e **Buscar original**
    quando não há PT-BR aceito;
  - botão **Ligar PC** dentro do card **PC Casa** (status/WOL).
- `custom.js` detecta o host:
  - acessado por `<LAN_IP>`, `localhost` ou `127.0.0.1` = **modo local**:
    todos os cards, as abas Home/Pedidos/Legendas e o Gaming; o WOL usa o 8099
    privado, sem senha.
  - acessado por `<TAILSCALE_IP>` (ou outro host) = **modo remoto**: esconde os
    cards de gestão (Radarr, Sonarr, Bazarr, Prowlarr, qBittorrent), o grupo
    Atalhos e o grupo Media Services Status; mantém Jellyfin, Seerr, Stremio,
    **PC Casa/Gaming** e as abas **Pedidos** e **Legendas**. Essas abas usam o
    `media-agent` em `http://<host-atual>:8097`.
    O botão **Ligar PC** usa o endpoint público `:8098/gaming/wake` e pede a
    senha (`.gaming_password`); o status vem de `:8098/gaming/status` sem
    IP/MAC.
- Links: os serviços de gestão usam `http://<LAN_IP>:<porta>`; os remotos
  (Jellyfin/Seerr/Stremio) são reescritos pelo `custom.js` para o host
  atual. `siteMonitor` e widgets internos continuam usando nomes de container
  (`jellyfin:8096`, `sonarr:8989`, etc.).
- A barra de busca do topo é `provider: custom` apontando para a busca do
  Seerr; não é uma busca web genérica.
- A chave do Bazarr saiu do `custom.js`: o painel Legendas usa o proxy
  `/bazarr` do media-agent, que guarda a chave em `.bazarr_key` no servidor.
  As chaves restantes ficam no `services.yaml` e são usadas pelo servidor do
  Homepage, não pelo navegador.
- `HOMEPAGE_ALLOWED_HOSTS: "*"`. O Homepage e o media-agent (`8097`) são
  expostos na LAN e no Tailscale; os demais serviços de gestão continuam
  presos ao IP da LAN.

## 10. Gaming agent (PC da casa)

- Container `gaming-agent` (host network), só WOL/status: `8099` privado
  (**LAN only**, `LISTEN_HOST=<LAN_IP>`) e `8098` público (LAN + Tailscale).
- Script: `<MEDIA_ROOT>/docker/gaming-agent/agent.py`; monta apenas o diretório
  `/app` (`.gaming_password`). Não acessa mais Bazarr, Radarr, Sonarr ou Seerr.
- Endpoints:
  - `GET /status`: ping em `PC_IP` (Tailscale `<PC_TAILSCALE_IP>` e LAN
    `<PC_LAN_IP>`) e retorna `online`, `status`, `ips`, `mac`, `checked_at`.
  - `POST /wake` (e `GET /wake`): envia magic packet para
    `<MAC>`, portas 9/7, broadcast `<PC_LAN_IP>55` e
    `<PUBLIC_IP>`.
- O 8098 é público (LAN + Tailscale) e só aceita:
  - `GET /gaming/status`: `online`, `status`, `checked_at` (sem IP/MAC);
  - `POST /gaming/wake`: exige `X-Gaming-Password`; a senha fica em
    `.gaming_password` (`GAMING_PASSWORD_FILE`), com limite de 5 falhas/min.
- A senha pode ser trocada editando
  `<MEDIA_ROOT>/docker/gaming-agent/.gaming_password`; o agente lê a cada
  request, sem reiniciar. O navegador guarda a senha em `sessionStorage` depois
  do primeiro WOL bem-sucedido.
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
- Script: `<MEDIA_ROOT>/docker/media-agent/media_agent.py`; monta o
  `config.yaml` do Bazarr, os `config.xml` de Radarr/Sonarr, o config do Seerr
  (`/seerr/settings.json`) e a chave `<MEDIA_ROOT>/docker/media-agent/.bazarr_key`
  (`BAZARR_KEY_FILE`). As API keys nunca vão para o navegador.
- Endpoints:
  - `GET /subs/quota`: quota real da OpenSubtitles (seção 8.1).
  - `GET /arr/pending`: filmes no perfil `Animação - Dublado` (8) e séries no
    `Séries - Dublado` (9), com `hasFile`.
  - `GET /arr/pending?status=1`: mesma lista enriquecida com `status`
    (`downloaded`, `partial`, `downloading`, `queued`, `searching`, `error`,
    `missing`, `request_pending`, `request_approved`, `request_declined`,
    `request_failed`), fila do *arr (progresso/tempo restante/erro), último
    evento do histórico e comando de busca ativo. Consulta `/api/v3/queue`,
    `/api/v3/history` e `/api/v3/command` em paralelo e cruza com
    `/api/v1/request` do Seerr por TMDB (filmes) ou TVDB (séries). Pedidos do
    Seerr sem item correspondente nos perfis dublados entram como itens
    somente-Seerr; `seerrError` é preenchido se o Seerr estiver indisponível,
    sem derrubar a lista do *arr.
  - `POST /arr/check` `{"kind":"movie|series","id":N}`: consulta
    `/api/v3/release` no *arr e retorna quantos releases foram aceitos.
  - `POST /arr/search` `{"kind","id"}`: dispara a busca no perfil atual.
  - `POST /arr/switch` `{"kind","id"}`: troca o item para o perfil Original
    (Radarr 7 / Sonarr 7) e dispara a busca.
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

## 12. Fluxo de um pedido

1. Você pesquisa no Seerr e escolhe o perfil (`Filmes - Original`,
   `Animação - Dublado`, `Séries - Original`, `Séries - Dublado` ou
   `Anime - Japonês`).
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
  Bazarr 6767, qBittorrent WebUI 8082, métricas 8081, gaming-agent **8099
  privado** e `media-gateway` (este nem publica porta). O peer do qBittorrent
  (6881) fica aberto para torrents.
- O Homepage detecta o host: acesso por `<LAN_IP>` mostra tudo; acesso pelo
  IP do Tailscale esconde os cards de gestão, mas mantém Jellyfin, Seerr,
  Stremio, **PC Casa** (WOL com senha) e as abas **Pedidos/Legendas** via
  `media-agent:8097`.
- A chave do Bazarr saiu do `custom.js` e vive em `.bazarr_key` no servidor; as
  demais chaves ficam no `services.yaml` e são usadas pelo servidor do
  Homepage, não pelo navegador.
- O gaming-agent tem dois listeners, só de WOL/status: o 8099 privado (LAN,
  sem auth) e o 8098 público, que expõe `/gaming/status` (sem IP/MAC) e
  `/gaming/wake` (senha em `.gaming_password`, limite de 5 falhas/min).
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
3. **Sonarr**: já está com 6 indexadores (Comando, Torrent dos Filmes, Starck,
   Rede, TPB, Torrentio); validar se Comando/Torrent dos Filmes retornam TV
   dublada na prática. O Starck é só filmes e o 1337x depende do FlareSolverr.
4. **Indexadores**: Comando voltou (FlareSolverr oficial + sessão + timeout
   180s). BluDV continua atrás do gate `promobr/x.gd`; Vaca morto; Filme
   Torrent sem handler; Dodo não existe. Decidir se implementa/remove.
5. **Seeds**: o Torrent dos Filmes não informa seeders no Radarr (mostra
   vazio); preferir Torrentio/TPB quando for escolher manualmente. O
   `minSeeds=1` está no App Profile do Prowlarr e nos *arr.
6. **-1s**: válido só para Suits; não usar “Sincronizar existentes” no Suits
   para não desfazer. Para outro release/série, criar um pós-processamento
   próprio.
7. **Fila de legendas**: é do navegador; se quiser execução em background,
   criar um cron/serviço no agente.
8. **Commit**: `api/torznab.go` (categorias + fallback) e os docs estão
   alterados no working tree; revisar e commitar.
9. **Compose versionado**: o `deploy/raspberry/docker-compose.yml` foi
   atualizado em 2026-10-26; manter sincronizado com o compose vivo.
10. Itens órfãos de `/media/downloads` e `/media/docker` no banco do Jellyfin;
    limpar se aparecerem.
11. **Acesso externo**: Homepage e serviços já usam o IP Tailscale
    `<TAILSCALE_IP>`, e o WOL já está no card **PC Casa**. Se o IP Tailscale do Pi
    mudar, atualizar `services.yaml`, `bookmarks.yaml`, `widgets.yaml` e
    `custom.js`.
12. **Jellyfin/FUSE**: o realtime não recebe eventos no NTFS-3G; o scan de
    30 min cobre a importação e o hook **Jellyfin Refresh** atualiza na hora.
    Se o hook for desativado, o fallback é o scan de 30 min.
13. **Áudio PT-BR**: os perfis dublados agora exigem PT-BR (mínimo 100) e
    rejeitam `Latino/Espanhol`. O proxy **PT-BR Alternate Titles** no
    `media-gateway` encontra o release do Jack no Rede Torrent (11 seeders) e o
    Radarr o aceita com score 100; `/arr/check` retorna **1 aceito de 160**,
    mas ainda não foi baixado. O painel **Pedidos** permite trocar para o
    perfil Original e buscar quando não houver PT-BR aceito.

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

# Jellyfin: forçar scan (token em <MEDIA_ROOT>/docker/jellyfin/data/jellyfin.db)
curl -s -X POST -H "X-Emby-Token: <JELLYFIN_TOKEN>" \
  http://<LAN_IP>:8096/Library/Refresh

# Bazarr: status
curl -s -H "X-API-KEY: <BAZARR_API_KEY>" \
  http://<LAN_IP>:6767/api/system/status
```

## 17. Histórico das implementações (2026-10-26)

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
  Radarr 6 indexadores (Comando incluído).
- Seerr (sucessor do Jellyseerr) na 5055, com Jellyfin/Sonarr/Radarr.
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
- Homepage: painel **Pedidos** (perfis dublados) com proxy no media-agent;
  lista pendências, mostra a contagem no botão, verifica releases aceitos e
  troca para Original + busca. Teste do Jack: `Nenhum PT-BR aceito (154
  release(s) analisados)` com o botão **Buscar original**.
- FlareSolverr: `solvearr` trocado para a imagem oficial 3.5.0, 1024 MB,
  `shm_size: 1gb`, sessões e timeout 180s. **Comando Torrents** voltou e foi
  adicionado ao Prowlarr/Radarr/Sonarr (6 indexadores cada); a página “listão”
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
  `/gaming/wake` com `X-Gaming-Password`; senha em `.gaming_password` e limite
  de 5 falhas/min. O 8099 privado continua LAN-only.
