# Migração para Raspberry Pi 4 (4 GB)

> **Nota de segurança:** IPs, MACs, usuários e caminhos absolutos foram substituídos por placeholders. Os valores reais ficam no `.env`/config local, fora do git. A senha do WOL agora usa `GAMING_PASSWORD` no `.env`; `.gaming_password` é fallback legado. Veja `SECURITY_AUDIT.md`.

Última atualização: 2026-10-26

Este documento lista o que precisa mudar para rodar o Torrent Indexer em um
Raspberry Pi 4 de 4 GB. Para o panorama geral do projeto, veja
[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md). Para o status dos sites, veja
[SITE_STATUS.md](SITE_STATUS.md). Para o stack de mídia (Jellyfin, Bazarr,
Radarr, Sonarr, Seerr, Homepage e automações), veja
[MEDIA_STACK.md](MEDIA_STACK.md).

## 1. Resumo

O Raspberry Pi 4 de 4 GB consegue rodar a stack completa, com ajustes de
memória:

- `torrent-indexer`
- Redis
- FlareSolverr
- Meilisearch

O ponto mais importante: **use sistema operacional 64-bit (`arm64`)**. O
Meilisearch não publica imagem `arm/v7`, então em um sistema 32-bit o `/search`
e a UI não vão funcionar.

## 2. Compatibilidade das imagens

| Componente | Arquiteturas publicadas |
|---|---|
| `torrent-indexer` (build local) | build para `arm64` no Pi ou via buildx |
| `flaresolverr` | `linux/arm/v7`, `linux/arm64`, `linux/amd64` |
| `meilisearch` | `linux/arm64`, `linux/amd64` (sem `arm/v7`) |
| `redis:alpine` | `linux/arm/v6`, `linux/arm/v7`, `linux/arm64` |

SO recomendado:

- Raspberry Pi OS 64-bit (Bookworm ou mais recente); ou
- Ubuntu Server 24.04 LTS arm64.

Evite Raspberry Pi OS 32-bit se quiser usar Meilisearch/UI.

## 3. O que precisa mudar no projeto

### 3.1 Volumes persistentes

O `docker-compose.yml` atual não tem volumes. Sem isso:

- o índice do Meilisearch é perdido quando o container é recriado;
- o cache do Redis e a lista de torrents manuais também são perdidos.

Adicione ao `docker-compose.yml`:

```yaml
services:
  redis:
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redis-data:/data

  meilisearch:
    volumes:
      - meili-data:/meili_data

volumes:
  redis-data:
  meili-data:
```

Observações:

- O caminho de dados do Meilisearch é `/meili_data`.
- O caminho de dados do Redis é `/data`.
- O cache do Redis é reconstruível, mas `manual:torrents` e contadores de peers
  são perdidos sem volume.
- O volume do Meilisearch é o mais importante: sem ele, toda a busca agregada
  recomeça vazia.

### 3.2 Build `arm64`

O Dockerfile usa `golang:1.24` + `alpine:latest`, que têm imagens multi-arch.
Existem duas opções.

Atenção: a imagem buildada no Windows/PC é `amd64` e não roda no Pi. O binário
`torrent-indexer-linux-arm64` que está na raiz do repositório pode estar
desatualizado em relação às correções; prefira buildar novamente.

#### Opção A — build no próprio Raspberry Pi

```bash
git clone https://github.com/felipemarinho97/torrent-indexer.git
cd torrent-indexer
docker compose build
docker compose up -d
```

Pode levar de 10 a 30 minutos no Pi 4, dependendo do cartão/SSD e da internet.
Use SSD ou pendrive USB 3.0, não cartão SD lento.

#### Opção B — build no PC com buildx (recomendado)

No PC com Docker:

```bash
docker buildx create --name pi-builder --use
docker buildx build --platform linux/arm64 \
  -t felipemarinho97/torrent-indexer:latest --load .

docker save felipemarinho97/torrent-indexer:latest | gzip > torrent-indexer-arm64.tar.gz
scp torrent-indexer-arm64.tar.gz pi@IP_DO_PI:/tmp/
```

