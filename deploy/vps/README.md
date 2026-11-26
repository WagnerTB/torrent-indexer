# VPS pública para o Jellyfin — Oracle + WireGuard + Caddy (+ Cloudflare)

> **Status Oracle:** [OCI_Jellyfin_Guia_Atualizado.md](OCI_Jellyfin_Guia_Atualizado.md) — VCN/Security List/Stack/CLI prontos; VPS pendente de capacidade.

Este diretório deixa pronto o caminho para expor o Jellyfin do Pi **sem abrir porta no Pi** e **sem depender do Tailscale Funnel**. O Pi continua atrás do CGNAT; ele apenas **inicia** o WireGuard para a VPS.

## Nomes (para não confundir)

| Nome | O que é |
|---|---|
| **Oracle Cloud (OCI)** | Onde a VPS roda (Always Free ou PAYG) |
| **WireGuard** | Túnel privado Oracle ↔ Pi (`10.8.0.1` ↔ `10.8.0.2`) |
| **Caddy** | Proxy HTTPS na Oracle; recebe o público e encaminha para o Jellyfin via WireGuard |
| **Cloudflare Tunnel** | Entrada pública opcional, sem abrir porta na Oracle; vídeo passa pelo CDN da Cloudflare |
| **DNS only (nuvem cinza)** | Registro A direto para a Oracle; o vídeo **não** passa pela Cloudflare |

## Caminho rápido (Oracle)

1. **Oracle:** `VM.Standard.E2.1.Micro` + Ubuntu 24.04 + IP público reservado. Security List: 22/tcp, 51820/udp e, no modo `public`, 80/443. Detalhes em [ORACLE.md](ORACLE.md).
2. **VPS:** copie `deploy/vps`, edite o `.env` e rode `sudo ./scripts/setup.sh public` (ou `tunnel`).
3. **Pi:** copie `wg0.conf.pi` e rode `sudo ./scripts/install-pi-wg.sh wg0.conf.pi`.
4. **Cloudflare:** no modo `public`, crie o A `jellyfin` → IP reservado, **DNS only (cinza)**; no modo `tunnel`, use `http://caddy:8080`.
5. **Jellyfin:** Known proxies `10.8.0.1`, `172.18.0.1`, `127.0.0.1`.

## Dois modos

| Modo | Entrada | Portas na Oracle | Vantagem | Quando usar |
|---|---|---|---|---|
| `tunnel` | Cloudflare Tunnel → `caddy:8080` | Nenhuma (só 22 e 51820/udp) | Teste rápido, sem DNS/porta | Validar a cadeia |
| `public` | `https://jellyfin.SEU_DOMINIO` → Oracle:443 | 80/443 + 51820/udp | Sem CDN da Cloudflare, sem ToS de vídeo | Definitivo |

Nos dois casos o Jellyfin continua no Pi; a Oracle só faz proxy. **Não há transcode na Oracle.**

## Arquitetura

```text
tunnel:
  Internet -> Cloudflare -> cloudflared (Oracle) -> Caddy:8080 -> WireGuard -> Pi:8096

public:
  Internet -> Oracle:443 (Caddy + Let's Encrypt) -> WireGuard -> Pi:8096
```

```text
Oracle (VPS)                         Pi (Jellyfin)
10.8.0.1  <---- WireGuard ---->      10.8.0.2
Caddy / cloudflared                  Jellyfin 8096, *arr, mídia
```

## Requisitos

- VPS Oracle com **Ubuntu 24.04** (não use Oracle Linux com este `setup.sh`, que é apt).
- **VM.Standard.E2.1.Micro** (AMD, 1 GB) já serve para este núcleo. **VM.Standard.A1.Flex 2 OCPU/12 GB** só é necessário se você for mover o stack público (BFF/indexer) para a VPS.
- IP público (reservado, de preferência).
- Domínio no Cloudflare (`example.com`).
- Pi com Jellyfin em `:8096` e acesso SSH.
- Para a Oracle: siga também o [ORACLE.md](ORACLE.md).

