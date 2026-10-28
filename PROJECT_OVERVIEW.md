# Torrent Indexer — Visão geral do projeto

> **Nota de segurança:** IPs, MACs, usuários e caminhos absolutos foram substituídos por placeholders. Os valores reais ficam no `.env`/config local, fora do git. A senha do WOL agora usa `GAMING_PASSWORD` no `.env`; `.gaming_password` é fallback legado. Veja `SECURITY_AUDIT.md`.

Última atualização: 2026-10-26

Documentos relacionados:

- [SITE_STATUS.md](SITE_STATUS.md) — status detalhado de cada site, testes e correções.
- [RASPBERRY_PI.md](RASPBERRY_PI.md) — o que muda para rodar no Raspberry Pi 4.
- [MEDIA_STACK.md](MEDIA_STACK.md) — stack de mídia do Pi (Jellyfin, Bazarr, Radarr, Sonarr, Prowlarr, Seerr, Homepage, gaming-agent, media-agent, media-gateway), perfis, legendas e pendências.

## 1. O que é

Indexador de torrents escrito em Go. Ele consulta sites públicos de torrent,
extrai os magnets e metadados das páginas HTML, consulta trackers para obter
seeds/leechers e expõe os resultados em:

- API JSON por indexer;
- busca agregada via Meilisearch;
- UI web;
- Torznab (para Prowlarr/Jackett).

O projeto foi feito para autohospedagem. A instância pública do autor não é
garantida e pode bloquear uso intenso.

## 2. Estado atual

O ambiente local está rodando via Docker Compose:

- `torrent-indexer` na porta `8080` (mapeada para `7006` no container);
- Redis;
- FlareSolverr (usado para sites com Cloudflare);
- Meilisearch (usado por `/search` e `/ui/`).

Indexers validados:

| Indexer | Estado |
|---|---|
| `comando_torrents` | Funciona com FlareSolverr |
| `torrent-dos-filmes` | Funciona; magnets diretos e fallback `systemads` |
| `rede_torrent` | Funciona no domínio novo `redestorrents.com` |
| `starck-filmes` | Funciona em `starckfilmes-v27.com`; resolvedor de `filmedl.com` |
| `bludv` | Páginas abrem, mas downloads estão atrás de gate de anúncio |
| `vaca_torrent` | Domínio não serve mais o site antigo; retorna erro explícito |

Funcionalidades adicionadas recentemente:

- Filtro padrão de seeds (`min_seeds`) e checkbox na UI;
- Campos `season`, `episode`, `release_type`;
- Agrupamento por temporada e badge `S03E02` na UI;
- Ordenação por seeds, data, título e temporada/episódio;
- Fallback ao vivo na UI quando o cache do Meilisearch está vazio;
- Scrape de trackers com timeout maior, máximo entre trackers e cache de
  resultados 0/0 por apenas 10 minutos.

O stack completo de mídia no Pi (Radarr, Seerr, Jellyfin, Bazarr, Homepage,
gaming-agent, perfis e legendas) está em [MEDIA_STACK.md](MEDIA_STACK.md).

Estado dos indexadores no Pi em 2026-10-26: `rede_torrent`,
`torrent-dos-filmes`, `starck-filmes` e `comando_torrents` funcionam; `bludv`
retorna 0 (gate `promobr/x.gd`); `vaca_torrent` está morto; `filme_torrent`
existe apenas como nome em `IndexerNames` (sem handler); `dodo` não existe no
código. Detalhes em [MEDIA_STACK.md](MEDIA_STACK.md) §4.

## 3. Arquitetura

Fluxo resumido:

```text
Cliente (UI, Prowlarr, curl)
  -> HTTP server (main.go)
     -> /indexers/<site>
        -> handler do site
        -> requester (cache Redis / FlareSolverr / HTTP)
        -> goquery (HTML)
        -> magnet.ParseMagnetUri
        -> scrape.GetLeechsAndSeeds (trackers UDP)
        -> post-processors (similaridade, metadados, temporada, filtros, sort)
        -> resposta JSON + envio para Meilisearch
     -> /search
        -> Meilisearch (índice "torrents")
     -> /ui/
        -> HTML/JS embutido (public/index.html)
```

Componentes principais:

