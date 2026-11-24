# Status dos sites e do indexer

> **Nota de segurança:** IPs, MACs, usuários e caminhos absolutos foram substituídos por placeholders. Os valores reais ficam no `.env`/config local, fora do git. A senha do WOL agora usa `GAMING_PASSWORD` no `.env`; `.gaming_password` é fallback legado. Veja `SECURITY_AUDIT.md`.

Última verificação: 2026-10-27

Documentos relacionados:

- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) — visão geral da arquitetura,
  endpoints, configuração e estado do projeto.
- [RASPBERRY_PI.md](RASPBERRY_PI.md) — migração para Raspberry Pi 4.
- [MEDIA_STACK.md](MEDIA_STACK.md) — stack de mídia, perfis, legendas e
  pendências no Pi.

Este documento registra o que já foi testado, os problemas encontrados e o que
foi alterado. A ideia é não repetir os mesmos testes e não confundir site lento
com travamento do processo.

## Resumo

| Indexer | Situação | Ação necessária |
|---|---|---|
| comando_torrents | Funciona quando o FlareSolverr está disponível | Configurar `FLARESOLVERR_ADDRESS` |
| baixarapido | Validado: 24 resultados para `matrix`; magnet direto e deduplicação por infohash | Nenhuma; algumas páginas não informam tamanho |
| torrent-dos-filmes | Validado: 19 resultados | Corrigido: volta a ler magnet direto e mantém fallback `systemads` |
| starck-filmes | Validado: 6 resultados | Corrigido: URL padrão v27 + resolvedor do redirect `filmedl.com` |
| rede_torrent | Validado: 39 resultados | Corrigido: nova URL, `?busca=` e novos seletores |
| vaca_torrent | Descontinuado: `vaqueirofilmes.com` virou streaming e não expõe magnet links | Mantido por compatibilidade; retorna 0 resultados |
| busca agregada (`/search`, `/ui/`) | Validado: 152 documentos, 10 resultados para “The Last of Us” | Meilisearch habilitado no compose; use `/ui/` ou `/search?q=...` |
| seeds / trackers | Validado com Ubuntu (34 seeds) e House of the Dragon S03 (12–99 seeds) | Corrigido timeout, cache de zero e escolha do tracker |
| temporadas / episódios | Implementado e validado com House of the Dragon S03 | Parser best-effort, filtros `season`/`episode` e agrupamento na UI |
| bludv | Páginas abrem via FlareSolverr, mas downloads usam gate de anúncio (`gate/go` → `promobr.online` → afiliado) | Sem correção simples; considerar indisponível até novo método |

### Estado no Pi em 2026-11-24

Teste com `q=matrix` direto nos endpoints do torrent-indexer e conferência no
Prowlarr/Radarr/Sonarr:

| Indexer | Resultado `matrix` | Prowlarr | Radarr | Sonarr |
|---|---|---|---|---|
| `rede_torrent` | 39 resultados, magnet direto | Sim | Sim | Sim |
| `torrent-dos-filmes` | 19 resultados, magnet direto | Sim (`/api/torrent-dos-filmes`) | Sim | Sim |
| `starck-filmes` | 3 resultados, magnet direto | Sim (`/api/starck-filmes`) | Sim | Sim (só filmes) |
| `baixarapido` | **24 resultados** (deduplicados), magnet direto | Sim (`/api/baixarapido`) | Sim | Sim |
| `bludv` | **0 resultados** (gate `promobr/x.gd`) | Não | Não | Não |
| `comando_torrents` | 14–20 resultados com FlareSolverr oficial | Sim (`/api/comando_torrents`) | Sim | Sim |
| `vaca_torrent` | Descontinuado (Vaqueiro Filmes, sem magnets) | Não | Não | Não |
| `filme_torrent` | 0; só nome em `IndexerNames`, sem handler | Não | Não | Não |
| `1337x` | Nativo; funciona com proxy `solvearr` (~110s na 1ª busca) | Sim | Sim | Sim |
| `UIndex` | Nativo; Cloudflare resolvido pelo proxy `solvearr` | Sim | Sim | Sim |
| `YTS` | Nativo; API `yts.gg` | Sim | Sim | Não (filmes) |
| `The Pirate Bay` | Nativo | Sim | Sim | Sim |
| `Torrentio` | Nativo | Sim | Sim | Sim |

