# Oracle Cloud (OCI) — guia de implantação da VPS do Jellyfin

**Revisão:** 26/11/2026 — configuração inicial, Stack Terraform e automação de tentativas.

**Estado atual:** rede e firewall criados; Stack configurado; API e e-mail testados; automação iniciada no Raspberry Pi. A VPS ainda não foi criada: a Oracle retornou `500-InternalError: Out of host capacity`.

**Atualização 27/11/2026:** pacote `deploy/vps` criado e validado localmente (Caddyfile, Compose e geração de chaves WireGuard); a VPS continua pendente de capacidade.

Este documento atualiza o checklist original da OCI. O deploy da aplicação está descrito no `README.md` deste diretório e foi criado/validado localmente em 27/11/2026 (Apêndice B); a execução na OCI segue pendente.

## 1. Arquitetura escolhida

```text
Celular / TV / PC externo
         │ HTTPS (443)
         ▼
jellyfin.example.com
         │ DNS only (Cloudflare)
         ▼
OCI São Paulo — media-vps (Ubuntu 24.04 / E2.1.Micro)
         │ Caddy (TLS) + WireGuard (10.8.0.1)
         │ túnel WireGuard, UDP 51820
         ▼
Raspberry Pi / servidor residencial (10.8.0.2)
         │ Jellyfin :8096
         ▼
Arquivos de mídia locais
```

O Pi inicia a conexão WireGuard para a VPS; não é necessário expor o Jellyfin nem abrir portas no roteador residencial para esse desenho. O IP residencial pode mudar ou estar atrás de CGNAT. É recomendável configurar `PersistentKeepalive = 25` no peer residencial quando houver NAT, se o script já não o fizer.

Modo escolhido: **public**, com DNS da Cloudflare sem proxy (nuvem cinza). O Cloudflare Tunnel não é necessariamente mais lento, mas adiciona uma dependência e os termos da Cloudflare para os planos Free, Pro e Business exigem serviço pago apropriado para distribuir vídeo e outros arquivos grandes pelo Tunnel público. O caminho direto evita esse problema. O IP público da VPS ficará visível.

## 2. Progresso e ponto de retomada

- [x] Conta OCI criada; São Paulo selecionada.
- [x] VCN `media-vcn` criada com o wizard de conectividade.
- [x] Security List padrão configurada para o modo public.
- [x] Configurações da instância selecionadas (E2.1.Micro / Ubuntu 24.04).
- [x] Stack salvo e Plan executado: `1 to add, 0 to change, 0 to destroy`.
- [x] Apply manual tentado; falha por falta de capacidade.
- [x] OCI CLI instalada e configurada no Raspberry (`<USER>`, host `<HOST_PI>`).
- [x] Chave pública de API cadastrada; autenticação verificada com `oci os ns get`.
- [x] Topic e inscrição de e-mail configurados; mensagem de teste recebida.
- [x] Script de retry e serviço systemd instalados; log inicial verificado.
- [x] Pacote `deploy/vps` criado e validado localmente (Caddy/Compose/WireGuard).
- [ ] Confirmar primeiro Apply automático e o eventual sucesso da criação.
- [ ] Executar `setup.sh` na VPS e validar WireGuard + Caddy + Jellyfin.
- [ ] Confirmar modalidade da conta e home region; conferir limites/consumo e configurar budget.
- [ ] Confirmar que a chave privada SSH correspondente ao Stack foi guardada.
- [ ] Reservar/vincular IPv4 público e testar SSH.
- [ ] Implantar WireGuard e Caddy; configurar DNS; testar Jellyfin.
- [ ] Conferir faturamento e segurança final.

Último log confirmado (26/11/2026, horário do Raspberry):

```text
14:18:51  Started oracle-vps.service
14:18:51  Automacao iniciada.
14:18:51  Intervalo: 900 segundos.
14:19:00  Sem capacidade disponivel.
14:19:00  Nova tentativa em 900s.
```

A tentativa seguinte era esperada por volta de 14:34. O log comprova a inicialização e identificação do erro anterior, mas não comprova ainda que o primeiro Apply automático foi criado ou que a VPS existe.

## 3. Nomes, limites e dimensionamento

| Termo | Significado / configuração |
|---|---|
| OCI | Oracle Cloud Infrastructure |
| Always Free | Recursos gratuitos dentro das franquias e condições aplicáveis |
| PAYG | Pay As You Go: cobra excedentes e recursos pagos; Always Free continua gratuito dentro das regras |
| E2.1.Micro | AMD x86-64, 1/8 OCPU garantido, 1 GB RAM; até duas instâncias gratuitas |
| A1.Flex | ARM, franquia atual de 1.500 OCPU-h e 9.000 GB-h mensais (~2 OCPUs/12 GB) |
| VCN | Virtual Cloud Network |
| Security List / NSG | Regras de firewall OCI de subnet / grupo de interfaces |
| Reserved Public IP | IPv4 reservado, independente da vida da instância |
| Boot Volume | Disco do sistema; padrão ~50 GB, franquia combinada de 200 GB |
| Resource Manager | Serviço Terraform da OCI, que armazena Stacks e executa jobs |
| Notifications | Publicação de mensagens para inscrições de e-mail e outros canais |

**Para este projeto:** E2.1.Micro, apenas como proxy e endpoint WireGuard. Não executar o stack público completo (BFF, torrent-indexer, Meilisearch, Redis, FlareSolverr) na instância de 1 GB. Se futuramente migrar esse stack, reavaliar a A1 e compatibilidade ARM; não trocar o shape no Stack atual enquanto o retry estiver ligado.