No Raspberry Pi:

```bash
gunzip -c /tmp/torrent-indexer-arm64.tar.gz | docker load
cd torrent-indexer
docker compose up -d --no-build
```

Use `--no-build` para evitar que o Compose tente rebuildar a imagem no Pi.

Também é possível publicar a imagem em um registry e usar `docker compose pull`
no Pi.

### 3.3 FlareSolverr com menos memória

O serviço `solvearr` usa a imagem oficial
`ghcr.io/flaresolverr/flaresolverr:latest` (3.5.0), com `mem_limit: 1024m`,
`shm_size: 1gb`, `FLARESOLVERR_POOL_SIZE=2`,
`FLARESOLVERR_TIMEOUT_SECONDS=180` e `FLARESOLVERR_USE_SESSIONS=true`. A
primeira busca em um domínio novo pode levar ~80-120s para resolver o
Cloudflare; depois a sessão/cache deixam rápido.

Sem o FlareSolverr, `comando_torrents` e `bludv` ficam indisponíveis. Mesmo com
ele, o `bludv` continua atrás do gate `gate/go` → `promobr.online`/`x.gd` e
retorna 0; o `comando_torrents` funciona.

### 3.4 Timeouts e logs

Em rede mais lenta, aumente o timeout dos requests:

```yaml
environment:
  - REQUEST_TIMEOUT_MILLISECONDS=10000
```

Para reduzir volume de logs:

```yaml
environment:
  - LOG_LEVEL=1
```

Opcional: fixe o timezone:

```yaml
environment:
  - TZ=America/Sao_Paulo
```

### 3.5 Script de verificação em bash

O script `scripts/check-indexers.ps1` é PowerShell e não roda no Pi. Crie um
equivalente em bash ou use `curl`:

```bash
BASE_URL="http://localhost:8080"
for indexer in torrent-dos-filmes rede_torrent starck-filmes comando_torrents; do
  echo "== $indexer =="
  curl -sG --max-time 45 \
    --data-urlencode "q=house of the dragon" \
    --data-urlencode "min_seeds=1" \
    "$BASE_URL/indexers/$indexer" \
    | head -c 400
  echo
 done
```

### 3.6 Porta de métricas

O `METRICS_PORT` padrão é `8081`, mas o compose não publica essa porta. Se for
usar Prometheus/Grafana, adicione:

```yaml
ports:
  - "8081:8081"
```

Não exponha a porta de métricas na internet sem proteção.

### 3.7 Docker em SSD

Cartões SD têm desgaste e são lentos para o build. Recomendações:

- use SSD USB 3.0 ou NVMe com adaptador;
- mova `/var/lib/docker` para o SSD; ou
- instale o sistema no SSD.

Em Docker 29+ o armazenamento de imagens fica no containerd
(`/var/lib/containerd`), não em `/var/lib/docker`. Nesse caso mova os dois ou
configure `data-root` no `/etc/docker/daemon.json` e `root` no
`/etc/containerd/config.toml`. O filesystem do SSD precisa ser Linux (ext4):
overlayfs não funciona em NTFS/exFAT (FUSE).

## 4. Passo a passo de instalação

### 4.1 Sistema operacional

1. Grave Raspberry Pi OS 64-bit ou Ubuntu Server 24.04 arm64.
2. Configure usuário, SSH e rede.
3. Atualize:

```bash
sudo apt update && sudo apt full-upgrade -y
```