O Radarr ficou com **11 indexadores** (1337x, Baixarapido, Comando, Rede,
Torrent dos Filmes, Starck, TPB, Torrentio, UIndex, YTS e o proxy
**PT-BR Alternate Titles**) e o Sonarr com **9** (1337x, Baixarapido, Comando,
Rede, Torrent dos Filmes, Starck, TPB, Torrentio e UIndex), todos com
`minimumSeeders = 1`, exceto o proxy (0). O app sync do Prowlarr usa query
vazia; o fallback do Torznab é `q=a`. Os proxies do Prowlarr foram corrigidos
para `http://solvearr:8191/` com timeout 180s.

### Teste Minions e perfis de áudio

No Radarr, o Minions 2015 foi adicionado com o perfil **Animação - Dublado**
(id 8): 162 releases, **6 aceitos**, 156 rejeitados (inglês-only, 4K/remux ou
score abaixo do mínimo). Aceitos:

- `Minions 2015 1080p BluRay DUAL [Dublado] LAPUMiA` — TPB, 1 seed, CF 150.
- `Minions.2015.1080P-Dual-Lat` — Torrentio, 18 seeds, CF 50.
- `Minions.2015.1080p.BluRay.Dual` — Torrentio, 6 seeds, CF 50.
- Três do Torrent dos Filmes (Dual), com `seeders` vazio no Radarr.

Custom formats: `PT-BR Dublado` (inclui `nacional`, `brazilian` e `ptbr`),
`English Dub`, `Dual Audio` e `Latino/Espanhol` (−100); perfis, scores e
defaults do Seerr em [MEDIA_STACK.md](MEDIA_STACK.md) §6. O `minSeeds=1`
descarta 0 seed quando o indexador informa o valor; o Torrent dos Filmes não
informa.

## O que foi observado nos testes

### comando_torrents
- `https://comando.la/` retorna HTTP 403 com `Cf-Mitigated: challenge`.
- Com o FlareSolverr **oficial 3.5.0** (sessão, `maxTimeout` 180s), o desafio é
  resolvido; a primeira consulta leva ~80-120s e as seguintes reaproveitam a
  sessão/cache (segundos).
- `/indexers/comando_torrents?q=salve se quem puder` retornou 200 com 2 itens;
  `/api/comando_torrents?t=search&q=a` retornou 42 itens.
- A página “listão” (`/listao-de-filmes-classicos...`) tem centenas de magnets e
  foi ignorada no handler para não travar a resposta.
- Adicionado ao Prowlarr e sincronizado no Radarr/Sonarr (id 6).
- Conclusão: funciona, mas a primeira busca de cada domínio é lenta.

### torrent-dos-filmes
- `https://torrentdosfilmes.se/?s=matrix` retorna HTTP 200.
- A página de detalhe atual expõe `magnet:` diretamente em `div.content`.
- Código do `HEAD` (sem alterações locais) retornou **19 resultados**.
- A alteração local não commitada que só seguia links `systemads.net` fazia o
  indexer retornar **0 resultados**.
- Correção aplicada: lê magnet direto primeiro e usa `systemads` apenas como
  fallback para páginas antigas.
- Validação após a correção: HTTP 200 em 7,1s, **19 resultados** para
  `q=matrix`. O comando encerrou sozinho e o servidor foi parado no `finally`.

### starck-filmes
- `https://www.starckfilmes-v10.com/?s=matrix` retorna HTTP 522.
- `https://starckfilmes-v27.com/?s=matrix` retorna HTTP 200 e a listagem tem
  os seletores `.item` / `.sub-item`.