| Pacote | Responsabilidade |
|---|---|
| `main.go` | Sobe servidor HTTP, métricas, cache, FlareSolverr e Meilisearch |
| `api/` | Handlers dos sites, Torznab, busca, pós-processadores, parser de temporada |
| `requester/` | HTTP client, cache curta, integração com FlareSolverr |
| `scrape/` | Scrape de trackers UDP (seeds/leechers) |
| `magnet/` | Parse de magnet e infohash |
| `cache/` | Cliente Redis |
| `search/` | Cliente Meilisearch |
| `schema/` | Structs de dados |
| `public/` | UI web embutida |
| `monitoring/` | Métricas Prometheus |
| `logging/` | Logs e middleware |

## 4. Estrutura do repositório

```text
api/                 Handlers HTTP e regras de cada site
cache/               Redis
consts/              Versão/build
deploy/homepage/     Fonte modular + build do custom.js do Homepage
deploy/raspberry/    Template do stack completo no Pi (compose, env, systemd)
logging/             Logs
magnet/              Magnet/infohash
monitoring/          Prometheus
public/              UI (index.html embutido)
requester/           HTTP, cache curta, FlareSolverr
schema/              Structs
scrape/              Trackers UDP
scripts/             Scripts de verificação
search/              Meilisearch
utils/               Utilidades
main.go              Entrada da aplicação
docker-compose.yml   Stack local do indexer
Dockerfile           Build da imagem
SETUP.md             Guia de instalação para uma pessoa nova
PROJECT_OVERVIEW.md  Arquitetura, endpoints e configuração
MEDIA_STACK.md       Stack de mídia no Pi
SITE_STATUS.md       Status dos sites e testes
RASPBERRY_PI.md      Migração/operação no Raspberry Pi
UI_AUDIT.md          Plano e status das etapas de UI
SECURITY_AUDIT.md    Auditoria e rotação de segredos
```

## 5. Endpoints

| Método | Caminho | Descrição |
|---|---|---|
| GET | `/` | JSON com endpoints, build e nomes dos indexers |
| GET | `/indexers/{site}` | Busca ao vivo em um site |
| GET | `/indexers/manual` | Lista torrents manuais |
| POST | `/indexers/manual` | Adiciona magnet manual por 8h |
| GET | `/search` | Busca no cache do Meilisearch |
| GET | `/search/health` | Saúde do Meilisearch |
| GET | `/search/stats` | Estatísticas do índice |
| GET | `/ui/` | Interface web |
| GET | `/api` e `/api/` | API Torznab (Prowlarr/Jackett) |
| GET | `/metrics` | Métricas Prometheus (porta separada) |

No Torznab, `t=caps` retorna as capacidades; `t=search&q=...` busca. O indexer
padrão é `rede_torrent`; use `indexer=<nome>` para escolher outro.

## 6. Parâmetros de query

| Parâmetro | Descrição |
|---|---|
| `q` | Texto da busca |
| `page` | Página (quando o site suporta) |
| `filter_results` | Remove resultados com similaridade zero |
| `limit` | Limite de resultados |
| `sortBy` | `title`, `original_title`, `year`, `season`, `episode`, `date`, `seed_count`, `leech_count`, `size`, `similarity` |
| `sortDirection` | `asc` ou `desc` |
| `audio` | Filtro de áudio (`por,eng,brazilian`) |
| `year` | Filtro por ano |
| `imdb` | Filtro por ID IMDb |
| `min_seeds` | Remove resultados com menos que N seeds |
| `season` | Filtro por temporada |
| `episode` | Filtro por episódio |

Exemplo:

```powershell
curl.exe -G --data-urlencode "q=house of the dragon" `
  --data-urlencode "min_seeds=1" `
  --data-urlencode "season=3" `
  --data-urlencode "sortBy=episode" `
  --data-urlencode "sortDirection=asc" `
  http://localhost:8080/search