### 4.2 Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
docker version
docker compose version
```

### 4.3 Projeto e configuração

```bash
git clone https://github.com/felipemarinho97/torrent-indexer.git
cd torrent-indexer
```

Para o stack completo, use o template versionado em `deploy/raspberry/` em vez
do compose da raiz:

```bash
mkdir -p <STACK_ROOT>/torrent-indexer
cp deploy/raspberry/docker-compose.yml <STACK_ROOT>/
cp deploy/raspberry/.env.example <STACK_ROOT>/.env
```

O template já traz volumes `redis-data` e `meili-data`, limites de memória,
FlareSolverr com 1024 MB/`shm_size: 1gb`, timeout de 180s e os bindings de
gestão no IP da LAN. Preencha o `.env` (`MEILI_MASTER_KEY`, `LAN_IP`,
`TAILSCALE_IP`, `ALLOWED_NETWORKS`, `MEDIA_ROOT`, `CONFIG_ROOT`, `PC_IP`,
`PC_MAC`, `LAN_BROADCAST`, `GAMING_PASSWORD`). O passo a passo completo está em
[SETUP.md](SETUP.md#4-caminho-b--stack-completa-no-raspberry-pi).

### 4.4 Build e subida

Build do binário arm64 no PC (recomendado) ou no Pi:

```bash
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -o torrent-indexer-linux-arm64 .
```

Copie o binário para o layout esperado e suba:

```bash
cp torrent-indexer-linux-arm64 <STACK_ROOT>/torrent-indexer/
cd <STACK_ROOT>
docker compose up -d --build
```

Se você buildou a imagem em vez do binário:

```bash
gunzip -c /tmp/torrent-indexer-arm64.tar.gz | docker load
docker compose up -d --no-build
```

### 4.5 Verificação

```bash
docker compose ps
docker compose logs -f torrent-indexer
curl -s http://localhost:8080/ | head -c 300
curl -s http://localhost:8080/search/health
```

Acesse a UI no navegador da rede local:

```text
http://IP_DO_PI:8080/ui/
```

Teste uma série recente pela UI ou via API:

```bash
curl -sG --max-time 60 \
  --data-urlencode "q=house of the dragon s03" \
  --data-urlencode "min_seeds=1" \
  http://localhost:8080/indexers/torrent-dos-filmes
```

## 5. Memória, CPU e armazenamento

Estimativas conservadoras:

| Componente | Memória |
|---|---|
| `torrent-indexer` | 50–150 MB |
| Redis | 20–100 MB |
| Meilisearch | 100–500 MB |
| FlareSolverr/Chromium | 500 MB–1,5 GB |
| Total | ~1–2,5 GB em uso normal |

Com 4 GB há folga moderada; os picos acontecem durante o FlareSolverr e o
build. Recomendações para essa quantidade de RAM:

- use zram como swap (ex.: 2 GB com `zstd`) para evitar desgaste do SD;
- mantenha o pool do FlareSolverr em 2 sessões;
- se quiser limites de memória por container, garanta que o controlador
  `memory` do cgroup esteja ativo (em alguns kernels do Pi ele vem desligado
  via `cgroup_disable=memory` no `bootargs`; adicione `cgroup_enable=memory`
  ao `/boot/firmware/cmdline.txt` e reinicie).

Armazenamento:

- imagens Docker: ~1,5–2,5 GB;
- índice do Meilisearch: depende do volume indexado;
- logs e cache: algumas centenas de MB;
- use pelo menos 32 GB, preferencialmente SSD.

Se for buildar no Pi, tenha swap ativo e pelo menos 2 GB livres.

## 6. Rede, Cloudflare e trackers

- O Pi precisa de saída UDP para consultar trackers.
- Cloudflare pode bloquear o IP; o FlareSolverr resolve desafios, mas não
  garante disponibilidade.
- Evite fazer muitas buscas simultâneas; os sites podem rate-limit.
- Prefira IP fixo ou reserva DHCP no roteador.
- Para acesso externo, use reverse proxy com HTTPS (Caddy, Nginx ou Traefik).
  Não exponha o indexer sem autenticação.
- A porta `8080` deve ficar acessível apenas na LAN, se possível.

## 7. Backup e restauração

### Meilisearch

O mais simples é parar o container e copiar o volume:

```bash
docker compose stop meilisearch
docker run --rm -v torrent-indexer_meili-data:/data -v "$PWD:/backup" alpine \
  tar czf /backup/meili-backup.tar.gz -C /data .