- A página de detalhe não tem mais `magnet:` nem `data-u`; agora os downloads
  apontam para `https://filmedl.com/?xid=...`.
- O fluxo do `filmedl.com` foi validado manualmente: formulários encadeados
  (`radardamoda.com`) até uma página com `<body data-id="...">`.
- O `data-id` é uma string embaralhada + Base64 URL; após desembaralhar com
  passo 3 e decodificar, o resultado é um `magnet:`.
- Em alguns links o `data-id` é uma URL `https://filmedl.com/?sid=...`; o
  resolvedor segue essa URL e continua a cadeia até o magnet.
- Correção aplicada em `api/starck_download.go`; a URL padrão passou para v27.
- Validação após a correção: HTTP 200 em 8,5s, **6 resultados**, 0 títulos
  vazios, para `q=matrix`.

### rede_torrent
- `https://redetorrent.com/` agora serve o site `redestorrents.com`.
- A busca antiga (`index.php?s=`) retorna HTTP 504.
- A busca nova (`https://redestorrents.com/index.php?busca=matrix`) retorna
  HTTP 200 com cartões `.custom-card` e links `.cover-link`.
- A página de detalhe usa `h1.movie-title`, `.download-list`,
  `.spec-card-glass` e magnet direto.
- Correção aplicada em `api/rede_torrent.go`.
- Validação após a correção: HTTP 200 em 5,5s, **39 resultados** para
  `q=matrix`. O comando encerrou sozinho e o servidor foi parado no `finally`.

### baixarapido
- URL: `https://baixarapido.com/`.
- Busca: `index.php?busca=<query>` (formulário GET com campo `busca`).
- Listagem: `div[itemprop="itemListElement"]` com `a[itemprop="url"]` para a
  página de detalhe.
- Detalhe: magnet em `a[href^="magnet:"]`; tabela com `Lançamento`, `Idioma`,
  `Tamanho`, `Qualidade`, `Nota IMDb`.
- Implementado em `api/baixarapido.go`, rota `/indexers/baixarapido` e Torznab
  `/api/baixarapido`.
- Validação 2026-11-24: **24 resultados** para `q=matrix`, deduplicados por
  infohash; títulos com nomes de sites (`VACATORRENT.COM`, `COMOEUBAIXO.COM`)
  limpos; Prowlarr/Radarr/Sonarr OK.
- Limitação: algumas páginas não informam `Tamanho`; nesses casos o campo fica
  vazio (o magnet continua válido).

### xterfilmes (xfilme.org)
- `xfilme.org` redireciona para `https://www.xterfilmes.com.br/`.
- Tem busca (`/?s=`) e catálogo de filmes/séries, mas o botão de download usa
  um redirect `?go=...` para `metilinksemvoce.site` (gate de anúncio).
- Não foi adicionado ao Prowlarr; exigiria contornar o gate, o que não é
  confiável nem desejável.

### vaca_torrent
- `https://vacatorrentmov.com/` redireciona para `https://vaqueirofilmes.com/`
  (Vaqueiro Filmes), que usa o mesmo tema `VacaTorrent` mas virou site de
  streaming.
- A busca GET `?s=` funciona e a listagem ainda usa `.i-tem_ht`, mas as páginas
  de detalhe **não expõem magnet links**; o `.streaming-container` está vazio e
  o antigo endpoint AJAX retorna `0`.
- Conclusão: o Vaca Torrent como indexador de torrents foi descontinuado. O
  handler foi mantido por compatibilidade, com o domínio padrão atualizado para
  `https://vaqueirofilmes.com/` e mensagem explícita de descontinuidade; hoje
  retorna 0 resultados.

### bludv
- `https://bludv-v1.xyz/` redireciona para `https://bludvfilmes2.xyz/` e ambos
  retornam HTTP 403 com challenge da Cloudflare.
- Com o FlareSolverr rodando no Docker, a listagem e as páginas de detalhe são
  abertas com sucesso (pool de 5 sessões), mas o endpoint retornou **0
  resultados** em ~64s.