```

## 7. Configuração

Variáveis principais:

| Variável | Padrão | Observação |
|---|---|---|
| `PORT` | `7006` | Porta do HTTP server |
| `METRICS_PORT` | `8081` | Porta das métricas |
| `LOG_LEVEL` | `1` | `0` debug, `1` info, `2` warn, `3` error |
| `LOG_FORMAT` | console | `json` para logs JSON |
| `REDIS_HOST` | `localhost` | Host do Redis |
| `REDIS_PASSWORD` | vazio | Senha do Redis |
| `FLARESOLVERR_ADDRESS` | vazio | Necessário para comando/bludv |
| `FLARESOLVERR_TIMEOUT_SECONDS` | `30` | Timeout de requests |
| `FLARESOLVERR_POOL_SIZE` | `5` | Sessões no pool |
| `REQUEST_TIMEOUT_MILLISECONDS` | `5000` | Timeout dos requests HTTP |
| `MEILISEARCH_ADDRESS` | vazio | Necessário para `/search` e `/ui/` |
| `MEILISEARCH_KEY` | vazio | Chave do Meilisearch |
| `SHORT_LIVED_CACHE_EXPIRATION` | `30m` | Cache de páginas de busca |
| `LONG_LIVED_CACHE_EXPIRATION` | `7d` | Cache de páginas de detalhe |
| `FALLBACK_TITLE_ENABLED` | `false` | Usa título da página se vazio |
| `MAGNET_METADATA_API_ENABLED` | `false` | API externa de metadados |
| `INDEXER_<NOME>_URL` | padrão do código | URL customizada por indexer |

## 8. Docker

Serviços do `docker-compose.yml`:

| Serviço | Imagem | Porta |
|---|---|---|
| `torrent-indexer` | build local | `8080:7006` |
| `redis` | `redis:alpine` | interna `6379` |
| `flaresolverr` | `ghcr.io/flaresolverr/flaresolverr:latest` | interna `8191` |
| `meilisearch` | `getmeili/meilisearch:latest` | interna `7700` |

Comandos:

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f torrent-indexer
docker compose down
```

Atualmente o compose **não tem volumes persistentes** para Redis e
Meilisearch. O índice do Meilisearch é perdido se o container for recriado. Para
produção/Raspberry Pi, veja as recomendações em [RASPBERRY_PI.md](RASPBERRY_PI.md).

## 9. Cache, busca e UI

- Redis guarda cache de páginas, cache curto, lista de trackers e peers.
- Meilisearch guarda o índice `torrents`, com ID = `info_hash`.
- `/search` só pesquisa o que já foi indexado.
- A UI tem fallback ao vivo: se o cache retornar 0, consulta
  `torrent-dos-filmes`, `rede_torrent`, `starck-filmes` e `comando_torrents`.
- A UI tem checkbox **Only with seeds** marcado por padrão.
- A UI agrupa por temporada e ordena por seeds por padrão.
- Documentos antigos do Meilisearch são parseados na hora para temporada.

## 10. Seeds e trackers

O scrape usa apenas trackers UDP. Para cada infohash:

- consulta o cache `peers:v2:<infohash>`;
- em caso de miss, consulta até 50 trackers UDP em paralelo;
- timeout de 3s no conjunto, 1,5s por tracker;
- usa o **máximo** de seeds/leechers entre os trackers;
- cacheia resultados positivos por 24h;
- cacheia 0/0 por 10 min para não “envenenar” o cache.

Validação: torrent oficial do Ubuntu retornou 34 seeds/19 leechers; House of the
Dragon S03 retornou 12–99 seeds. Torrents antigos podem continuar em 0 porque o
swarm está morto.

## 11. Temporadas e episódios

O parser em `api/season.go` preenche `season`, `episode` e `release_type`.
Padrões: `S02E05`, `2x05`, `2ª Temporada`, `Temporada 2`, `Season 2`,
`Episódio 5`, `Temporada Completa`, `Série Completa`.

Limitações:

- packs de temporada não têm episódio;
- títulos fora do padrão caem em “Outros”;
- numeração absoluta de anime ainda não é detectada;
- a UI agrupa no cliente; o backend também aceita `season`/`episode`.

## 12. Como rodar e testar

Para instalação do zero (Docker, Pi, segredos e Homepage), siga
[SETUP.md](SETUP.md). Resumo de desenvolvimento:

Desenvolvimento:

```bash
go run .
```

Build:

```bash
go build ./...
```

Testes e qualidade:

```bash
go test ./...
go vet ./...
go run github.com/golangci/golangci-lint/cmd/golangci-lint@latest run --timeout 5m
docker compose config --quiet
```

Verificação de um endpoint:

```powershell
curl.exe -G --data-urlencode "q=house of the dragon s03" `
  --data-urlencode "min_seeds=1" `
  --max-time 90 `
  http://localhost:8080/indexers/torrent-dos-filmes
```

Script de verificação no Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-indexers.ps1 -TimeoutSeconds 45
```

Dica: no PowerShell, use `curl.exe -G --data-urlencode` para não quebrar URLs
com `&` e `%20`.

