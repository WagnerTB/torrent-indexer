# Oracle Cloud (OCI) — checklist para a VPS do Jellyfin

Este é o passo a passo específico da Oracle. O deploy em si (WireGuard + Caddy + Cloudflare) está no [README.md](README.md).

## 1. Nomes da Oracle

| Nome | O que é |
|---|---|
| **OCI** | Oracle Cloud Infrastructure (a nuvem) |
| **Always Free** | Recursos gratuitos para sempre, na *home region* |
| **PAYG** | Pay As You Go: os recursos Always Free continuam grátis; você paga só o excedente |
| **VM.Standard.E2.1.Micro** | Shape **AMD**: 1/8 OCPU, 1 GB, 50 Mbps de internet; até 2 grátis |
| **VM.Standard.A1.Flex** | Shape **ARM Ampere**: 2 OCPU/12 GB grátis (2026); só necessário para o stack público |
| **VCN** | Rede virtual (subnet pública + Internet Gateway) |
| **Security List / NSG** | Firewall da nuvem (entrada/saída) |
| **Reserved Public IP** | IP público fixo; use para o WireGuard e para o DNS |
| **Boot Volume** | Disco da instância (padrão 50 GB; 200 GB grátis no total) |

## 2. Dimensionamento

Para **expor o Jellyfin** (Caddy + WireGuard + cloudflared), use a **E2.1.Micro**:

- ~200–350 MB de RAM em uso; 1 GB é suficiente.
- 50 Mbps de internet: 4 streams de 1080p a 12 Mbps.
- 10 TB/mês de egress: ~1.850 h de 1080p; 10 filmes/mês ≈ 110 GB.

A **A1 2/12** só vale se você for mover o stack público (BFF + torrent-indexer + Meilisearch + Redis + FlareSolverr) para a VPS. Para o núcleo, é overkill e a capacidade ARM em São Paulo costuma estar esgotada.

## 3. Conta e região

- [ ] Criar a conta com **home region São Paulo (`sa-saopaulo-1`)**. Os Always Free ficam na home region.
- [ ] Fazer upgrade para **PAYG** (evita a parada por ociosidade).
- [ ] Conferir em **Governance → Limits, Quotas and Usage** os limites da conta.
- [ ] Confirmar o selo **Always Free-eligible** no shape escolhido.
- [ ] **Não** rodar 4 OCPU/24 GB sem confirmar que a sua conta ainda tem isso como free; o padrão 2026 é **2/12**. O excedente de 2/12 custa ~US$ 27,7/mês.

## 4. VCN, subnet e Security List

O jeito mais simples é o wizard **Create VCN with Internet Connectivity**:

- [ ] VCN com subnet **pública** e **Internet Gateway**.
- [ ] Security List de entrada:
  - [ ] TCP **22** — origem: seu IP (melhor) ou `0.0.0.0/0`
  - [ ] UDP **51820** — origem `0.0.0.0/0` (WireGuard)
  - [ ] TCP **80** e **443** — origem `0.0.0.0/0` **somente no modo `public`**
  - [ ] No modo `tunnel`, **não** abra 80/443 na Security List
- [ ] Egress: liberado (padrão).
- [ ] Se usar NSG além da Security List, replique as regras no NSG.

## 5. Instância

- [ ] Shape **VM.Standard.E2.1.Micro** (AMD) ou **VM.Standard.A1.Flex 2 OCPU/12 GB**.
- [ ] Imagem **Ubuntu 24.04** (não Oracle Linux; o `setup.sh` usa `apt`).
- [ ] Boot volume **50 GB** (ou 100 GB se A1; o total grátis é 200 GB).
- [ ] **Assign a public IPv4 address**: sim.
- [ ] Chave SSH: gere/baixe a private key e guarde.
- [ ] Se der **“Out of host capacity”**: tente outro Availability Domain ou espere. **Não** crie shape pago para contornar.
- [ ] Anote o **OCID da instância** (Governance → Instance Details) para o CLI.

## 6. IP público reservado

O IP entregue por padrão é efêmero; ele pode mudar se você parar/iniciar a instância.

- [ ] No console: **Networking → Public IPs** → localize o IP da instância → **Reserve**.
- [ ] Ou via CLI:

```bash
oci network public-ip create \
  --compartment-id <OCID_DO_COMPARTMENT> \
  --lifetime RESERVED \
  --display-name media-vps-ip
```

- [ ] Use esse IP em `VPS_PUBLIC_IP` no `.env` e no registro A (modo `public`).

## 7. Firewall do sistema operacional

A Security List é o firewall da nuvem; a imagem Ubuntu pode ter regras próprias (iptables/nftables).

- [ ] O `setup.sh` instala e configura o **UFW** com 22, 51820/udp e, no modo `public`, 80/443.
- [ ] Se a porta não abrir, verifique também:

```bash
sudo ufw status verbose
sudo iptables -L -n
sudo nft list ruleset
```

- [ ] Se houver regra antiga bloqueando, libere e persista:

```bash
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p udp --dport 51820 -j ACCEPT
sudo netfilter-persistent save   # se o pacote estiver instalado
```

## 8. Copiar e rodar o deploy

No seu PC/Pi (na raiz do repo):

```bash
rsync -av deploy/vps/ ubuntu@<IP_DA_ORACLE>:media-vps/
ssh ubuntu@<IP_DA_ORACLE>
cd media-vps
cp .env.example .env
nano .env
```

No `.env`:

```dotenv
DOMAIN=example.com
ACME_EMAIL=seu-email@dominio
VPS_PUBLIC_IP=<IP reservado>
TUNNEL_TOKEN=            # só no modo tunnel
```

Rode:

```bash
sudo ./scripts/setup.sh tunnel    # teste sem abrir 80/443
# ou
sudo ./scripts/setup.sh public    # definitivo (80/443 + Let's Encrypt)
```

O script:

- instala dependências, Docker e WireGuard;
- gera as chaves e as configs;
- ativa `wg-quick@wg0`;
- configura o UFW;
- sobe o Caddy (e o cloudflared no modo tunnel).

## 9. Pi

No Pi:

```bash
scp ubuntu@<IP_DA_ORACLE>:media-vps/wireguard/generated/wg0.conf.pi .
sudo ./scripts/install-pi-wg.sh wg0.conf.pi
wg show
ping -c3 10.8.0.1
```

No VPS, teste:

```bash
curl -fsS http://10.8.0.2:8096/health
```

## 10. Cloudflare/DNS

- **Modo tunnel**: crie o tunnel, copie o token para `TUNNEL_TOKEN` e adicione o Public Hostname `jellyfin.SEU_DOMINIO` → `http://caddy:8080`. Não abra 80/443.
- **Modo public**: crie o registro **A** `jellyfin` → IP reservado, **Proxy status: DNS only (cinza)**. Abra 80/443 na Security List e no UFW. O Caddy emite o Let's Encrypt.

## 11. Jellyfin

- [ ] **Dashboard → Networking → Known proxies**: `10.8.0.1`, `172.18.0.1`, `127.0.0.1`.
- [ ] **EnableRemoteAccess: true**; admin sem acesso remoto.
- [ ] App/TV: `https://jellyfin.SEU_DOMINIO`, qualidade máxima, Direct Play.
- [ ] Confira no Dashboard: **Direct Play/DirectStream**, sem transcode.

## 12. Custos, budget e quota

- [ ] **Budget** de US$ 1/mês com alertas 50%/100% (Billing → Budgets).
- [ ] **Quota** no compartment para limitar compute/block storage. No console, os nomes exatos dos recursos aparecem no editor de quotas. Via CLI:

```bash
oci limits quota create \
  --compartment-id <OCID_DO_COMPARTMENT> \
  --name free-guard \
  --description "limites Always Free" \
  --statements file://statements.json
```

- [ ] Não criar NAT Gateway, load balancer maior, IP extra, volume Higher Performance ou imagem paga.
- [ ] Conferir a fatura no primeiro mês: esperado **US$ 0,00**. Se aparecer centavos, identificar (IP? volume? recurso fora do free).

### Idle reclamation

A Oracle pode **parar** (não apagar) instâncias Always Free ociosas: por 7 dias, CPU no percentil 95 < 20%, rede < 20% e memória < 20% (A1). O volume de boot permanece; você reinicia no console se o shape estiver disponível.

- O núcleo Caddy+WireGuard **não** gera carga suficiente para evitar isso.
- Para “ligar e esquecer”, use **PAYG** ou um VPS pago. No PAYG, os Always Free continuam grátis; o excedente é cobrado.

## 13. CLI útil

```bash
# configurar API key
oci setup config

# ligar/parar
oci compute instance action --action START --instance-id <OCID>
oci compute instance action --action STOP  --instance-id <OCID>

# listar instância/IP
oci compute instance list --compartment-id <OCID_DO_COMPARTMENT> --output table
oci network public-ip list --compartment-id <OCID_DO_COMPARTMENT> --output table

# IP reservado
oci network public-ip create --compartment-id <OCID_DO_COMPARTMENT> --lifetime RESERVED --display-name media-vps-ip
```

Política mínima para automação: `Allow group <grupo> to manage instances in compartment <compartment>` (não use `manage all-resources`).

## 14. O que não fazer

- Não rodar o stack completo (indexer/FlareSolverr) na E2.1.Micro de 1 GB; ele não cabe.
- Não rodar 4 OCPU/24 GB sem confirmar o free; o excedente custa ~US$ 27,7/mês.
- Não expor 8096/8097/Redis/Meilisearch/FlareSolverr; só o Caddy (443 ou tunnel).
- Não usar o proxy laranja da Cloudflare no modo `public`; o vídeo voltaria para o CDN e para o problema de ToS.
- Não deixar o firewall IPv6 do roteador aberto tentando resolver; o caminho aqui é a Oracle.