- Os links de download agora são
  `https://bludvfilmes2.xyz/gate/go/<id>?p=...`, que redirecionam para uma
  página de anúncio (`promobr.online`) e depois para `x.gd`/`valedesconto.shop`.
  Não há magnet exposto automaticamente.
- Teste em 2026-10-26 com FlareSolverr oficial: 200 após ~4m45s, **0 resultados**.
- O scraper antigo procurava magnet direto e domínios de adware
  (`seuvideo`, `systemads`, `superadsgo`); isso não se aplica mais.
- Conclusão: o problema não é só FlareSolverr. O download está atrás de um gate
  de anúncio; automatizar esse fluxo é frágil e provavelmente exige interação
  humana. Manter como indisponível até haver um método novo.

## Correção da “trava” no startup

Antes, `NewFlareSolverr` inicializava o pool de sessões de forma síncrona. Se o
FlareSolverr estivesse configurado mas inacessível, o servidor demorava para
subir. Além disso, o loop de criação de sessões podia girar indefinidamente
quando a criação falhava.

Alterações em `requester/flaresolverr.go`:
- Inicialização do pool em background (`go f.initialize()`).
- Timeout de inicialização de 10s no cliente usado pelo pool.
- Loop de criação de sessões limitado por tentativas.
- Até 6 tentativas com 5s de intervalo, para tolerar o FlareSolverr subindo
  depois do indexer.
- Se o pool ficar vazio, o FlareSolverr não é marcado como pronto.
- Logs claros: “Initializing...”, “session pool ready” ou erro.
- `Get` retorna vazio rapidamente enquanto o pool não estiver pronto.
- `depends_on` adicionado no compose para Redis e FlareSolverr.

Teste realizado com `FLARESOLVERR_ADDRESS=http://<LAN_IP>.1:8191`
(endereço inacessível):
- `GET /` respondeu HTTP 200 em ~2s.
- O erro do FlareSolverr apareceu no log depois de ~10s, sem bloquear o servidor.

## FlareSolverr oficial e Comando (2026-10-26)

- `solvearr` passou a usar `ghcr.io/flaresolverr/flaresolverr:latest` (3.5.0),
  `mem_limit: 1024m`, `shm_size: 1gb`.
- `FLARESOLVERR_TIMEOUT_SECONDS=180`, `FLARESOLVERR_USE_SESSIONS=true` e
  `FLARESOLVERR_POOL_SIZE=2`.
- Teste de sessão: primeira busca Comando em 81s; segunda (`q=matrix`) em 5,8s.
- `requester/flaresolverr.go` ganhou `FLARESOLVERR_USE_SESSIONS` (default false)
  para permitir requests sessionless quando necessário.
- `api/comando_torrents.go` ignora links `listao`/`lista-de`.
- BluDV continua sem magnet; o gate `promobr/x.gd` exige interação.

## Títulos alternativos (2026-10-26)

- O Radarr guarda `alternateTitles` do TMDB mas envia só o título em inglês na
  busca; alterar `title`/`originalTitle` via API não funciona.
- O container **`media-gateway`** expõe o proxy Torznab em `/torznab/api`; o
  Radarr usa o indexer **PT-BR Alternate Titles**
  (`http://media-gateway:8099/torznab`, `apiPath=/api`, chave `alternate`,
  `minimumSeeders=0`). O gateway fica na rede `media`, sem porta publicada.
- O proxy lê `MovieTranslations` (Language 18/30 = pt-BR/Portugal) do
  `radarr.db`, consulta os indexers brasileiros no Prowlarr e injeta o IMDb do
  filme nos resultados.
- Para o Jack, o release `O Estranho Mundo de Jack (1993) BDrip 1080p Dublado
  dat2014` apareceu com **score 100** e `accepted: true` no Radarr; a
  verificação `/arr/check` retorna **1 aceito de 160**, mas ainda não foi
  baixado.