A Oracle anuncia até 50 Mbps de internet na E2.1.Micro (até 480 Mbps para determinados tráfegos internos). Quatro streams de 12 Mbps consumiriam 48 Mbps antes de overhead: não é uma capacidade garantida. Começar com um stream e medir; o upload residencial, a CPU e a rota também limitam a velocidade. O consumo estimado de 200–350 MB do núcleo Caddy/WireGuard é uma hipótese do guia original, não medição desta VPS.

Os primeiros 10 TB mensais de tráfego de saída elegível são gratuitos segundo a tabela da Oracle; a 12 Mbps constantes, 1 hora equivale a cerca de 5,4 GB, um filme de 2 h a cerca de 10,8 GB e 10 filmes a ~108 GB (sem overhead). O custo esperado do projeto é R$ 0,00, condicionado à elegibilidade e ao uso dentro das franquias. Não é garantia de fatura.

## 4. Conta, região e limites

- Região de trabalho: `sa-saopaulo-1` (Brazil East / São Paulo); confirmar que também é a home region da tenancy.
- Compartimento: root. Modalidade PAYG não foi confirmada; não houve upgrade registrado no acompanhamento.
- Menu **Governance → Limits, Quotas and Usage**: filtrar Compute e consultar o limite/uso de E2.1.Micro na região/AD aplicável. Não solicitar aumento de limite para contornar falta de host.
- A disponibilidade física é diferente da quota: limite livre não garante host disponível.
- O upgrade PAYG é opcional e não garante capacidade para o shape gratuito nem imunidade a recolhimento por ociosidade. Não selecionar recursos pagos sem avaliar custo.

## 5. VCN, subnet e firewall OCI — já criado

Menu **Networking → Virtual Cloud Networks → Start VCN Wizard → Create VCN with Internet Connectivity**.

| Campo | Valor |
|---|---|
| VCN | `media-vcn` |
| CIDR VCN | `10.0.0.0/16` |
| Subnet pública | `public subnet-media-vcn (regional)` |
| CIDR público | `10.0.0.0/24` |
| CIDR privado | `10.0.1.0/24` (valor proposto; confirmar na console se necessário) |
| IPv6 | Desabilitado |
| DNS Resolver | Habilitado |
| Internet Gateway | Criado pelo wizard |
| Rota pública | `0.0.0.0/0` via Internet Gateway (confirmar na tabela de rotas) |

O wizard também cria subnet privada, NAT Gateway e Service Gateway. Não são necessários para esta VPS pública; não criar outros. Não excluir os recursos existentes sem conferir suas dependências. A faixa WireGuard `10.8.0.0/24` é separada da VCN; verificar se também não conflita com a LAN residencial.

### Default Security List for media-vcn

Todas as regras de entrada são **stateful** (`Stateless = No`). Source Type = CIDR; Source Port Range = All. Regras observadas/configuradas:

| Origem | Protocolo | Destino / tipo | Finalidade |
|---|---|---|---|
| `0.0.0.0/0` | TCP | 22 | SSH (restringir posteriormente) |
| `0.0.0.0/0` | ICMP | regra padrão | Path MTU Discovery |
| `10.0.0.0/16` | ICMP | regra padrão | Erros de conectividade interna |
| `0.0.0.0/0` | UDP | 51820 | WireGuard |
| `0.0.0.0/0` | TCP | 80 | HTTP/ACME |
| `0.0.0.0/0` | TCP | 443 | HTTPS |

Manter Egress padrão liberado. Não abrir 8096/8097, Redis, Meilisearch ou FlareSolverr. O SSH foi deixado aberto durante a instalação; restringir à origem pública autorizada `/32` quando possível, sem bloquear o próprio acesso (IP residencial pode mudar). Não configurar NSG adicional apenas para duplicar regras: OCI combina permissões de Security Lists e NSGs; uma regra mais restrita num grupo não anula uma regra ampla em outro.

## 6. Configuração da instância — salva no Stack, não criada

Menu **Compute → Instances → Create Instance**.

| Seção | Campo | Configuração |
|---|---|---|
| Basic | Name | `media-vps` (nome proposto) |
| Basic | Compartment | root |
| Placement | Availability Domain | AD-1 |
| Placement | Capacity type | On-demand capacity |
| Placement | Fault Domain | Preferir seleção automática; conferir no Stack |
| Image | SO | Canonical Ubuntu 24.04, x86-64, Free |
| Shape | Compute | `VM.Standard.E2.1.Micro`, Always Free-eligible |
| Management | IMDS | Requerer cabeçalho de autorização se imagem compatível |
| Management | Initialization script | Nenhum |
| Availability | Live migration | Oracle escolhe melhor opção |
| Availability | Restore lifecycle state | Habilitado |
| Security | Shielded instance | Desabilitado |
| Security | Security attributes / ZPR | Nenhum |
| Networking | VCN | `media-vcn` |
| Networking | Subnet | Pública existente |
| Networking | VNIC name | `media-vnic` (nome proposto) |
| Networking | Private IPv4 | Automático |
| Networking | Public IPv4 | Automático, inicialmente efêmero |
| Networking | IPv6 / NSG | Desabilitado / nenhum NSG adicional |
| SSH | Add SSH keys | Generate a key pair for me; baixar ambas as chaves |
| Storage | Boot volume | Padrão (console mostrava ~46,6 GB) |
| Storage | Performance | Padrão/Balanced, não customizar |
| Storage | In-transit encryption | Habilitado |
| Storage | Chave própria | Desabilitado; criptografia gerenciada pela Oracle |
| Storage | Additional volumes | Nenhum |