## 13. Limitações e problemas conhecidos

- `bludv`: downloads usam gate de anúncio (`gate/go` → `promobr.online` →
  `x.gd`). Não há magnet automático; considerado indisponível.
- `vaca_torrent`: domínio redireciona para `vaqueirofilmes1.com`; sem correção
  sem um novo domínio.
- Cloudflare pode bloquear por IP/rate limit; o FlareSolverr ajuda, mas não é
  garantia.
- Seeds refletem o swarm real; torrents antigos podem ter 0.
- Parser de temporada é best-effort.
- Sem volumes persistentes no compose atual.
- Scripts de verificação são PowerShell; no Linux/Raspberry Pi precisam de
  equivalente em bash.
- A instância pública do autor pode bloquear Prowlarr/Jackett; prefira
  autohospedar.
- Stack de mídia no Pi: ver [MEDIA_STACK.md](MEDIA_STACK.md) — BluDV 0,
  Vaca morto, `filme_torrent` sem handler, 1337x dependente do FlareSolverr,
  seeders vazios no Torrent dos Filmes. Radarr tem 7 indexadores (6 do Prowlarr
  + o proxy **PT-BR Alternate Titles**) e o Sonarr tem 6.
- Títulos alternativos: o Radarr não usa os `alternateTitles` do TMDB na busca.
  O proxy Torznab no container **media-gateway** lê `MovieTranslations` pt-BR
  do banco do Radarr, busca no Prowlarr e injeta o IMDb; o release PT-BR do Jack
  apareceu aceito com score 100.
- Exposição pelo Tailscale: Jellyfin 8096, Seerr 5055, torrent-indexer 8080,
  Homepage 3000, Stremio 11470, **gaming 8098** (status/WOL com senha) e
  **media-agent 8097** (Pedidos/Legendas). Radarr/Sonarr/Prowlarr/Bazarr/
  qBittorrent/métricas e o **8099 privado** do gaming-agent ficam presos ao IP
  `<LAN_IP>` (LAN). O Homepage detecta o host: no modo remoto esconde os
  cards de gestão, mas mantém PC Casa e as abas Pedidos/Legendas.
- O WOL fica no card **PC Casa**: no modo local usa o 8099 sem senha; no modo
  remoto usa o 8098 e pede a senha definida em `GAMING_PASSWORD` no `.env`
  (`.gaming_password` é fallback legado).
- Jellyfin: o realtime não funciona no mount FUSE/NTFS-3G; o scan agendado roda
  a cada 30 min e o hook **Jellyfin Refresh** no Radarr/Sonarr atualiza o item
  na hora após import/upgrade/rename.
- Perfis dublados (Radarr `Animação - Dublado` e Sonarr `Séries - Dublado`)
  exigem PT-BR desde 2026-10-26 (mínimo 100) e rejeitam `Latino/Espanhol`.
  O Homepage tem abas no topo **Início**, **Pedidos** e **Legendas**; a aba
  Pedidos cruza os perfis dublados com os pedidos do Seerr (pendente,
  aprovado, recusado ou falhou), verifica releases PT-BR e permite trocar para
  o perfil Original e buscar quando não houver. Também busca séries/animes no
  Sonarr, adiciona com o perfil escolhido sem monitorar tudo e permite marcar e
  buscar episódios específicos. O `custom.js` é buildado a partir de
  `deploy/homepage/src` (ver [deploy/homepage/README.md](deploy/homepage/README.md)).

## 14. Alterações recentes no working tree

O repositório tem alterações não commitadas. Antes de continuar em outra
conversa, rode:

```bash
git status --short
git diff --stat
```

Arquivos importantes alterados/adicionados nesta etapa:

- `api/season.go` e `api/season_test.go` (novos);
- `api/starck_download.go` (novo);
- `scrape/info.go`, `scrape/scrape.go`;
- `api/post_processors.go`, `api/search.go`, `api/index.go`;
- `schema/indexed_torrent.go`;
- `public/index.html`;
- `docker-compose.yml`;
- `api/torznab.go` — `<category>` 2000/5000, atributo `category` e fallback
  `q=a` para o teste de sync do Prowlarr;
- `requester/flaresolverr.go` — opção `FLARESOLVERR_USE_SESSIONS` e suporte a
  requests sessionless;
- `api/comando_torrents.go` — ignora a página “listão” (centenas de magnets)
  para não travar a resposta;