- O XML devolve `downloadUrl` do Prowlarr com a API key; por isso o gateway é
  interno. Para séries, o Sonarr não guarda traduções no banco; avaliar
  TVDB/API.

## Acesso e dashboard (2026-10-27)

- Tailscale: Jellyfin 8096, Seerr 5055, torrent-indexer 8080, Homepage 3000,
  Stremio 11470/12470, gaming 8098 (status/WOL com senha) e media-agent 8097
  (Pedidos/Legendas).
- LAN-only (`<LAN_IP>`): Radarr 7878, Sonarr 8989, Prowlarr 9696, Bazarr
  6767, qBittorrent WebUI 8082, métricas 8081, gaming-agent 8099 (só WOL) e
  `media-gateway` (sem porta).
- Homepage adaptativo: `<LAN_IP>:3000` mostra tudo; `<TAILSCALE_IP>:3000`
  esconde os cards de gestão e mantém Jellyfin/Seerr/Stremio + PC Casa e as
  abas Pedidos/Legendas via media-agent.
- Aba Pedidos: além do status dos perfis dublados no Radarr/Sonarr, mostra
  pedidos do Seerr pendentes/aprovados que ainda não chegaram aos *arr e
  recusados/falhos. Também busca séries/animes no Sonarr, adiciona com o perfil
  escolhido (sem monitorar tudo) e permite marcar e buscar episódios
  específicos. Os grupos do dashboard são Filmes e Séries, Media Services
  Status e Gaming.
- WOL remoto: o card PC Casa usa `:8098/gaming/status` e `:8098/gaming/wake`;
  a senha vem de `GAMING_PASSWORD` no `.env` e o WOL exige
  `X-Gaming-Password` (5 falhas/min); `.gaming_password` é fallback legado. O
  8099 privado continua LAN-only.
- A chave do Bazarr saiu do `custom.js`; a aba Legendas usa o proxy
  `/bazarr` do media-agent e a chave fica em
  `<CONFIG_ROOT>/media-agent/.bazarr_key`.
- O media-agent (`8097`) não tem autenticação, mas só aceita LAN
  (`<LAN_SUBNET>`) e Tailscale (`<TAILSCALE_RANGE>`); ele pode adicionar séries,
  monitorar episódios e alterar perfis no Sonarr.

## Infraestrutura

O `docker-compose.yml` agora inclui os serviços `flaresolverr` e
`meilisearch`, já conectados à rede `indexer`. O `torrent-indexer` aponta para
`http://flaresolverr:8191` e `http://meilisearch:7700`.

```bash
docker compose up -d
```

Isso sobe indexer, Redis, FlareSolverr e Meilisearch juntos. Sem o
FlareSolverr, os sites protegidos por Cloudflare (`comando_torrents` e `bludv`)
ficam indisponíveis. Sem o Meilisearch, `/search` e `/ui/` não funcionam.

## Raspberry Pi

Alvo previsto: Raspberry Pi 4 (8 GB de RAM) com sistema 64-bit (`arm64`).

- O projeto tem builds para `arm`, `armv7` e `arm64`; no Pi 4 com SO 64-bit use
  `arm64`.
- O `Dockerfile` usa `golang:1.24` + `alpine:latest`, que têm imagens
  multi-arch. `docker compose build` funciona no Pi, mas a compilação Go pode
  ser lenta. Alternativa: buildar no PC com
  `docker buildx build --platform linux/arm64 -t torrent-indexer .` e levar a
  imagem, ou usar o binário `torrent-indexer-linux-arm64` (lembrando que o
  binário do repositório pode estar desatualizado em relação às correções).
- 8 GB é suficiente para indexer + Redis + FlareSolverr + Meilisearch. O
  FlareSolverr (Chrome) é o componente mais pesado; se faltar memória, rode sem
  ele e aceite que `comando_torrents` e `bludv` ficarão indisponíveis.
- Confirme se as imagens do FlareSolverr e do Meilisearch têm suporte `arm64`.
  Redis alpine tem.
