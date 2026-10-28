# Setup — do zero ao ambiente rodando

Este guia é o ponto de partida para uma pessoa nova no repositório. Ele cobre
dois caminhos:

- **A. Indexer local** — só o `torrent-indexer` com Redis, Meilisearch e
  FlareSolverr.
- **B. Stack de mídia no Raspberry Pi** — indexer + Homepage + Radarr/Sonarr/
  Prowlarr/Bazarr/Jellyfin/Seerr + agentes de WOL/pedidos.

O código do indexer e o template da stack estão no repositório. Configurações,
bancos, mídia e alguns scripts de agente vivem **fora** do Git (ver
[O que não está no repositório](#o-que-não-está-no-repositório)).

## 1. Pré-requisitos

| Ferramenta | Versão/observação |
|---|---|
| Git | qualquer versão recente |
| Docker Engine | 24+ com Compose v2 (`docker compose`) |
| Go | 1.24 (para desenvolvimento/build local) |
| Node.js + npm | 20+ (somente para editar/compilar o `custom.js` do Homepage) |
| Raspberry Pi | opcional; Pi 4 de 4 GB com SO **64-bit** para o stack completo |
| FlareSolverr | necessário para indexers protegidos por Cloudflare (`comando_torrents`, `bludv`) |

No Windows, use PowerShell 7 ou superior para os comandos com `curl.exe`.

## 2. Caminho A — indexer local com Docker

```bash
git clone https://github.com/felipemarinho97/torrent-indexer.git
cd torrent-indexer
cp .env.example .env
```

Gere uma chave forte e coloque em `MEILI_MASTER_KEY` no `.env`:

```bash
openssl rand -base64 32
```

No PowerShell:

```powershell
# alternativa sem openssl
[Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Max 256 }))
```

Suba a stack:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f torrent-indexer
```

Valide:

```bash
curl -s http://localhost:8080/ | head -c 300
curl -s http://localhost:8080/search/health
```

Abra a UI em <http://localhost:8080/ui/>.

> O `docker-compose.yml` da raiz é intencionalmente simples: Redis e
> Meilisearch não têm volumes persistentes. Para produção, use o template do
> Raspberry Pi, que tem volumes e limites de memória.

## 3. Desenvolvimento sem Docker

Suba as dependências:

```bash
docker compose up -d redis meilisearch flaresolverr
```

Exporte as variáveis (ou use um `.env` carregado pelo seu shell) apontando para
`localhost`:

```bash
export REDIS_HOST=localhost
export MEILISEARCH_ADDRESS=http://localhost:7700
export MEILISEARCH_KEY="<sua-chave>"
export FLARESOLVERR_ADDRESS=http://localhost:8191
```

Rode o indexer:

```bash
go run .
```

Testes e qualidade:

```bash
go test ./...
go vet ./...
go run github.com/golangci/golangci-lint/cmd/golangci-lint@latest run --timeout 5m
docker compose config --quiet
```

Teste um indexer:

```bash
curl -G --data-urlencode "q=house of the dragon s03" \
  --data-urlencode "min_seeds=1" \
  --max-time 90 \
  http://localhost:8080/indexers/torrent-dos-filmes
```

No PowerShell:

```powershell
curl.exe -G --data-urlencode "q=house of the dragon s03" `
  --data-urlencode "min_seeds=1" `
  --max-time 90 `
  http://localhost:8080/indexers/torrent-dos-filmes
```

## 4. Caminho B — stack completa no Raspberry Pi

O template versionado fica em [`deploy/raspberry/`](deploy/raspberry/):
`docker-compose.yml`, `.env.example` e `media-stack.service`.

### 4.1 Sistema e Docker

1. Grave Raspberry Pi OS 64-bit (Bookworm+) ou Ubuntu Server 24.04 arm64.
2. Configure usuário, SSH e rede.
3. Instale Docker e Compose:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
newgrp docker
docker version
docker compose version
```

> Use SO **64-bit**. O Meilisearch não publica imagem `arm/v7`; em 32-bit a
> busca e a UI não funcionam.

### 4.2 Layout esperado

O compose do Pi usa um diretório de trabalho com o binário do indexer ao lado:

```text
<STACK_ROOT>/
  docker-compose.yml
  .env
  torrent-indexer/
    torrent-indexer-linux-arm64
```

Copie o template e o binário:

```bash
mkdir -p <STACK_ROOT>/torrent-indexer
cp deploy/raspberry/docker-compose.yml <STACK_ROOT>/
cp deploy/raspberry/.env.example <STACK_ROOT>/.env
# copie o binário arm64 para <STACK_ROOT>/torrent-indexer/
```

Build do binário no PC (recomendado) ou no Pi:

```bash
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -o torrent-indexer-linux-arm64 .
```

### 4.3 Variáveis do `.env`

Edite `<STACK_ROOT>/.env` (nunca commite). Principais variáveis:

| Variável | Uso |
|---|---|
| `TZ` | fuso horário dos containers (ex.: `America/Sao_Paulo`) |
| `PUID` / `PGID` | UID/GID do usuário que roda os containers |
| `MEDIA_ROOT` | raiz da mídia, montada como `/media` |
| `CONFIG_ROOT` | raiz das configs persistentes dos serviços |
| `MEILI_MASTER_KEY` | mesma chave do indexer e do Meilisearch |
| `LAN_IP` | IP da LAN usado para publicar portas de gestão |
| `TAILSCALE_IP` | IP Tailscale do host (acesso remoto) |
| `ALLOWED_NETWORKS` | LAN, Tailscale, loopback e IPv6 do Tailscale |
| `PC_IP` | IPs do PC para ping/WOL (Tailscale e LAN) |
| `PC_MAC` | MAC do PC para o magic packet |
| `LAN_BROADCAST` | broadcast da LAN para WOL |
| `GAMING_PASSWORD` | senha do WOL no modo remoto |

Gere `MEILI_MASTER_KEY` e `GAMING_PASSWORD` com valores fortes e diferentes.

### 4.4 O que precisa existir fora do repositório

O template do compose referencia arquivos que **não** são versionados:

- `${CONFIG_ROOT}/gaming-agent/agent.py`
- `${CONFIG_ROOT}/media-gateway/gateway.py`
- `${CONFIG_ROOT}/homepage/{settings,services,widgets,bookmarks}.yaml` e
  `custom.js`
- configs e bancos de Radarr, Sonarr, Prowlarr, Bazarr, Jellyfin, Seerr e
  qBittorrent
- chaves de API locais (`.env`, `.bazarr_key`, `config.xml`, `settings.json`)

O `media_agent.py` é versionado em `deploy/raspberry/media-agent/`; copie-o
para `${CONFIG_ROOT}/media-agent/` antes de subir o stack.

Esses itens são específicos da instalação. Para entender cada serviço, portas,
perfis e integrações, veja [MEDIA_STACK.md](MEDIA_STACK.md).

### 4.5 Subir e verificar

```bash
cd <STACK_ROOT>
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Verificações mínimas:

```bash
curl -s http://localhost:8080/ | head -c 300
curl -s http://localhost:8080/search/health
curl -s "http://localhost:8097/requests?view=history&pageSize=1"
curl -s http://localhost:8098/gaming/status
```

Portas típicas (quando o stack completo está configurado):

| Serviço | Porta |
|---|---|
| torrent-indexer | `8080` |
| métricas | `<LAN_IP>:8081` |
| Homepage | `3000` |
| Jellyfin | `8096` |
| Seerr | `5055` |
| Radarr | `<LAN_IP>:7878` |
| Sonarr | `<LAN_IP>:8989` |
| Prowlarr | `<LAN_IP>:9696` |
| Bazarr | `<LAN_IP>:6767` |
| qBittorrent | `<LAN_IP>:8082` |
| media-agent | `8097` |
| gaming-agent (público) | `8098` |
| gaming-agent (privado) | `<LAN_IP>:8099` |

### 4.6 Atualizar e reverter

Atualize o binário e recrie só o indexer:

```bash
# no PC
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -o torrent-indexer-linux-arm64 .
scp torrent-indexer-linux-arm64 <pi>:<STACK_ROOT>/torrent-indexer/
ssh <pi> 'cd <STACK_ROOT> && docker compose up -d --build torrent-indexer'
```

Guarde o binário anterior como `torrent-indexer-linux-arm64.bak.<timestamp>`.
Para reverter, copie o `.bak` de volta e rode o mesmo `docker compose up -d
--build torrent-indexer`.

O `media-stack.service` é um exemplo de unit systemd para subir o compose no
boot; ajuste `WorkingDirectory` ao caminho real.

## 5. Homepage (`custom.js`)

O Homepage só serve `custom.js` e `custom.css`; não é possível separar o painel
em vários arquivos em runtime. A fonte fica no repositório e o build gera um
único IIFE clássico.

```bash
cd deploy/homepage
npm install
npm run build
npm run check
```

O artefato é `dist/custom.js`. Para publicar:

```bash
ssh <pi> 'cp -p <MEDIA_ROOT>/docker/homepage/custom.js \
  <MEDIA_ROOT>/docker/homepage/custom.js.bak.$(date +%Y%m%d-%H%M%S)'
scp dist/custom.js <pi>:<MEDIA_ROOT>/docker/homepage/custom.js
```

Faça hard refresh no navegador. **Não edite o `custom.js` do Pi à mão.**

Detalhes da estrutura e do fluxo de paridade estão em
[`deploy/homepage/README.md`](deploy/homepage/README.md).

## 6. Segurança e segredos

- `.env`, `.env.*` (exceto `.env.example`), `.gaming_password`, `.bazarr_key`,
  `requests.db`, `state/` e `*.local.md` são ignorados pelo Git.
- O `.env` vivo deve ficar com permissão `600`.
- A senha do WOL vem de `GAMING_PASSWORD` no `.env`; `.gaming_password` é apenas
  fallback legado. Para trocar, edite o `.env` e recrie o container.
- Chaves de API dos *arr/Bazarr/Seerr ficam nos configs do servidor e no
  `.bazarr_key`; não coloque segredos no `custom.js`.
- Os runbooks `*.local.md` contêm IPs/caminhos reais e **não** devem ser
  commitados.

Leia [SECURITY_AUDIT.md](SECURITY_AUDIT.md) antes de expor qualquer porta fora
da LAN/Tailscale.

## 7. Checklist pós-instalação

- [ ] `docker compose ps` sem containers em restart.
- [ ] `GET /` e `GET /search/health` respondem 200.
- [ ] `/ui/` abre e a busca retorna resultados.
- [ ] Meilisearch com volume persistente (stack do Pi).
- [ ] Homepage abre em `:3000` e as abas **Início**, **Pedidos** e **Legendas**
      carregam sem erro no console.
- [ ] `media-agent` responde em `:8097` e o WOL responde em `:8098/gaming/status`
      (não dispare `/wake` sem querer).
- [ ] `custom.js` publicado é o artefato de `deploy/homepage/dist/custom.js`.
- [ ] `.env` e arquivos de chave com permissão restrita.

## 8. Troubleshooting

| Sintoma | Causa provável / ação |
|---|---|
| `/search` ou `/ui/` vazios | Meilisearch indisponível, chave errada ou SO 32-bit no Pi |
| `422 Unsupported file` em `/api/config/*.js` | O Homepage só serve os arquivos suportados; use o bundle `custom.js` |
| `custom.js` antigo no navegador | Hard refresh/limpar cache; confira o hash do arquivo servido |
| Cloudflare/403 em indexers | FlareSolverr fora do ar ou timeout baixo (`FLARESOLVERR_TIMEOUT_SECONDS`) |
| `media-agent` retorna 403 | IP fora de `ALLOWED_NETWORKS` |
| WOL retorna 401/403 | `GAMING_PASSWORD` ausente/incorreta ou arquivo legado divergente |
| Homepage não abre por IP/Tailscale | `HOMEPAGE_ALLOWED_HOSTS` restritivo |
| Container reiniciando por falta de variável | O compose usa `${VAR:?}`; preencha o `.env` |
| Porta ocupada | Ajuste as portas publicadas ou pare o serviço conflitante |

## 9. O que não está no repositório

Para evitar expectativa errada: o repositório **não** contém mídia, bancos dos
*arr, configurações do Homepage, os scripts vivos de `media-agent`,
`gaming-agent` e `media-gateway`, nem segredos. O template do Pi mostra como
esses serviços se encaixam, mas cada instalação mantém seus próprios arquivos em
`${CONFIG_ROOT}`/`${MEDIA_ROOT}`.

## 10. Onde continuar

- [README.md](README.md) — visão geral e configuração do indexer.
- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) — arquitetura e endpoints.
- [MEDIA_STACK.md](MEDIA_STACK.md) — stack de mídia, portas, perfis e agentes.
- [RASPBERRY_PI.md](RASPBERRY_PI.md) — detalhes de migração e operação no Pi.
- [deploy/homepage/README.md](deploy/homepage/README.md) — build do painel.
- [UI_AUDIT.md](UI_AUDIT.md) — plano e histórico das etapas de UI.
- [SECURITY_AUDIT.md](SECURITY_AUDIT.md) — auditoria e rotação de segredos.