O console mostrou estimativa de **R$ 10,45/mês** para o Boot Volume, sem necessariamente aplicar a franquia gratuita. Dentro dos 200 GB totais na home region, o disco padrão é esperado como gratuito. Conferir o Cost Analysis após criação.

A chave privada SSH deve ficar guardada em local seguro. Exemplo Windows: `<CAMINHO_DA_CHAVE_SSH>`. Não confundir com a chave de assinatura da API. Não foi verificada a posse da chave privada; confirmar antes da implantação.

## 7. Stack e erro de capacidade

O primeiro Create falhou com:

```text
Error: 500-InternalError, Out of host capacity
```

Foi usada a opção **Save as Stack**, sem necessidade de preencher novamente o wizard. Configuração recomendada: `media-vps-stack`, root, versão Terraform 1.5.x apresentada pelo console, sem providers personalizados. Verificar o nome e versão reais no Stack antes de recriá-lo.

Caminho: **Developer Services → Resource Manager → Stacks → Stack existente**.

| Operação | Efeito |
|---|---|
| Plan | Calcula alterações propostas; não cria infraestrutura |
| Apply | Executa a criação/modificação conforme o plano |
| Destroy | Destrói recursos gerenciados; não usar para tentar de novo |

Plan validado: `Plan: 1 to add, 0 to change, 0 to destroy.` O Apply manual falhou por capacidade. A disponibilidade muda; não há prazo garantido. Se o erro persistir, avaliar seleção automática de Fault Domain, outra shape elegível ou VPS alternativa. Não modificar o Stack com o serviço ativo.

O Resource Manager padrão possui franquia Always Free de 100 stacks e 2 jobs simultâneos (duração máxima por job de 24 horas). Não selecionar jobs premium.

## 8. Autenticação OCI no Raspberry — concluída

Host `<HOST_PI>`, usuário Linux `<USER>`, home `<HOME>`. OCI CLI reportada nos erros: 3.97.1, SDK 2.193.0.

Instalação original:

```bash
bash -c "$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)"
oci --version
oci setup config
```

Na configuração interativa: User OCID e Tenancy OCID do console, região `sa-saopaulo-1`, gerar chave de assinatura. Arquivo confirmado: `<HOME>/.oci/config`.

```bash
ls -la ~/.oci/
cat ~/.oci/oci_api_key_public.pem
```

No console: **Profile → User Settings → API Keys → Add API Key → Paste Public Key**. Colar somente a chave pública PEM. Conferir fingerprint com o arquivo config; não sobrescrever a chave privada existente. Os nomes padrão das chaves podem variar conforme a configuração feita.

Teste executado com sucesso:

```bash
oci os ns get
```

Retornou `data` conforme esperado. Guardar `~/.oci/config` e chave privada de API em backup criptografado, restringir permissões e nunca adicionar a Git. O perfil tem acesso aos recursos conforme suas permissões IAM; idealmente usar usuário/grupo dedicado com permissões mínimas para Stack/jobs e Notifications, em vez de credencial administrativa de uso geral.

## 9. Notifications — concluído

Console: **Notifications → Topics → Create Topic**. Nome sugerido `media-vps-alerts`, root. Abrir tópico → Create Subscription → Email → confirmar inscrição no e-mail. O teste de publicação foi bem-sucedido.

| Tipo de OCID | Uso correto |
|---|---|
| `ocid1.ormstack...` | Stack, para criar/consultar jobs |
| `ocid1.onstopic...` | Topic, para publicar mensagens |
| `ocid1.onssubscription...` | Subscription, para consultar inscrição |

Ocorreram dois erros `400 InvalidParameter` por passar primeiro o OCID do Stack e depois o OCID da Subscription para o parâmetro `--topic-id`. Não era falha de autenticação. Para recuperar o Topic via Subscription:

```bash
TOPIC_ID=$(oci ons subscription get \
  --subscription-id "OCID_DA_SUBSCRIPTION" \
  --query 'data."topic-id"' --raw-output)
echo "$TOPIC_ID"
oci ons message publish --topic-id "$TOPIC_ID" \
  --title "Teste Oracle VPS" \
  --body "O Raspberry Pi conseguiu enviar uma notificacao."
```

A Oracle documenta franquia de 1.000 notificações de e-mail/mês. A automação envia avisos de sucesso e erro inesperado, não e-mails a cada falta de capacidade.

## 10. Automação de tentativas — instalada e iniciada

### 10.1 Estrutura real no Raspberry

```text
<HOME>/
├── .oci/
│   ├── config
│   └── [chaves de assinatura PEM]
└── oracle-vps/
    ├── config.env      # OCIDs, intervalos e caminho OCI CLI
    ├── retry.sh        # script de tentativas
    ├── retry.lock      # trava local flock
    ├── last-job.json   # logs do último Apply com falha
    ├── success.flag    # criado quando Apply tem sucesso
    └── halted.flag     # criado em erro crítico

/etc/systemd/system/oracle-vps.service
```

Os flags podem ainda não existir; são criados conforme o resultado. OCIDs completos e chaves não são reproduzidos neste documento para facilitar seu armazenamento/compartilhamento seguro. Eles estão no arquivo local e no console.

### 10.2 Configuração

Dependências instaladas/configuradas: OCI CLI, `jq`, Bash, `flock` (util-linux), systemd. Para reproduzir em outro Raspberry, instalar a CLI e autenticar primeiro.