- O script `scripts/check-indexers.ps1` é PowerShell; no Pi use `curl`/bash.

## Busca agregada (Meilisearch)

O `docker-compose.yml` agora sobe o Meilisearch e o indexer aponta para ele.
A UI fica em:

```text
http://localhost:8080/ui/
```

A API de busca agregada:

```powershell
curl.exe -G --data-urlencode "q=the last of us" --data-urlencode "limit=10" `
  http://localhost:8080/search
```

O índice não é um crawl completo. Ele é populado quando um endpoint de indexer
é consultado. A UI agora tem fallback ao vivo: se o cache retornar 0, ela
consulta `torrent-dos-filmes`, `rede_torrent`, `starck-filmes` e
`comando_torrents` em paralelo (até 50 resultados por indexer), junta,
deduplica e indexa. A primeira busca de um termo novo pode levar ~10–20s;
depois fica no cache. `bludv` e `vaca_torrent` ficam fora do fallback por
estarem indisponíveis.

Para indexar uma série antes de usar o `/search`:

```powershell
curl.exe -G --data-urlencode "q=the last of us" `
  --data-urlencode "filter_results=false" `
  http://localhost:8080/indexers/torrent-dos-filmes
```

Teste realizado:
- `torrent-dos-filmes`: 132 resultados para “The Last of Us”
- `rede_torrent`: 20 resultados
- Índice inicial: 152 documentos
- `/search?q=the last of us&limit=10`: 10 episódios retornados
- “Game of Thrones” e “Suits”: indexados pela UI
- “Breaking Bad” (fallback ao vivo): TDF 5 + Rede 5 resultados

Dica: no PowerShell, use `curl.exe -G --data-urlencode` em vez de montar a URL
com `&` e `%20` na mão, para evitar que o comando seja quebrado.

## Seeds e trackers

Problema encontrado: o scrape usava timeout de 500ms, retornava a primeira
resposta (mesmo 0/0) e cacheava 0/0 por 24h. Isso fazia torrents ativos
aparecerem sem seeds.

Correções em `scrape/info.go` e `scrape/scrape.go`:
- timeout de 3s no conjunto e 1,5s por tracker;
- coleta o máximo de seeds/leechers entre os trackers, em vez da primeira
  resposta;
- apenas trackers UDP são consultados;
- cache `peers:v2:<infohash>` (ignora os valores antigos de 0/0);
- resultados 0/0 ficam em cache por 10 min, não 24h;
- validação da transaction ID do tracker.

Validação:
- Ubuntu <PUBLIC_IP> (torrent oficial, via `/indexers/manual`): **34 seeds, 19
  leechers**.
- House of the Dragon S03: **12–99 seeds** dependendo do episódio.
- Game of Thrones S06E10 e Suits: torrents antigos, 0–2 seeds. Não é falha do
  scrape; o swarm está morto.

Conclusão: o indexer mostra o seed real. Torrents antigos ou sem seed continuam
em 0.

## Filtro de seeds

O parâmetro `min_seeds` foi adicionado ao `/search` e aos endpoints
`/indexers/<nome>`:

```powershell
curl.exe -G --data-urlencode "q=house of the dragon s03" `
  --data-urlencode "min_seeds=1" `
  http://localhost:8080/search