## 1. No VPS Oracle

Copie este diretório para a VPS (do seu PC/Pi):

```bash
rsync -av deploy/vps/ ubuntu@<IP_DA_ORACLE>:media-vps/
ssh ubuntu@<IP_DA_ORACLE>
cd media-vps
cp .env.example .env
nano .env
```

Preencha:

```dotenv
DOMAIN=example.com
ACME_EMAIL=seu-email@dominio
VPS_PUBLIC_IP=<IP público reservado da Oracle>
TUNNEL_TOKEN=            # só no modo tunnel
```

Rode:

```bash
sudo ./scripts/setup.sh tunnel    # teste via Cloudflare
# ou
sudo ./scripts/setup.sh public    # definitivo via IP público + Caddy TLS
```

O script:

- instala `wireguard-tools`, `ufw`, Docker/Compose;
- gera as chaves e as configs do WireGuard;
- instala `/etc/wireguard/wg0.conf` e ativa `wg-quick@wg0`;
- abre 22 e 51820/udp (e 80/443 no modo `public`);
- sobe o Caddy (e o cloudflared no modo `tunnel`);
- deixa a config do Pi em `wireguard/generated/wg0.conf.pi`.

> Se o `/etc/wireguard/wg0.conf` já existir, o script não sobrescreve. Use `FORCE=1 sudo ./scripts/setup.sh ...` se for intencional.

## 2. No Pi (cliente WireGuard)

Copie a config gerada para o Pi:

```bash
scp ubuntu@<IP_DA_ORACLE>:media-vps/wireguard/generated/wg0.conf.pi .
sudo ./scripts/install-pi-wg.sh wg0.conf.pi
```

O script instala o WireGuard no Pi e ativa o `wg0`. A config usa:

```ini
AllowedIPs = 10.8.0.0/24
PersistentKeepalive = 25
```

Ela **não** altera a rota default do Pi. O Tailscale/SSH continuam funcionando.

Teste:

```bash
wg show
ping -c3 10.8.0.1
```

No VPS, teste o Jellyfin pelo túnel:

```bash
curl -fsS http://10.8.0.2:8096/health
```

## 3. Cloudflare

### 3.1 Modo `tunnel` (teste, sem abrir porta)

1. Zero Trust → Networks → Tunnels → **Create a tunnel** → Cloudflared.
2. Copie o token para `TUNNEL_TOKEN` no `.env` e rode `sudo ./scripts/setup.sh tunnel` (ou `docker compose -f docker-compose.tunnel.yml up -d`).
3. No tunnel, adicione **Public Hostname**:
   - `jellyfin.SEU_DOMINIO`
   - Service: `http://caddy:8080`
4. Teste `https://jellyfin.SEU_DOMINIO`.

O Caddy recebe a requisição em `:8080`, identifica o Host e encaminha para `10.8.0.2:8096`.

> **ToS:** nesse modo o vídeo passa pelo CDN da Cloudflare. Para uso familiar pequeno costuma funcionar, mas o plano free não permite oficialmente servir vídeo. Para o definitivo, use o modo `public`.

### 3.2 Modo `public` (definitivo, sem CDN no vídeo)

1. No Cloudflare DNS, crie:
   - Tipo: **A**
   - Nome: `jellyfin`
   - Conteúdo: `<IP público reservado da Oracle>`
   - Proxy status: **DNS only (nuvem cinza)**
2. Na Oracle, libere **80/tcp e 443/tcp** na Security List e no UFW (o `setup.sh public` já abre no UFW).
3. Rode `sudo ./scripts/setup.sh public`.
4. O Caddy emite o certificado Let's Encrypt e serve `https://jellyfin.SEU_DOMINIO`.

> Se o registro ficar **laranja (proxied)**, o vídeo volta a passar pela Cloudflare e o problema de ToS retorna. Use **cinza**.

### 3.3 Teste rápido sem Oracle (opcional)