```bash
mkdir -p ~/oracle-vps
sudo apt install -y jq
# Substituir ambos os OCIDs pelos do console.
cat > ~/oracle-vps/config.env <<EOF_CONFIG
STACK_ID=OCID_DO_STACK
TOPIC_ID=OCID_DO_TOPIC
RETRY_INTERVAL=900
POLL_INTERVAL=30
OCI_BIN=$(command -v oci)
EOF_CONFIG
chmod 600 ~/oracle-vps/config.env
```

`RETRY_INTERVAL=900` = 15 minutos entre falhas de capacidade e nova tentativa; `POLL_INTERVAL=30` = consulta de job em andamento. Sem máximo de tentativas definido. Esses intervalos são escolhas do projeto, não recomendações oficiais da OCI.

### 10.3 Comportamento do script

1. Carrega `config.env`, valida prefixos dos OCIDs e caminho da CLI.
2. Usa `flock` para evitar duas execuções locais; verifica os flags de encerramento.
3. Lista jobs do Stack; se houver Apply bem-sucedido, grava `success.flag`, notifica e termina.
4. Aguarda jobs pendentes ou em andamento.
5. Obtém logs do último Apply com falha. Repete apenas se houver `out of host capacity`.
6. Aguarda 900 segundos; consulta novamente os jobs antes de criar um novo.
7. Cria Apply com `AUTO_APPROVED`, usando o mesmo Stack, sem alterar shape/configurações.
8. Consulta o job a cada 30 s. Em sucesso, grava flag, envia e-mail e termina; em falha, volta a verificar motivo.
9. Em erro inesperado, grava `halted.flag`, tenta avisar e termina.

A cópia exata instalada não foi lida: o usuário confirmou o final do script, 168 linhas e o log de início. Para backup fiel, copie o `retry.sh` existente no Pi. O código de referência enviado na conversa está reproduzido no apêndice; não é necessário substituir o script em funcionamento.

### 10.4 Serviço systemd instalado

```ini
[Unit]
Description=Oracle Cloud VPS Automatic Retry
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<USER>
Environment=HOME=<HOME>
WorkingDirectory=<HOME>/oracle-vps
ExecStart=/bin/bash <HOME>/oracle-vps/retry.sh
Restart=no

[Install]
WantedBy=multi-user.target
```

Comandos de instalação (já executados):

```bash
chmod +x ~/oracle-vps/retry.sh
bash -n ~/oracle-vps/retry.sh
sudo systemctl daemon-reload
sudo systemctl enable --now oracle-vps.service
```

### 10.5 Monitoramento e administração

```bash
systemctl status oracle-vps --no-pager
journalctl -u oracle-vps -n 50 --no-pager
journalctl -u oracle-vps -f
```

Ctrl+C fecha apenas a visualização do log. O serviço continua quando o SSH é fechado e inicia com o Pi se habilitado. O Raspberry precisa continuar ligado e conectado.

| Ação | Comando |
|---|---|
| Parar | `sudo systemctl stop oracle-vps` |
| Iniciar | `sudo systemctl start oracle-vps` |
| Reiniciar | `sudo systemctl restart oracle-vps` |
| Desabilitar boot automático | `sudo systemctl disable oracle-vps` |
| Ativar boot automático | `sudo systemctl enable oracle-vps` |
| Ver se está habilitado | `systemctl is-enabled oracle-vps` |
| Ver erro do Apply | `less ~/oracle-vps/last-job.json` |

Para alterar o intervalo, editar `~/oracle-vps/config.env` e reiniciar o serviço. 300 = 5 min; 600 = 10 min; 900 = 15 min; 1800 = 30 min; 3600 = 1 h. Preferir 900 ou um intervalo maior se a OCI apresentar limitação de requisições.

### 10.6 Alertas, limitações e recuperação

- O primeiro Apply automático e o envio de e-mail de sucesso ainda não foram observados. O script não foi testado de ponta a ponta fora do Raspberry.
- `Restart=no`: erro de CLI, rede, API, limite de requisições ou outro erro pode encerrar a automação. O flag `halted.flag` impede novas execuções mesmo após reboot. Se o Pi estiver sem internet, o e-mail de erro também pode falhar. Consultar periodicamente o journal.
- Se houver `success.flag`, confirmar em Compute que a instância existe e está Running. Um Apply bem-sucedido é identificado pelo histórico, não por checagem independente da instância; não apagar o flag para forçar outra criação.
- O flag de sucesso é gravado antes do envio de e-mail. Se a publicação falhar, a VPS pode ter sido criada sem aviso. Conferir o console e logs. Não reiniciar tentativas por ausência de e-mail.
- Não executar Apply manual nem editar o Stack em paralelo. A trava é apenas local e não impede alterações feitas pelo console/outros clientes. `AUTO_APPROVED` executa as configurações vigentes; é essencial preservar o Stack aprovado e seus limites.
- Parar o serviço não cancela um job já em execução na Oracle. Consultar Resource Manager antes de retomar ou alterar recursos.
- O script compara a resposta inteira de listagem antes de criar outro job; mudanças nos metadados podem adiar uma tentativa. Se os logs repetirem esse comportamento, investigar, não desabilitar a proteção sem revisão.
- Um erro de capacidade pode coexistir com outro erro; a busca de texto é simples. Se falhas diferentes surgirem, parar o serviço e conferir o log inteiro.
- Após erro crítico: parar o serviço, ler journal/last-job.json, verificar console e se já existe VPS/job em curso; corrigir a causa. Somente se não houver VPS criada nem job concorrente, remover `halted.flag` e iniciar novamente:

```bash
sudo systemctl stop oracle-vps
journalctl -u oracle-vps -n 100 --no-pager
ls -l ~/oracle-vps/*.flag
# Após investigar e confirmar que é seguro retomar:
rm -f ~/oracle-vps/halted.flag
sudo systemctl start oracle-vps
```