```

Na UI, o checkbox **Only with seeds** vem marcado por padrão. Se nenhum
resultado sobrar, a UI avisa para desmarcar o filtro. Os resultados 0 seed
continuam no índice do Meilisearch; o filtro é aplicado na resposta.

## Temporadas e episódios

O backend extrai `season`, `episode` e `release_type` do título do release
(`api/season.go`). Padrões suportados:
- `S02E05`, `2x05`
- `2ª Temporada`, `Temporada 2`, `Season 2`
- `Episódio 5`, `Ep. 5`
- `Temporada Completa`, `Série Completa`, `Complete Series`

Filtros na API:
- `/search?...&season=3&episode=2&min_seeds=1`
- `/indexers/<nome>?...&season=3&episode=2&min_seeds=1`
- `sortBy=season`, `sortBy=episode`, `sortDirection=asc|desc`

Na UI:
- select **Temporada/Episódio** para ordenar;
- select de temporada (Todas, 1, 2, ...);
- resultados agrupados por temporada, com badge `S03E02`;
- resultados sem temporada vão para **Outros**.

Limitações:
- É best-effort: packs de temporada não têm episódio; títulos fora do padrão
  caem em "Outros"; numeração absoluta de anime pode não ser detectada.
- O `/search` busca uma janela maior de candidatos quando há filtros ativos,
  para não filtrar apenas os primeiros resultados.
- Documentos antigos do Meilisearch são parseados na hora no `/search`; novos
  já são indexados com os campos.

## Configuração necessária

Variáveis principais:

```env
PORT=7006
METRICS_PORT=8081
REDIS_HOST=localhost
REDIS_PASSWORD=
FLARESOLVERR_ADDRESS=http://localhost:8191
REQUEST_TIMEOUT_MILLISECONDS=5000
```

Para comando e bludv, o FlareSolverr precisa estar rodando. Redis é necessário
para cache e para o fluxo normal do indexer.

URLs opcionais por indexer:

```env
INDEXER_BAIXARAPIDO_URL=https://baixarapido.com/
INDEXER_COMANDO_URL=https://comando.la/
INDEXER_BLUDV_URL=https://bludv-v1.xyz/
INDEXER_TORRENT_DOS_FILMES_URL=https://torrentdosfilmes.se/
INDEXER_STARCK_FILMES_URL=https://starckfilmes-v27.com/
INDEXER_REDE_TORRENT_URL=https://redestorrents.com/
INDEXER_VACA_TORRENT_URL=https://vaqueirofilmes.com/
```

Observação: `vaca_torrent` foi descontinuado; o domínio novo é Vaqueiro Filmes
e não expõe magnet links. O endpoint é mantido por compatibilidade.

## Como testar sem esperar demais

Use timeouts curtos e teste um endpoint por vez:

```powershell
curl.exe --max-time 45 "http://localhost:7006/indexers/torrent-dos-filmes?q=matrix"
curl.exe --max-time 45 "http://localhost:7006/indexers/rede_torrent?q=matrix"
curl.exe --max-time 90 "http://localhost:7006/indexers/starck-filmes?q=matrix"
```

Não use `curl` sem `--max-time` contra esses sites: Cloudflare e origens lentas
podem fazer a chamada parecer travada. O servidor em si continua respondendo na
porta configurada.

## Por que uma execução pode parecer travada

- O indexer é um servidor de longa duração. Se ele for iniciado em foreground,
  o terminal fica aberto para sempre esperando requisições; isso é normal.
- Quando um teste inicia o servidor em background dentro do mesmo comando, o
  processo filho pode manter os pipes de saída abertos. O executor pode ficar
  esperando o processo terminar mesmo que os testes já tenham acabado. Por
  isso, prefira rodar o servidor em outro terminal e usar apenas comandos que
  terminam sozinhos para testar.
- Sempre use `--max-time` no `curl` e evite loops sem limite. Um teste demorado
  deve ter um limite explícito.
- A correção do FlareSolverr em background evita o bloqueio no startup, mas não
  muda o comportamento de um comando de teste que fica esperando rede.

### Script de verificação

Há um script que testa um endpoint por vez, com timeout e sem iniciar o
servidor:

```powershell
# Em um terminal: inicie o indexer
go run .

# Em outro terminal: teste os indexers
powershell -ExecutionPolicy Bypass -File scripts/check-indexers.ps1 -TimeoutSeconds 45
```

Para testar só um indexer:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-indexers.ps1 `
  -TimeoutSeconds 45 `
  -Indexers torrent-dos-filmes
```

O script não inicia nem para o servidor, então ele sempre termina sozinho.

## Validação final