docker compose start meilisearch
```

Alternativa: usar o endpoint de dumps do Meilisearch.

### Redis

Se `appendonly yes` estiver ativo, copie o volume `redis-data`. O cache é
reconstruível; o mais importante é a lista `manual:torrents`.

### Configuração

Guarde `docker-compose.yml`, o `.env` (se usar) e eventuais arquivos de reverse
proxy.

## 8. Checklist

- [ ] Sistema 64-bit (`arm64`), não 32-bit.
- [ ] Docker + Compose plugin instalados.
- [ ] Repositório clonado no Pi.
- [ ] Volumes `meili-data` e `redis-data` adicionados.
- [ ] `FLARESOLVERR_POOL_SIZE` ajustado (2–3).
- [ ] Imagem arm64 buildada no Pi ou via buildx.
- [ ] `docker compose up -d` sem erros.
- [ ] `docker compose ps` com todos os serviços `Up`.
- [ ] `/` responde HTTP 200.
- [ ] `/search/health` responde.
- [ ] UI abre em `http://IP_DO_PI:8080/ui/`.
- [ ] Busca por série recente retorna resultados com seeds.
- [ ] Backup do volume do Meilisearch configurado.
- [ ] Acesso externo protegido por reverse proxy/autenticação (se aplicável).

## 9. Problemas comuns no Pi

| Sintoma | Causa provável | Ação |
|---|---|---|
| `/search` ou UI não funcionam | SO 32-bit | Migrar para 64-bit |
| Build muito lento | SD lento/CPU limitada | Buildar no PC com buildx |
| FlareSolverr morre por OOM | pool grande/Chromium | `FLARESOLVERR_POOL_SIZE=2` |
| Seeds sempre 0 | torrents antigos ou UDP bloqueado | Testar conteúdo recente; checar rede |
| Índice some após recriar container | falta volume | Adicionar `meili-data` |
| Containers não sobem no boot | Docker não habilitado | `sudo systemctl enable docker` |
| UI acessível só localmente | firewall/porta | Liberar `8080` na LAN |
| Cloudflare bloqueia | IP/rate limit | FlareSolverr + menos concorrência |

## 10. Melhorias opcionais

- Reverse proxy com HTTPS (Caddy é o mais simples).
- Autenticação básica no reverse proxy.
- Monitoramento com Prometheus/Grafana.
- Alertas de disco/memória.
- Build multi-arch no CI e publicação em registry.
- Cache de camadas no Dockerfile (`COPY go.mod go.sum` antes de `COPY . .`).
- Script `check-indexers.sh` no repositório.
- Backup automatizado do volume do Meilisearch.

## 11. Estado da implantação (2026-10-26)

Instalação real usada no Pi `<os_user>` (Pi 4, 4 GB). Serve de referência para
futuras alterações.

### 11.1 Hardware e sistema

- Raspberry Pi 4, 4 GB, Raspberry Pi OS 64-bit (Bookworm, kernel 6.12).
- SD de 15 GB para o sistema (~6,4 GB livres) e SSD USB 3.0 de 240 GB:
  - `/dev/sda2`: NTFS de 160 GB em `<MEDIA_ROOT>` (mídia e configs);
  - `/dev/sda4`: ext4 de 63 GB em `<DOCKER_DATA_ROOT>` (Docker/containerd).
- zram de 2 GB (`zstd`, prioridade 100) como swap e `vm.swappiness=100`.
- `cgroup_enable=memory` no `/boot/firmware/cmdline.txt`. O DTB do Pi define
  `cgroup_disable=memory`; sem esse parâmetro o Docker não aplica limites.