- `deploy/raspberry/docker-compose.yml` — FlareSolverr oficial, 1024 MB,
  `shm_size: 1gb`, timeout 180s, modo de sessão, `media-gateway` e bindings de
  gestão no IP `<LAN_IP>`;
- `SITE_STATUS.md`, `PROJECT_OVERVIEW.md`, `RASPBERRY_PI.md`;
- `MEDIA_STACK.md` (novo) — stack de mídia, perfis, legendas e pendências;
- `deploy/homepage/` — fonte modular, `package.json`, build esbuild e README;
- `SETUP.md` — guia de instalação para uma pessoa nova;
- `UI_AUDIT.md` e `SECURITY_AUDIT.md` — plano/status da UI e auditoria de
  segurança.

No Pi, também foram atualizados (fora do Git): `gaming-agent/agent.py` (só
WOL/status, 8099 privada/8098 pública), `media-agent/media_agent.py` (Pedidos e
Legendas: `/arr/*`, `/sonarr/*`, `/bazarr`, quota, porta 8097),
`media-gateway/gateway.py` (proxy Torznab), `.bazarr_key`, `GAMING_PASSWORD` no
`.env` e o `custom.js` do Homepage (modo local/remoto, sem segredos). O fonte do
`custom.js` está em `deploy/homepage/src` e o artefato é gerado com esbuild.

O compose vivo do Pi em `<STACK_ROOT>/docker-compose.yml` ganhou
`radarr`, `seerr`, `homepage`, `gaming-agent`, `media-agent` e `media-gateway`;
a cópia versionada em `deploy/raspberry/docker-compose.yml` é mantida em
sincronia.

Também existem binários não rastreados na raiz (`torrent-indexer.exe`,
`torrent-indexer-linux-arm64` e `torrent-indexer-linux-arm64-new`). O binário
`linux-arm64-new` é o build ARM64 desta etapa (categorias/fallback); o
`linux-arm64` da raiz pode estar desatualizado. O binário do Pi em
`<STACK_ROOT>/torrent-indexer/` foi atualizado e o antigo está em
`.bak.*`.

## 15. Próximos passos recomendados

1. Decidir o destino do `bludv` (manter indisponível, remover da lista ou
   implementar o fluxo do gate).
2. Decidir o destino do `vaca_torrent`.
3. Adicionar volumes persistentes para Redis e Meilisearch.
4. Criar `scripts/check-indexers.sh` para Linux/Raspberry Pi.
5. Revisar o diff e commitar as correções.
6. Para Raspberry Pi, seguir [RASPBERRY_PI.md](RASPBERRY_PI.md).
7. Opcional: reverse proxy/HTTPS, autenticação, backup do índice e monitoramento.
8. Implementar a seção **Filmes** no painel de legendas do dashboard (Bazarr
   `/api/movies`, wanted, quota/fila).
9. Seerr: adicionar o widget no Homepage com a API key e sincronizar a
   biblioteca **Animes** no Jellyfin (Settings → Jellyfin → Sync Libraries).
10. Sonarr: já está com 6 indexadores (Comando, Torrent dos Filmes, Starck,
    Rede, TPB, Torrentio); validar TV dublada e avaliar o 1337x/FlareSolverr.
11. Revisar `api/torznab.go`, `MEDIA_STACK.md` e os docs e commitar.
12. Atualizar a cópia versionada `deploy/raspberry/docker-compose.yml` se o
    compose vivo divergir.
13. Proxy de títulos alternativos: implementado no **media-gateway**; o Jack
    PT-BR já aparece aceito (score 100), download pendente. Para séries, o
    Sonarr não guarda traduções no banco; avaliar TVDB/API para o mesmo fluxo.
14. Acesso: Homepage em modo local/remoto, portas de gestão presas à LAN e
    segredos do Bazarr fora do `custom.js`. Revisar se o Stremio/Homepage devem
    continuar expostos no Tailscale.

## 16. Stack de mídia no Pi

O detalhamento do stack de mídia (Jellyfin, Bazarr, Radarr, Sonarr, Prowlarr,
Seerr, Homepage, gaming-agent, media-agent, media-gateway), caminhos, perfis, legendas,
quota e pendências está em [MEDIA_STACK.md](MEDIA_STACK.md). A fonte do painel
do Homepage fica em `deploy/homepage/src`; o build e o deploy estão em
[deploy/homepage/README.md](deploy/homepage/README.md).