- `go test ./...` -> OK
- `go vet ./...` -> OK
- `golangci-lint run --timeout 5m` -> OK
- `docker compose config --quiet` -> OK
- Endpoints testados sem Redis/FlareSolverr:
  - `torrent-dos-filmes`: 19 resultados em 7,1s
  - `rede_torrent`: 39 resultados em 5,5s
  - `starck-filmes`: 6 resultados em 8,5s
- Stack Docker (`docker compose up -d`): indexer, Redis e FlareSolverr no ar;
  pool do FlareSolverr com 5 sessões.
- `comando_torrents` via Docker: **883 resultados** em 17,4s.
- `bludv` via Docker: **0 resultados** em 64,5s (gate de anúncio).
- Seeds: Ubuntu oficial 34/19; House of the Dragon S03 12–99;
  Game of Thrones/Suits 0–2 (torrents antigos).
- Filtro `min_seeds=1`: House of the Dragon S03 só com seeds; Game of Thrones
  S06E10 retornou 2 resultados com seed=1.
- Temporadas/episódios: House of the Dragon S03 retornou `season=3` com
  `episode=1,2,3,5,8`; filtro `season=3` no `/search` retornou os episódios
  corretos com seeds.
- 2026-11-24 (Pi): `baixarapido` implementado e validado com 24 resultados
  para `matrix`; Comando 14–20 resultados; Vaca 0 (descontinuado); Prowlarr com
  10 indexadores; Radarr 11 e Sonarr 9; 1337x, YTS e UIndex associados; proxies
  do FlareSolverr em `solvearr:8191`.
- 2026-10-26 (Pi): `torrent-dos-filmes` 18, `starck-filmes` 5 e `rede_torrent`
  34 resultados para Minions; BluDV 0 (gate); Comando funciona com FlareSolverr
  oficial; Vaca morto; Radarr 7 (com o proxy PT-BR Alternate Titles) e Sonarr 6;
  Minions 162 releases, 6 aceitos (Dual, 6/18 seeds); ver
  [MEDIA_STACK.md](MEDIA_STACK.md) §6.

## Pendências

1. **BluDV**: mantém 0 resultados por causa do gate `promobr/x.gd`; decidir se
   remove da lista pública.
2. **Comando Torrents**: funcionando; a primeira busca em um domínio novo pode
   levar ~80-120s por causa do Cloudflare; acompanhar se o site muda de domínio.
3. **Vaca Torrent**: descontinuado (Vaqueiro Filmes, sem magnets); decidir se
   remove o endpoint/lista pública ou mantém por compatibilidade.
4. **Filme Torrent**: só nome em `IndexerNames`, sem handler/rota; implementar
   ou remover. **Dodo Filmes** não existe no código atual.
5. **1337x**: recuperado com os proxies do Prowlarr em `solvearr:8191`; está no
   Radarr e Sonarr. A primeira busca pode levar ~110s.
6. **Sonarr/Torrent dos Filmes (TV)**: o indexador está no Sonarr (9
   indexadores); validar se retorna TV dublada.
7. **Seeds**: `minimumSeeders=1` no App Profile Standard e nos *arr; o Torrent
   dos Filmes não informa seeders no Radarr (vazio); preferir Torrentio/TPB na
   escolha manual.
8. **Baixarapido**: acompanhar mudanças de layout/busca; parte dos resultados
   fica sem tamanho porque a página não informa.
9. **Torznab**: `api/torznab.go` e `api/baixarapido.go` revisados; docs e código
   commitados em 2026-11-24.
9. **Stack de mídia**: dashboard Filmes, widget do Seerr, sync da biblioteca
   Animes no Jellyfin, `-1s` só no Suits e fila de legendas no navegador; ver
   [MEDIA_STACK.md](MEDIA_STACK.md) §15.
10. Avaliar o TTL de 10 min para resultados 0/0 e a numeração absoluta de
    anime/packs no parser de temporada/episódio.
11. Manter a cópia versionada `deploy/raspberry/docker-compose.yml`
    sincronizada com o compose vivo (atualizada em 2026-10-26).