- `data-root` do Docker e `root` do containerd em `<DOCKER_DATA_ROOT>`.
  Drop-ins do systemd usam
  `RequiresMountsFor=<MEDIA_ROOT> <DOCKER_DATA_ROOT>`, evitando que o Docker
  grave no SD quando o SSD não montar.
- A ventoinha está ligada direto no 5 V (sem PWM), somando corrente no mesmo
  trilho do SSD USB. Inicialmente houve undervoltage transitório no boot,
  quando todos os containers subiam juntos. Com a subida escalonada
  (`media-stack.service`, seção 11.6) o boot passou a registrar
  `throttled=0x0` e nenhum undervoltage, inclusive sob 60 s de carga nos
  quatro núcleos. Se for trocar ventoinha/fonte: 5 V/3 A+ (ideal 5 V/5 A),
  cabo curto e ventoinha em 3,3 V ou via transistor no GPIO14 (o overlay
  `gpio-fan` já está no `config.txt`).

### 11.2 Compose único

Arquivo: `<STACK_ROOT>/docker-compose.yml`, com `.env` ao lado
(não versionar). Cópia versionada em
[`deploy/raspberry/docker-compose.yml`](deploy/raspberry/docker-compose.yml)
e exemplo de variáveis em `deploy/raspberry/.env.example`.
Projeto Compose: `media`. A subida no boot é controlada por
`media-stack.service` (seção 11.6).

| Serviço | Porta no host |
|---|---|
| `torrent-indexer` | `8080` → `7006` (UI/API) |
| `torrent-indexer` métricas | `8081` |
| `qbittorrent` | `8082` (WebUI), `6881` TCP/UDP |
| `jellyfin` | `8096` (remoto) |
| `sonarr` | `<LAN_IP>:8989` (LAN) |
| `radarr` | `<LAN_IP>:7878` (LAN) |
| `prowlarr` | `<LAN_IP>:9696` (LAN) |
| `bazarr` | `<LAN_IP>:6767` (LAN) |
| `stremio-server` | `11470`, `12470` (remoto) |
| `homepage` | `3000` (remoto, modo adaptativo) |
| `seerr` | `5055` (remoto) |
| `gaming-agent` | `<LAN_IP>:8099` (privado, LAN) e `8098` (público: status/WOL com senha) |
| `media-agent` | `8097` (LAN + Tailscale, allowlist de IP) |
| `media-gateway` | interna (`8099`, rede `media`) |
| `redis`, `meilisearch`, `solvearr` | sem porta publicada |

Limites de memória: Jellyfin 1536 MB; Sonarr/qBittorrent/solvearr/Meilisearch
512 MB; Prowlarr/Bazarr/Radarr/Seerr/Homepage 384 MB; indexer/Stremio 256 MB;
media-gateway 128 MB; Redis 192 MB; gaming-agent 64 MB; media-agent 96 MB.

O `seerr` usa `init: true`, `cap_drop: [ALL]` e `no-new-privileges`. O
`gaming-agent` usa `network_mode: host` e `cap_add: [NET_RAW]` para WOL/ping;
o 8099 é privado (LAN) e o 8098 é público com senha para o WOL. O
`media-agent` também usa `network_mode: host`, em `0.0.0.0:8097`, com
`ALLOWED_NETWORKS` para LAN/Tailscale.
O `homepage` usa `HOMEPAGE_ALLOWED_HOSTS: "*"` (LAN-only).

### 11.3 Volumes e bind mounts

- Volumes nomeados: `redis-data` (`appendonly yes`) e `meili-data`.
- Configs no SSD:
  `<MEDIA_ROOT>/docker/{qbittorrent,sonarr2,prowlarr,bazarr,jellyfin,jellyfin-cache,radarr,homepage,gaming-agent,media-agent,seerr}`.
- Mídia: `<MEDIA_ROOT>` montado como `/media` nos containers; downloads em
  `<MEDIA_ROOT>/downloads`.
