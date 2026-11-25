# Plano — Acesso remoto ao Jellyfin com Tailscale Funnel

> **Status:** não iniciado
> **Criado em:** 2026-11-24
> **Objetivo:** permitir que TVs fora da rede assistam ao Jellyfin sem instalar Tailscale na TV, usando o celular apenas para administração.
> **Escopo:** Jellyfin. Não expor Radarr, Sonarr, Bazarr, Prowlarr, qBittorrent, Homepage ou `media-agent`.

## Contexto atual

- Jellyfin roda na Raspberry Pi 4 (8 GB) em `:8096`.
- O Tailscale já é usado para acessar Jellyfin, Seerr, Homepage, indexer e `media-agent`.
- O Tailscale Funnel está incluído no plano Personal gratuito (até 6 usuários).
- O Funnel está em beta e tem **limite de banda não configurável**.
- TVs Samsung/LG normalmente não têm Tailscale; TVs Android/Apple TV podem ter.
- O gargalo real de streaming remoto é o **upload da casa** e a **transcodificação no Pi 4**.

## Decisão

Usar o **Funnel** como primeira tentativa, porque:

- é grátis e rápido de testar;
- não exige abrir porta no roteador;
- resolve TVs sem Tailscale;
- mantém o Tailscale para administração.

Se a qualidade não for suficiente, cair para uma das alternativas da seção **Fallback**.

## Pré-requisitos

- Tailscale v1.38.3 ou superior no Pi.
- MagicDNS habilitado no tailnet.
- HTTPS habilitado no tailnet (o Funnel cria o certificado).
- Jellyfin acessível localmente em `http://127.0.0.1:8096` a partir do host do Tailscale.
- Conta no Jellyfin com senha forte para cada pessoa da família.
- Um aparelho fora da rede (celular no 4G/5G) para testar.

## Etapas

### 1. Validar a base

- [ ] Confirmar o Tailscale no Pi:

  ```bash
  tailscale status
  tailscale version
  ```

- [ ] Confirmar o Jellyfin local:

  ```bash
  curl -I http://127.0.0.1:8096
  ```

- [ ] Confirmar o IP Tailscale do Pi e o nome do tailnet no admin console.

### 2. Habilitar HTTPS e MagicDNS

- [ ] No admin console do Tailscale, habilitar **MagicDNS**.
- [ ] Habilitar **HTTPS Certificates** para o tailnet.
- [ ] Confirmar que o Pi aparece com o nome `https://<pi>.<tailnet>.ts.net`.

### 3. Criar o Funnel

- [ ] Criar o Funnel apontando para o Jellyfin:

  ```bash
  tailscale funnel 8096
  ```

  O comando mostra a URL pública, algo como:

  ```text
  https://<pi>.<tailnet>.ts.net
  ```

- [ ] Testar a URL no próprio Pi:

  ```bash
  curl -I https://<pi>.<tailnet>.ts.net
  ```

- [ ] Testar no celular **fora do Wi-Fi da casa**, usando 4G/5G.
- [ ] Fazer login no Jellyfin pela URL pública.

> Para deixar rodando em background, usar o modo background da CLI ou configurar via admin console. Confirmar o comando disponível na versão instalada.

### 4. Configurar a TV remota

- [ ] Instalar/abrir o app do Jellyfin na TV.
- [ ] Adicionar o servidor com a URL do Funnel.
- [ ] Fazer login com o usuário da família.
- [ ] Testar navegação, capas, reprodução e legendas.

### 5. Testes de qualidade

Executar com a TV na rede remota real, não só no celular.

| Teste | Como medir | Critério |
|---|---|---|
| Direct play 1080p | Jellyfin Dashboard → Playback Info | Vídeo direto, sem transcode |
| 1080p com transcode | Dashboard + CPU do Pi | Sem travamentos; CPU abaixo de ~80% |
| 720p | Forçar limite de bitrate | Estável por 30 min |
| Duas streams | Duas TVs/celulares | Sem buffering constante |
| 4K | Teste opcional | Provavelmente inviável no Pi 4 |
| Legenda | Faixa PT-BR | Sincronizada e selecionável |
| Retomada | Sair e voltar | Continua do ponto correto |

- [ ] Medir o upload real da casa (Speedtest ou equivalente).
- [ ] Definir limite de qualidade por usuário no Jellyfin.
- [ ] Confirmar no dashboard se está ocorrendo transcode.
- [ ] Ajustar `MaxStreamingBitrate` no app/TV se necessário.