No tunnel que já roda no Pi (`pi-media`), adicione um Public Hostname `jellyfin.SEU_DOMINIO` → `http://127.0.0.1:8096`. Serve para validar a Cloudflare antes de montar a Oracle. Se ficar bom, você pode parar por aqui — mas o vídeo estará no CDN da Cloudflare.

## 4. Jellyfin

No Jellyfin do Pi:

1. **Dashboard → Networking → Known proxies**: adicione
   - `10.8.0.1` (WireGuard da Oracle)
   - `172.18.0.1` (gateway Docker do Pi)
   - `127.0.0.1`
2. Salve e reinicie o container do Jellyfin.
3. Mantenha **EnableRemoteAccess: true**; deixe o usuário **admin sem acesso remoto**.
4. No app/TV, use `https://jellyfin.SEU_DOMINIO` e qualidade **máxima** (1080p 60 Mbps). Confirme no Dashboard que está **Direct Play/DirectStream**, não transcode.

Se o IP real aparecer como `10.8.0.1`/`172.18.0.1`, confira os Known proxies acima.

## 5. Validação

No VPS:

```bash
./scripts/check.sh tunnel
# ou
./scripts/check.sh public
```

O script mostra:

- `wg show` e ping no `10.8.0.2`;
- `curl http://10.8.0.2:8096/health`;
- containers;
- HTTPS público;
- logs do cloudflared (modo tunnel).

Teste final: 1080p no 4G por 30 min; Dashboard do Jellyfin em Direct Play.

## 6. Segurança

- SSH só por chave; firewall 22 restrito ao seu IP quando possível.
- Jellyfin com senha forte; admin sem acesso remoto.
- Não exponha `8096`, `8097`, Redis, Meilisearch, FlareSolverr ou o indexer.
- `wireguard/generated/` e `.env` nunca vão para o git (já estão no `.gitignore`).
- Mantenha o Ubuntu e as imagens Docker atualizados (`unattended-upgrades`, `docker compose pull`).
- No modo `public`, a 443 fica pública e recebe bots: use fail2ban/limites se quiser.

## 7. Custos e limites (Oracle)

- **E2.1.Micro (AMD)**: 1 GB, 50 Mbps de internet, 10 TB/mês de egress — suficiente para 1080p (4 streams de 12 Mbps).
- **A1 Flex**: 2 OCPU/12 GB grátis (2026); só necessário para o stack público.
- **PAYG**: os recursos Always Free continuam grátis; você paga só o que passar. Use **Budget** e **Quotas**.
- **Idle reclamation**: instâncias Always Free ociosas podem ser paradas; no PAYG, na prática, isso não acontece. O núcleo Caddy+WireGuard gera pouco tráfego e **não** evita a reciclagem sozinho.
- Detalhes e checklist da Oracle: [ORACLE.md](ORACLE.md).

## 8. Rollback

```bash
sudo ./scripts/teardown.sh tunnel
# ou
sudo ./scripts/teardown.sh public
```

Isso para os containers, desativa o `wg-quick@wg0` e remove as regras 80/443/51820 do UFW. As configs e volumes são preservados.

Para voltar atrás no DNS, remova o hostname no Cloudflare (tunnel) ou o registro A (public).

## 9. Arquivos

```text
deploy/vps/
  README.md                     este guia
  ORACLE.md                     checklist da Oracle (VCN, shape, PAYG, budget)
  .env.example                  variáveis (domínio, IP, token)
  Caddyfile.public              HTTPS + Let's Encrypt
  Caddyfile.tunnel              HTTP :8080 atrás do cloudflared
  docker-compose.public.yml     Caddy 80/443
  docker-compose.tunnel.yml     Caddy :8080 + cloudflared
  cloudflared/config.yml.example
  wireguard/wg0.conf.vps.example
  wireguard/wg0.conf.pi.example
  scripts/gen-wg-keys.sh
  scripts/setup.sh
  scripts/install-pi-wg.sh
  scripts/check.sh
  scripts/teardown.sh
```