- Bibliotecas: `<MEDIA_ROOT>/Suits`, `<MEDIA_ROOT>/series`,
  `<MEDIA_ROOT>/animes` e `<MEDIA_ROOT>/movies`.
- Stremio: `<MEDIA_ROOT>/stremio-server`.
- Legendas/pós-processamento do Bazarr:
  `<MEDIA_ROOT>/docker/bazarr/scripts/shift_subs.py`.

### 11.4 Integrações

- `torrent-indexer` fala com `redis`, `meilisearch` e `solvearr` pela rede
  `media` (nomes de serviço, sem IP).
- `solvearr` usa a imagem oficial `ghcr.io/flaresolverr/flaresolverr` (3.5.0).
  O código suporta sessões e também `FLARESOLVERR_USE_SESSIONS=false` para
  requests sessionless.
- Sonarr → qBittorrent em `qbittorrent:8082`.
- Radarr → qBittorrent em `qbittorrent:8082` (categoria `movies`); Radarr →
  Prowlarr em `prowlarr:9696`.
- Prowlarr → indexer em `torrent-indexer:7006` (Torznab em `/api`, categorias
  2000/5000). O App Profile Standard usa `minimumSeeders = 1`.
- Indexadores no Prowlarr/Radarr/Sonarr: **Comando, Rede Torrent, Torrent dos
  Filmes, Starck, TPB e Torrentio** (6 no Sonarr; 7 no Radarr, contando o proxy
  **PT-BR Alternate Titles**). BluDV ainda atrás do gate; 1337x depende do
  FlareSolverr.
- Sonarr → Prowlarr em `prowlarr:9696`.
- Seerr → Jellyfin `http://jellyfin:8096`, Sonarr `http://sonarr:8989` e
  Radarr `http://radarr:7878`. Perfis/defaults em `MEDIA_STACK.md` §6-7.
- Homepage → widgets e `siteMonitor` pelos nomes de container; os links de
  gestão usam `<LAN_IP>` e os remotos usam o host atual (Tailscale).
  As abas Pedidos/Legendas usam o media-agent e funcionam também no modo
  remoto; o WOL usa o gaming-agent (8098 no Tailscale).
- gaming-agent → só status/WOL do PC; `<LAN_IP>:8099` privado e `8098`
  público com senha. Não acessa mais Bazarr/Radarr/Sonarr/Seerr.
- media-agent → Bazarr (`/bazarr/config.yaml`) para a quota/legendas, lê os
  `config.xml` de Radarr/Sonarr para os endpoints `/arr/*` e `/sonarr/*`
  (busca/adicionar séries e monitorar episódios) e consulta a API do Seerr
  (`/seerr/settings.json`) para incluir pedidos pendentes/aprovados; expõe
  `/bazarr` com a chave do Bazarr no servidor. Fica em `0.0.0.0:8097` com
  allowlist para LAN/Tailscale.
- media-gateway → container interno com o banco do Radarr e `config.xml` do
  Prowlarr; expõe `/torznab/api` (**PT-BR Alternate Titles**), que usa as
  traduções pt-BR do Radarr e busca no Prowlarr.
- Bazarr → Sonarr/Radarr; as legendas ficam no mesmo caminho da mídia.
- Jellyfin: Séries (`/media/Suits` + `/media/series`), Filmes
  (`/media/movies`) e Animes (`/media/animes`). O realtime está ligado, mas não
  é efetivo no mount FUSE/`fuseblk` (NTFS-3G); o scan agendado roda a cada
  30 min.
- Radarr/Sonarr disparam o Custom Script **Jellyfin Refresh**
  (`/config/scripts/jellyfin-refresh.sh`) em import/upgrade/rename, chamando
  `/Library/Media/Updated`; a chave fica em `.jellyfin_key` no diretório
  `scripts/` de cada *arr.
- O qBittorrent mudou de `8080` para `8082`; se algum cliente externo usava
  `8080`, precisa ser atualizado.