Depois de sucesso confirmado: `sudo systemctl disable --now oracle-vps`. Preservar arquivos/logs para histórico. Não usar Destroy para limpar os logs do Stack.

### 10.7 Backup do que realmente foi instalado

```bash
umask 077
tar -czf ~/oracle-vps-backup-$(date +%F).tar.gz \
  -C <HOME> oracle-vps \
  -C / etc/systemd/system/oracle-vps.service
```

O arquivo contém OCIDs e logs; guardar em local privado. Fazer backup separado e criptografado de `~/.oci/` e da chave SSH original; não colocar em Git. Exportar/download do Terraform do Stack pelo Resource Manager se desejar uma cópia de suas configurações exatas.

## 11. O que adiantar enquanto falta capacidade

- Testar Jellyfin local, se estiver no Pi: `curl -fsS http://localhost:8096/health` (esperado `Healthy`). Se estiver em outro host, usar seu IP LAN real. Testar Direct Play em TV/celular na rede local.
- Medir upload residencial por cabo, preferencialmente também em horários de pico; deixar margem para bitrate variável e outros usuários da rede.
- Conferir a zona DNS de `example.com` e a delegação à Cloudflare; não apontar o registro A para um IP provisório.
- Conferir o repositório `deploy/vps/`, `.env.example`, `scripts/setup.sh`, `scripts/install-pi-wg.sh`, Compose e Caddyfile. Confirmar caminhos, permissões, porta 8096, modo `public` e como o Pi recebe a config WireGuard. Não executar `setup.sh` de VPS no Pi. **Revisado e validado em 27/11/2026 (Apêndice B).**
- Conferir backup das chaves SSH/API e arquivos de automação. Configurar budget e alertas agora, se disponíveis na conta.
- Não alterar as configurações do Stack enquanto o serviço estiver ativo.

## 12. Quando a VPS for criada — IP reservado e SSH

1. Abrir Compute → Instances → instância criada; verificar Running, E2.1.Micro, Ubuntu, VCN pública e selo Always Free. Confirmar que não existem outras instâncias/volumes inesperados.
2. Conferir o job bem-sucedido e interromper a automação como indicado na seção 10.
3. Em Instance details → Attached VNICs → VNIC principal → IPv4 Addresses, localizar o IP privado primário e seu IP público efêmero.
4. Criar um **Reserved Public IP** (`media-vps-ip`) na região e no compartimento apropriados. Conferir elegibilidade, limites e preço antes da reserva; não manter IPs extras desnecessários.
5. Para atribuí-lo, primeiro remover o IP público efêmero do IP privado primário, depois associar o reservado. Não é possível converter o endereço efêmero existente em reservado mantendo o mesmo número. Fazer pela console para evitar perder acesso durante uma sessão SSH. O IPv4 efêmero não muda simplesmente por parar/iniciar a instância; o reservado facilita recuperação e troca de instância.
6. Confirmar que o IP reservado está atribuído ao VNIC; anotar IP e OCID da instância em local privado.

Exemplo de CLI (somente após conferir IDs e remover o IP efêmero corretamente):

```bash
oci network public-ip create \
  --compartment-id "OCID_DO_COMPARTMENT" \
  --lifetime RESERVED --display-name media-vps-ip
oci network public-ip update \
  --public-ip-id "OCID_DO_IP_RESERVADO" \
  --private-ip-id "OCID_DO_IP_PRIVADO_PRIMARIO"
```

Não reexecutar Apply automaticamente depois de alterações manuais de rede: mudanças fora do Terraform podem causar drift. Fazer Plan e revisar antes de qualquer Apply futuro.

Conectar via Windows PowerShell (adaptar caminho da chave):

```powershell
ssh -i "<CAMINHO_DA_CHAVE_SSH>" ubuntu@IP_DA_VPS
```

Ou Linux/Pi, se possuir cópia segura da chave SSH:

```bash
chmod 600 /caminho/media-vps.key
ssh -i /caminho/media-vps.key ubuntu@IP_DA_VPS
```

Conferir a impressão digital da chave de host na primeira conexão por canal confiável. Não compartilhar a chave privada; não habilitar login por senha ou root remoto para contornar falhas. Atualizar pacotes e verificar RAM/disco (`free -h`, `df -h`).

## 13. Firewall do Ubuntu e deploy — pendente

A Security List da Oracle e o firewall do Ubuntu são camadas diferentes. O roteiro original informa que o `setup.sh` instala e configura UFW, Docker e WireGuard. Confirmar o código antes de executar; não assumir que as regras foram aplicadas corretamente.

```bash
sudo ufw status verbose
sudo iptables -L -n -v
sudo nft list ruleset
sudo ss -lntup
```

Permitir apenas SSH, WireGuard UDP 51820 e HTTP/HTTPS TCP 80/443 no modo public, com política de entrada restrita. Antes de habilitar UFW, garantir que o SSH autorizado está liberado. Imagens OCI podem conter regras próprias; não limpar o firewall inteiro. Caso uma regra antiga impeça o tráfego, identificar cadeia, ordem e gerenciador responsável antes de ajustar. Não aplicar cegamente `iptables -I INPUT` nem persistir regras conflitantes com UFW/Docker. Docker pode publicar portas desviando do UFW; conferir também o Compose e as regras Docker. Nunca publicar diretamente os serviços internos na Internet.

Do PC/Pi, na raiz do repositório original:

```bash
rsync -av -e 'ssh -i /caminho/media-vps.key' deploy/vps/ ubuntu@IP_DA_VPS:media-vps/
ssh -i /caminho/media-vps.key ubuntu@IP_DA_VPS
cd media-vps
cp .env.example .env
chmod 600 .env
nano .env
```

No `.env`:

```dotenv
DOMAIN=example.com
ACME_EMAIL=SEU_EMAIL
VPS_PUBLIC_IP=IP_RESERVADO
TUNNEL_TOKEN=
```

Conferir se `DOMAIN` é o domínio raiz esperado pelo Caddyfile ou o hostname completo; o roteiro original usa domínio raiz. Criar o DNS definitivo conforme a seção 15 antes da emissão TLS.

```bash
sudo ./scripts/setup.sh public
```

Segundo o roteiro, o script instala dependências, Docker/WireGuard, gera chaves/configs, ativa `wg-quick@wg0`, configura firewall e sobe Caddy. O pacote foi validado localmente (Apêndice B); a execução na VPS segue pendente.

## 14. WireGuard no Pi — ferramentas instaladas, config pendente

Transferir a configuração gerada pela VPS (contém chave privada; proteger o arquivo). Ajustar os caminhos de chave SSH e do repositório conforme a instalação:

```bash
scp -i /caminho/media-vps.key ubuntu@IP_DA_VPS:media-vps/wireguard/generated/wg0.conf.pi .
chmod 600 wg0.conf.pi
# Na pasta do repositório que contém scripts/install-pi-wg.sh:
sudo ./scripts/install-pi-wg.sh wg0.conf.pi
sudo wg show
ping -c3 10.8.0.1
```

Se o arquivo remoto estiver acessível apenas por root, usar método seguro de transferência; não torná-lo público nem world-readable. Verificar endpoint IP reservado/51820 e `AllowedIPs` antes de instalar; não rotear toda a internet do Pi pelo túnel se não for necessário. Confirmar `PersistentKeepalive` no peer residencial quando aplicável.

Na VPS:

```bash
sudo wg show
curl -fsS http://10.8.0.2:8096/health
```

O esperado é handshake recente e `Healthy`. Caso falhe, investigar firewall do Pi, IP do Jellyfin, Docker, rota, endpoint/porta, MTU e `AllowedIPs`. Não abrir 8096 publicamente para resolver.

## 15. Cloudflare/DNS e Caddy — pendente

Modo escolhido: **public**.

| Campo Cloudflare DNS | Valor |
|---|---|
| Type | A |
| Name | `jellyfin` |
| IPv4 address | IP reservado da Oracle |
| Proxy status | DNS only (cinza) |
| TTL | Auto ou valor padrão |