### 6. Segurança

- [ ] Criar usuários separados para cada pessoa; não compartilhar o admin.
- [ ] Usar senhas fortes e únicas.
- [ ] Não usar a conta admin para assistir.
- [ ] Revisar permissões de biblioteca por usuário (ex.: conteúdo infantil).
- [ ] Manter Jellyfin e Tailscale atualizados.
- [ ] Monitorar logs de login do Jellyfin.
- [ ] Considerar fail2ban/reverse proxy com rate limit se houver exposição pública relevante.
- [ ] Não expor `media-agent`, Radarr, Sonarr, Bazarr, Prowlarr ou qBittorrent.

### 7. Operação

- [ ] Verificar o status do Funnel:

  ```bash
  tailscale funnel status
  ```

- [ ] Documentar a URL pública em local seguro.
- [ ] Testar novamente após reinício do Pi.
- [ ] Verificar se o Funnel sobe automaticamente após reboot.
- [ ] Definir rotina de atualização mensal.

### 8. Rollback

Se o Funnel não servir ou expuser demais:

```bash
tailscale funnel reset
```

- [ ] Confirmar que a URL pública deixou de responder.
- [ ] Manter o acesso por Tailscale normal para administração.
- [ ] Reavaliar a alternativa de gateway na casa da TV.

## Critérios de conclusão

- [ ] Uma TV fora da rede abre o Jellyfin pela URL do Funnel.
- [ ] Login funciona com usuário não-admin.
- [ ] Uma stream 1080p roda por 30 minutos sem buffering relevante.
- [ ] Legendas PT-BR funcionam.
- [ ] O Pi não fica sobrecarregado.
- [ ] A URL pública não expõe nenhum serviço de gestão.
- [ ] O procedimento de rollback foi testado.

## Fallback (se o Funnel não der conta)

| Opção | Custo | Vantagem | Desvantagem |
|---|---|---|---|
| Segundo Raspberry Pi como gateway na casa da TV | custo do Pi | funciona com qualquer TV; controle total | setup manual; precisa de Ethernet/AP |
| GL.iNet com Tailscale | ~US$ 30–80 | plug-and-play; Wi-Fi/Ethernet | mais um aparelho |
| VPS + WireGuard/Tailscale + reverse proxy | ~US$ 5/mês | estável; controle de TLS/domínio | configuração e custo mensal |
| IP público + DDNS + Caddy | custo do domínio | direto, sem relay | depende de IP público (CGNAT bloqueia) |
| Tailscale no Apple TV/Android TV | grátis | sem hardware extra | só funciona se a TV for um box compatível |
| Celular como ponte | grátis | AirPlay/espelhamento ou cabo HDMI | não é integrado; bateria/qualidade |

### Segundo Pi como gateway

- Pi na casa da TV, conectado à internet local por Wi-Fi ou Ethernet.
- Ethernet para a TV (recomendado) ou Wi-Fi AP com adaptador USB.
- Pi como gateway/DHCP da TV, com NAT e Tailscale.
- A TV acessa o Jellyfin pelo IP Tailscale da casa.
- **Não basta** colocar o Pi na mesma rede da TV: a TV precisa usar o Pi como gateway ou conectar na rede dele.

### O mesmo Pi do Jellyfin

- **Não** consegue ser o gateway de uma TV em outra casa.
- Pode ser o host do Funnel (este plano) ou exit node/subnet router para dispositivos que já estão no Tailscale.

## Riscos

- **Funnel em beta:** comportamento e limites podem mudar.
- **Banda do relay:** pode ser insuficiente para 1080p/4K ou múltiplas streams.
- **Upload da casa:** limite físico; o Funnel não aumenta a banda.
- **Transcodificação no Pi 4:** sem Quick Sync; transcode por software é limitado.
- **Exposição pública:** qualquer pessoa com a URL chega ao login do Jellyfin; a segurança depende da autenticação.
- **CGNAT:** se o upload for baixo ou a operadora bloquear, nem alternativas com IP público funcionam.

## Perguntas em aberto

- Qual a velocidade real de upload da casa?
- Quantas pessoas vão assistir simultaneamente?
- As TVs remotas são Android TV/Fire TV, Samsung/LG ou Apple TV?
- O Funnel precisa expor também o Seerr ou só o Jellyfin?
- Vale a pena reservar um domínio próprio em vez de usar `*.ts.net`?