### 11.5 Build do indexer

O binário é gerado fora do Pi e copiado (evita compilar no Pi). O Torznab
(`api/torznab.go`) publica `<category>` 2000/5000, o atributo `category` e o
fallback `q=a`; o build inclui essas mudanças.

```bash
GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -trimpath \
  -ldflags "-s -w" -o dist/torrent-indexer-linux-arm64 .
scp dist/torrent-indexer-linux-arm64 \
  <user>@<LAN_IP>:<STACK_ROOT>/torrent-indexer/
```

Antes de substituir, guardar o binário antigo em
`<STACK_ROOT>/torrent-indexer/torrent-indexer-linux-arm64.bak.*`.
O compose usa `dockerfile_inline` apenas copiando o binário. Para atualizar:

```bash
cd <STACK_ROOT>
docker compose build torrent-indexer
docker compose up -d torrent-indexer
```

### 11.6 Operação

A subida no boot é feita por `media-stack.service` em cinco ondas (com ~8 s
entre elas), em vez de deixar o Docker subir tudo de uma vez. A unit está em
[`deploy/raspberry/media-stack.service`](deploy/raspberry/media-stack.service)
e usa `docker compose stop` no shutdown para marcar os containers como
parados; assim o daemon não os inicia sozinho no próximo boot e a unit
controla a ordem. As ondas são: cache/motor, indexer/downloads, Sonarr/Bazarr/
Jellyfin, Radarr/Seerr/Homepage e por fim gaming-agent/media-agent.

Instalação da unit:

```bash
sudo cp deploy/raspberry/media-stack.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable media-stack
```

Observação: depois de uma queda de energia (parada não limpa) o Docker pode
subir todos os containers juntos, ignorando a ordem; em reboot/shutdown
normal a subida é escalonada. Para subir manualmente:

```bash
cd ~/media-stack
docker compose ps
docker compose logs -f torrent-indexer
docker compose up -d <serviço>   # atualiza um serviço só
docker compose down              # derruba a stack inteira
```

#### Watchdog de hardware

O Pi 4 expõe `/dev/watchdog` (BCM2835, timeout de 15 s). O systemd alimenta o
watchdog; se o sistema inteiro travar, o hardware reinicia o Pi. Isso é
complementar ao `autoheal`, que reinicia apenas containers unhealthy.

```bash
sudo sh deploy/raspberry/setup-watchdog.sh
systemctl show -p RuntimeWatchdogUSec -p RebootWatchdogUSec
sudo wdctl
```

O script instala `deploy/raspberry/watchdog.conf` em
`/etc/systemd/system.conf.d/watchdog.conf` e roda `systemctl daemon-reexec`.
O valor de `RuntimeWatchdogSec` deve ficar em `15s` (limite do BCM2835). Se
`/dev/watchdog` não existir, adicione `dtparam=watchdog=on` em
`/boot/firmware/config.txt`, recarregue o módulo `bcm2835_wdt` e reinicie.
A configuração atual já foi aplicada no Pi (`RuntimeWatchdogUSec=15s`,
`WatchdogDevice=/dev/watchdog0`).

### 11.7 Backup

- Meilisearch: parar o container e copiar o volume `meili-data`, ou usar os
  dumps da API.
- Redis: copiar o volume `redis-data` (cache + `manual:torrents`).
- Configs: `<MEDIA_ROOT>/docker` e guarde os arquivos `docker-compose.yml` e
  `.env`. Inclui `radarr`, `sonarr2`, `prowlarr`, `bazarr`, `jellyfin`,
  `homepage`, `gaming-agent`, `media-agent` e `seerr`.
- Backups já criados nesta etapa: `docker-compose.yml.bak.*`,
  `config.yaml.bak.*` (Bazarr), `options.xml.bak.*` (Jellyfin),
  `settings.json.bak.*` (Seerr), legendas `*.bak.shift.*` (Suits) e o binário
  antigo `torrent-indexer-linux-arm64.bak.*`.