Hostname: `https://jellyfin.example.com`. Não criar AAAA sem IPv6 funcional. O Caddy deve emitir certificado público (ACME/Let's Encrypt conforme config) após o DNS resolver para a VPS e 80/443 estarem acessíveis.

Testes:

```bash
# Em uma máquina com dig instalado:
dig +short jellyfin.example.com A
curl -I https://jellyfin.example.com
curl -fsS https://jellyfin.example.com/health
```

Conferir configuração/logs do Caddy e containers se houver falha. Um modo alternativo `tunnel` existe no roteiro original, mas não é o escolhido; exigiria rever termos da Cloudflare, token e portas. Não usar proxy laranja para o Jellyfin no desenho public.

## 16. Jellyfin — configuração e testes finais

- Dashboard → Networking: habilitar acesso remoto (`EnableRemoteAccess: true`), manter admin sem acesso remoto se compatível com administração local e criar usuários sem privilégio administrativo para streaming.
- Em Known Proxies, cadastrar **somente os IPs reais e confiáveis do reverse proxy**. O guia original sugeria `10.8.0.1`, `172.18.0.1`, `127.0.0.1`, mas os dois últimos só devem ser usados se a topologia e o IP de origem real os justificarem. Verificar antes de configurar.
- Não expor painel/porta 8096 diretamente; usar HTTPS, senhas fortes e atualizações.
- No app/TV, usar `https://jellyfin.example.com`. Testar com rede móvel, fora do Wi-Fi doméstico.
- No Dashboard, confirmar Direct Play/Direct Stream; se transcodificar, verificar codecs, áudio, legendas e limites do cliente. Ajustar bitrate à velocidade real, não forçar qualidade máxima se houver buffering.
- Medir estabilidade com 1 stream e depois com streams simultâneos. Verificar CPU, RAM, upload residencial e tráfego da VPS. Não prometer 4 streams antes dos testes.

## 17. Custos, segurança e idle reclamation

| Recurso | Expectativa / limite |
|---|---|
| E2.1.Micro | Gratuito, até 2 na home region conforme condições |
| Ubuntu | Imagem Free selecionada |
| Boot Volume | ~50 GB dentro de 200 GB combinados (home region) |
| Backups de volume | Até 5 dentro do Always Free |
| Internet egress | Primeiros 10 TB/mês elegíveis gratuitos |
| Resource Manager padrão | 100 stacks, 2 jobs simultâneos |
| Notifications | 1.000 notificações e-mail/mês |
| Total esperado | R$ 0,00 condicionado à elegibilidade e uso; não verificado no faturamento |

Ações pendentes: Billing → Budgets, criar limite de US$ 1/mês ou equivalente disponível, alertas a 50%/100%; conferir Cost Analysis e fatura. Budget é aviso, não bloqueio de gasto. Se for possível, usar quotas de compartimento adequadas para limitar compute e armazenamento. Evitar shapes pagos, volumes extras, performance superior, IPs desnecessários, load balancers adicionais, jobs premium e imagens licenciadas.

A Oracle pode recuperar instâncias Always Free consideradas ociosas durante sete dias (CPU p95 abaixo de 20%, rede abaixo de 20%, e memória abaixo de 20% apenas para A1). Não assumir que o boot volume sempre será preservado ou que será possível iniciar imediatamente após recuperação; manter backups e documentação de reconstrução. O núcleo Caddy/WireGuard pode ter uso baixo, portanto essa é uma possibilidade real. PAYG preserva as franquias, mas não foi confirmada proteção absoluta contra recuperação ou falta de capacidade. Não gerar carga artificial para contornar regras de ociosidade.

## 18. CLI de referência

```bash
# Consulta de jobs e logs
oci resource-manager job list --stack-id "OCID_DO_STACK" --all
oci resource-manager job get --job-id "OCID_DO_JOB"
oci resource-manager job get-job-logs --job-id "OCID_DO_JOB" --all

# Apply manual: SOMENTE com automação parada e plano revisado
# Preferir usar a opção de aplicar um Plan validado pela console.
oci resource-manager job create-apply-job \
  --stack-id "OCID_DO_STACK" --execution-plan-strategy AUTO_APPROVED

# Consultas de instâncias e IPs
oci compute instance list --compartment-id "OCID_DO_COMPARTMENT" --output table
oci network public-ip list --compartment-id "OCID_DO_COMPARTMENT" --scope REGION --output table

# Ligar / parar instância (somente após confirmar o OCID)
oci compute instance action --action START --instance-id "OCID_DA_INSTANCIA"
oci compute instance action --action STOP --instance-id "OCID_DA_INSTANCIA"
```

Política IAM: permissões de Compute não bastam para operar Resource Manager e Notifications. Se criar identidade dedicada para automação, conceder apenas as permissões requeridas de Stack/jobs e publicação no tópico, além das permissões de recursos necessárias para o Apply. Não copiar `manage all-resources` indiscriminadamente. A identidade atual já demonstrou autenticação e publicação; a autorização de criação do Apply automático ainda deve ser confirmada.

## 19. Referências oficiais (consultadas em 26/11/2026)

- [Oracle — Recursos Always Free](https://docs.oracle.com/pt-br/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [Oracle — Limites por serviço](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm)
- [Oracle — Preços de rede e egress](https://www.oracle.com/cloud/networking/virtual-cloud-network/pricing/)
- [Oracle — Wizard de VCN](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/quickstartnetworking.htm)
- [Oracle — Security Lists](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm)
- [Oracle — Security Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm)
- [Oracle — Out of host capacity](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/troubleshooting-out-of-host-capacity.htm)
- [Oracle — Instalação da CLI](https://docs.oracle.com/pt-br/iaas/Content/API/SDKDocs/cliinstall.htm)
- [Oracle — Chaves de assinatura da API](https://docs.oracle.com/Content/API/Concepts/apisigningkey.htm)
- [Oracle — Apply Job](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-job-apply.htm)
- [Oracle CLI — create-apply-job](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/resource-manager/job/create-apply-job.html)
- [Oracle CLI — listar jobs](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/resource-manager/job/list.html)
- [Oracle CLI — logs de job](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/resource-manager/job/get-job-logs.html)
- [Oracle — Notifications](https://docs.oracle.com/en-us/iaas/Content/Notification/Concepts/notificationoverview.htm)
- [Oracle — Publicar notificação](https://docs.oracle.com/en-us/iaas/Content/Notification/Tasks/publishingmessages.htm)
- [Oracle — IPs públicos](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingpublicIPs.htm)
- [Oracle — Atribuir IP reservado](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/reserved-public-ip-assign.htm)
- [Oracle — Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm)
- [Cloudflare — DNS proxy status](https://developers.cloudflare.com/dns/proxy-status/)
- [Cloudflare — Tunnel FAQ / streaming](https://developers.cloudflare.com/cloudflare-one/faq/cloudflare-tunnels-faq/)
- [Jellyfin — Reverse proxy](https://jellyfin.org/docs/general/post-install/networking/reverse-proxy/)
- [Docker — Packet filtering e firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/)

## Apêndice A — referência do retry.sh

Código enviado durante a configuração, reproduzido para registro. **Não substitua a cópia em execução sem necessidade.** A cópia real tem 168 linhas segundo `wc -l`; esta reprodução pode diferir em espaços/linhas ou conteúdo colado. O backup da seção 10.7 é a fonte mais fiel.

```bash
#!/bin/bash
set -Eeuo pipefail

cd "$(dirname "$0")"
source config.env

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

oci_cmd() {
    "$OCI_BIN" --region sa-saopaulo-1 "$@"
}

notify() {
    oci_cmd ons message publish \
        --topic-id "$TOPIC_ID" \
        --title "$1" \
        --body "$2"
}

halt_error() {
    trap - ERR
    log "ERRO: $1"
    touch halted.flag
    notify "Oracle VPS - Automacao interrompida" "$1" || true
    exit 1
}

trap 'halt_error "Falha inesperada. Verifique os logs do Raspberry."' ERR

exec 9>retry.lock
flock -n 9 || exit 0

[[ "$STACK_ID" == ocid1.ormstack.* ]]
[[ "$TOPIC_ID" == ocid1.onstopic.* ]]
[[ -x "$OCI_BIN" ]]

if [[ -f success.flag || -f halted.flag ]]; then
    log "Automacao ja encerrada."
    exit 0
fi

list_jobs() {
    oci_cmd resource-manager job list \
        --stack-id "$STACK_ID" \
        --all \
        --sort-by TIMECREATED \
        --sort-order DESC \
        --output json
}

log "Automacao iniciada."
log "Intervalo: ${RETRY_INTERVAL} segundos."

while true; do
    JOBS=$(list_jobs)

    if jq -e '.data | any(
        .operation == "APPLY" and
        ."lifecycle-state" == "SUCCEEDED"
    )' <<< "$JOBS" >/dev/null; then
        log "Apply concluido com sucesso!"
        touch success.flag
        notify "Oracle VPS criada com sucesso!" \
            "O Apply da VPS Jellyfin foi concluido. Acesse o console da Oracle."
        exit 0
    fi

    if jq -e '.data | any(
        ."lifecycle-state" == "ACCEPTED" or
        ."lifecycle-state" == "IN_PROGRESS" or
        ."lifecycle-state" == "CANCELING"
    )' <<< "$JOBS" >/dev/null; then
        log "Existe um job em andamento. Aguardando."
        sleep "$POLL_INTERVAL"
        continue
    fi

    LAST=$(jq -c '[.data[] |
        select(.operation == "APPLY")][0] // empty' \
        <<< "$JOBS")

    if [[ -z "$LAST" ]]; then
        halt_error "Nenhum Apply anterior encontrado."
    fi

    JOB_ID=$(jq -r '.id' <<< "$LAST")
    STATE=$(jq -r '."lifecycle-state"' <<< "$LAST")

    if [[ "$STATE" != "FAILED" ]]; then
        halt_error "Estado inesperado: $STATE"
    fi

    oci_cmd resource-manager job get-job-logs \
        --job-id "$JOB_ID" \
        --all > last-job.json

    if grep -qi 'out of host capacity' last-job.json; then
        log "Sem capacidade disponivel."
    else
        halt_error "O Apply falhou por outro motivo. Consulte last-job.json."
    fi

    log "Nova tentativa em ${RETRY_INTERVAL}s."
    sleep "$RETRY_INTERVAL"

    CURRENT=$(list_jobs)
    if [[ "$CURRENT" != "$JOBS" ]]; then
        log "Estado do Stack mudou. Verificando novamente."
        continue
    fi

    log "Executando novo Apply..."
    NEW_JOB=$(oci_cmd resource-manager job create-apply-job \
        --stack-id "$STACK_ID" \
        --execution-plan-strategy AUTO_APPROVED \
        --display-name "media-vps-auto-retry" \
        --no-retry \
        --query 'data.id' \
        --raw-output)

    log "Job criado: $NEW_JOB"

    while true; do
        STATE=$(oci_cmd resource-manager job get \
            --job-id "$NEW_JOB" \
            --query 'data."lifecycle-state"' \
            --raw-output)
        log "Status: $STATE"
        case "$STATE" in
            ACCEPTED|IN_PROGRESS|CANCELING)
                sleep "$POLL_INTERVAL"
                ;;
            SUCCEEDED)
                touch success.flag
                notify "Oracle VPS criada com sucesso!" \
                    "Sua VPS Jellyfin foi criada. Acesse o console da Oracle."
                log "Sucesso! Automacao encerrada."
                exit 0
                ;;
            FAILED)
                break
                ;;
            *)
                halt_error "Job terminou com estado: $STATE"
                ;;
        esac
    done
done
```

## Apêndice B — atualização do deploy (27/11/2026)

O pacote `deploy/vps/` foi criado e validado localmente. A VPS Oracle ainda não existe; o Apply segue em retry por falta de capacidade.

### Arquivos

- `README.md`, `ORACLE.md`
- `Caddyfile.public`, `Caddyfile.tunnel`
- `docker-compose.public.yml`, `docker-compose.tunnel.yml`
- `wireguard/wg0.conf.vps.example`, `wireguard/wg0.conf.pi.example`
- `scripts/gen-wg-keys.sh`, `scripts/setup.sh`, `scripts/install-pi-wg.sh`, `scripts/check.sh`, `scripts/teardown.sh`
- `.env.example`

### Validações feitas

- `bash -n` em todos os scripts: ok.
- `docker compose config` nos dois composes: ok.
- `caddy validate` nos dois Caddyfiles: ok.
- `gen-wg-keys.sh` executado em cópia temporária com IP de teste: gerou `wg0.conf.vps` e `wg0.conf.pi` com chaves/PSK e endpoint corretos.
- Caddy do modo tunnel iniciado em container: configuração carregada e requisição retornou 502 para o upstream `10.8.0.2:8096` (esperado, pois o túnel ainda não existe).

### Estado do Pi

- `wireguard`/`wireguard-tools` instalados (cliente).
- Nenhum `wg0.conf` ativado; falta o IP público da Oracle para gerar/aplicar a config.

### Próximo passo

1. Quando a instância E2.1.Micro for criada, reservar o IPv4 e liberar 22/51820 (+80/443 no modo public) na Security List.
2. Copiar `deploy/vps`, preencher `.env` e rodar `sudo ./scripts/setup.sh public`.
3. Copiar `wireguard/generated/wg0.conf.pi` para o Pi e rodar `sudo ./scripts/install-pi-wg.sh wg0.conf.pi`.
4. Criar o A `jellyfin` (DNS only) e testar `https://jellyfin.<DOMAIN>`.
5. Jellyfin Known proxies: `10.8.0.1` (VPS) e `172.18.0.1` (gateway Docker do Pi); `127.0.0.1` só se a topologia justificar.

### Observação

O texto original das seções 13/14 ("não examinado", "nenhuma etapa validada") fica superado por este apêndice: os arquivos foram examinados e validados localmente; o que falta é a execução na VPS.