- O detalhamento e o rollback estão em [MEDIA_STACK.md](MEDIA_STACK.md) §13.

### 11.8 Segurança e rede

- `8081` (métricas) não tem autenticação; preso ao IP `<LAN_IP>`.
- Meilisearch, Redis, solvearr e media-gateway não publicam portas.
- O Homepage (`3000`) usa `HOMEPAGE_ALLOWED_HOSTS: "*"` e não tem login; no modo
  remoto ele esconde a gestão. As chaves do Bazarr/Radarr ficam no
  `services.yaml` (servidor) e a do Bazarr em `.bazarr_key`; o `custom.js` não
  tem segredo.
- O Bazarr está com CORS habilitado para o dashboard. O **gaming-agent** tem o
  8099 privado (LAN) e o 8098 público, que só expõe `/gaming/status` (sem
  IP/MAC) e `/gaming/wake` com senha em `GAMING_PASSWORD` no `.env` (5
  falhas/min); `.gaming_password` é fallback legado.
  O **media-agent** (`8097`, sem auth) pode alterar perfis, adicionar séries,
  monitorar episódios e acessar o Bazarr; ele só aceita LAN e Tailscale via
  `ALLOWED_NETWORKS`.
- O `media-gateway` é interno; o XML tem `downloadUrl` do Prowlarr com a chave,
  mas o container não tem porta publicada.
- No Tailscale ficam Jellyfin (8096), Seerr (5055), torrent-indexer (8080),
  Homepage (3000), Stremio (11470/12470), gaming 8098 (WOL com senha) e
  media-agent 8097 (Pedidos/Legendas). Radarr/Sonarr/Prowlarr/Bazarr/
  qBittorrent/métricas e o 8099 privado ficam na LAN.
- Para exposição pública, usar reverse proxy com HTTPS e autenticação.
- Prefira reserva DHCP/IP fixo para o Pi.
- Segredos: não versionar `.env`, `config.yaml`, `settings.json`,
  `services.yaml`/`custom.js` do Homepage, nem os bancos dos *arr. A API key do
  hook do Jellyfin fica em `<MEDIA_ROOT>/docker/{radarr,sonarr2}/scripts/.jellyfin_key`.

### 11.9 Stack de mídia e automações

O stack de mídia foi expandido além do indexer:

- **Radarr** (`7878`) e **Sonarr** (`8989`) com Prowlarr (`9696`) e
  qBittorrent (`8082`); roots `/media/movies`, `/media/series` e
  `/media/animes`.
- **Jellyfin** (`8096`) com bibliotecas Séries (`/media/Suits` +
  `/media/series`), Filmes (`/media/movies`) e Animes (`/media/animes`), todas
  com realtime.
- **Bazarr** (`6767`) com perfil PTBR, OpenSubtitles.com/Subf2m, sync
  automático e pós-processamento `-1s` **somente Suits/PT-BR**.
- **Seerr** (`5055`, sucessor do Jellyseerr) para pesquisa/pedidos de filmes e
  séries; perfis Original/Dublado/Anime Japonês.
- **Homepage** (`3000`) como dashboard adaptativo: modo local com gestão e modo
  remoto com Jellyfin/Seerr/Stremio + PC Casa (WOL com senha) e as abas
  Pedidos/Legendas via media-agent.
- **gaming-agent** (`<LAN_IP>:8099` privado e `8098` público) só com
  status/WOL do PC.
- **media-agent** (`8097`, LAN + Tailscale) com Pedidos/Legendas: quota da
  OpenSubtitles, painéis, Seerr, Radarr/Sonarr e proxy do Bazarr.
- **media-gateway** (interno) com o proxy Torznab **PT-BR Alternate Titles**.

Detalhes completos, perfis, custom formats, quota, filas, pendências e rollback
em [MEDIA_STACK.md](MEDIA_STACK.md).

