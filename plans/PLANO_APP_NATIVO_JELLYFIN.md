# Plano — App nativo da família (Jellyfin + Seerr + media-agent)

> **Status:** decisões de arquitetura fechadas; próximo passo é o spike do Seerr (etapa 0)
> **Criado em:** 2026-11-24
> **Atualizado em:** 2026-11-24 — plataforma, auth e acesso público decididos
> **Objetivo:** um app mobile próprio, no estilo Netflix/Crunchyroll, para a família e amigos acessarem a biblioteca do Jellyfin, pedirem conteúdo no Seerr e acompanharem legendas/status.
> **Fora de escopo:** substituir o Homepage no desktop. O dashboard web continua como está.
> **Licenças:** o uso é pessoal/família; a prioridade é controle e capacidade de modificação, não licença permissiva.
> **Prévia visual:** `preview/mobile-app.html` (protótipo navegável) e `preview/mockup-board.png`.

## Decisões fechadas (2026-11-24)

| # | Decisão | Escolha |
|---|---|---|
| D1 | Plataforma do MVP | **Android-only**, Kotlin + Compose + Media3 |
| D2 | Onde vive o BFF | **Evoluir o `media-agent`** (Python), com listener novo em `/api/v1` |
| D3 | Identidade | **Jellyfin é o IdP do BFF**; o BFF valida o token em `/Users/Me` |
| D4 | Identidade no Seerr | **Sessão por pessoa** (cookie do Seerr guardado no BFF) |
| D5 | Acesso público | **Funnel → Jellyfin (8096)** e **Cloudflare Tunnel → BFF (8099)** |
| D6 | Rotas de admin | **Só em LAN/Tailscale**, nunca públicas, além de exigir `IsAdministrator` |
| D7 | “Manter conectado” | **Senha no Keystore do Android** (ligado por padrão); o BFF nunca a persiste |

Consequências aceitas:

- D4 obriga login com **usuário/senha** do Jellyfin no primeiro uso (Quick Connect não entrega a senha, então não abre sessão no Seerr).
- D5 mantém vídeo fora da Cloudflare de propósito, para não arriscar throttle/termos de uso.
- D2 mantém as rotas legadas do `media-agent` intactas para o Homepage; só o `/api/v1` fica público e autenticado.
- D6 aceita que administração fora de casa exija Tailscale. É o preço de não expor gestão na internet.
- D7 troca “sessão expirada pede senha” por “login único de verdade”, concentrando o risco no aparelho (que já guarda o token do Jellyfin).

## Princípios do produto

1. **Família primeiro:** linguagem simples, sem jargão de Radarr/Sonarr/Prowlarr.
2. **Assistir e pedir em poucos toques:** buscar, pedir, acompanhar, continuar assistindo.
3. **Admin separado:** ferramentas de gestão só no modo administrador.
4. **Um app, não um navegador:** pedidos e reprodução dentro do app; browser só para administração avançada do Seerr.
5. **Funcionar fora de casa:** o app não deve depender de Tailscale para o uso normal da família.
6. **Direto play sempre que possível:** o Pi 4 não é bom de transcode.

## Escopo

### MVP

- Login com Jellyfin. **Usuário/senha é o caminho principal**, porque é o único que abre a sessão do Seerr por pessoa. Quick Connect fica como entrada secundária “só assistir” (sem aba de Pedidos).
- Início com “continuar assistindo” e “adicionados recentemente”.
- Biblioteca com filmes, séries e animes; busca e filtros básicos.
- Detalhe do item com temporadas/episódios.
- Player com direct play, legendas, faixas de áudio, retomada e progresso.
- Pedidos: buscar no Seerr, pedir, acompanhar ativos e histórico.
- Legendas: quota, pendências e fila no servidor.
- Casa: status do Pi, armazenamento, serviços e Wake-on-LAN.
- Modo família e modo admin.
- Acesso remoto: Jellyfin pelo Funnel e pedidos/status pelo BFF via Cloudflare Tunnel.

### Fase 2

- Downloads offline.
- Chromecast/AirPlay.
- Notificações push (“seu pedido chegou”).
- Widgets de tela inicial.
- App para Android TV.
- Recomendações e “minha lista”.
- Múltiplos servidores Jellyfin.
- Perfis infantis com limites.

## Decisão de plataforma

### Decisão: Android-only no MVP

**Decidido em 2026-11-24.** Usar **Kotlin + Jetpack Compose + Media3/ExoPlayer**, com HTTP via **Retrofit + modelos próprios**. O SDK Kotlin do Jellyfin fica como opção para quando WebSocket/sync de sessão entrarem — a API dele ainda muda entre versões menores e isso atrapalha um app deste tamanho.

Motivos:

- Media3 é o player maduro do Android (mesmo motor usado pelos apps de vídeo);
- maior controle sobre player, cache, downloads e UI;
- o app pode evoluir para Android TV reutilizando a camada de dados;
- o ecossistema de TVs da casa tende a Android TV/Fire TV;
- Android-only reduz o trabalho pela metade em relação a KMP/Flutter.

### iOS (fase 2, fora do MVP)

A plataforma do MVP está decidida e não bloqueia o início. Quando o iOS entrar, a escolha será entre:

- **Dois apps nativos:** Android (Kotlin) + iOS (Swift/SwiftUI, Swiftfin como referência). Mais trabalho, melhor experiência.
- **Kotlin Multiplatform:** compartilha lógica; Android com Compose, iOS com Compose/SwiftUI.
- **Flutter:** um código para os dois, mas usa a API REST direto e um player de terceiros.

A camada de dados do app Android deve nascer isolada (repositórios + modelos sem dependência de UI) para não inviabilizar KMP depois.

## Arquitetura

```text
┌──────────────────────────┐
│ App mobile               │
│  Início / Biblioteca     │
│  Player / Pedidos        │
│  Legendas / Casa         │
└────────────┬─────────────┘
             │ HTTPS (LAN primeiro, público como fallback)
     ┌───────┴─────────────────────────┐
     │                                 │
┌────▼─────────────────┐      ┌────────▼─────────────────┐
│ Jellyfin público     │      │ BFF `/api/v1`            │
│ Funnel → :8096       │      │ Cloudflare Tunnel → :8099│
│ catálogo e playback  │      │ auth + agregação         │
└────┬─────────────────┘      └────┬─────────────────────┘
     │                             │
┌────▼─────────┐        ┌──────────▼──────────────────────┐
│ Jellyfin     │        │ media-agent (mesmo processo)    │
│ Pi 4         │        │ :8097 legado (allowlist de IP)  │
└──────────────┘        │ Radarr / Sonarr / Bazarr / Seerr│
                        └─────────────────────────────────┘
```

### Decisões de arquitetura

- **Jellyfin:** o app fala direto com a API do Jellyfin para catálogo, imagens, playback e progresso. O BFF não intermedeia vídeo.
- **BFF:** evolui o `media-agent` em Python, mas em **processo próprio** com a mesma imagem, para não arriscar as rotas do Homepage. Dois listeners: `:8099` público preso a `127.0.0.1` (só `/api/v1/*`, atrás do cloudflared) e `:8092` de admin preso ao IP da LAN. O legado continua na `:8097`, intocado.
- **Segredos:** chaves de Radarr/Sonarr/Bazarr/Seerr ficam no servidor. O app nunca recebe essas chaves. A API key do Seerr é *god-mode* e não pode ir para log.
- **Auth:** Jellyfin é o IdP. O BFF valida o token em `GET /Users/Me` com cache curto e deriva `userId` e `IsAdministrator` de lá.
- **Admin:** rotas de admin exigem `IsAdministrator` vindo do Jellyfin; o modo família só esconde a UI, não é a única barreira de segurança.
- **Acesso remoto:** o vídeo sai pelo Funnel, o JSON sai pelo Cloudflare Tunnel. Nunca expor `8097` publicamente.

## Autenticação e sessão (detalhado)

### Fluxo de login

1. App coleta **usuário e senha** do Jellyfin.
2. App chama `POST /Users/AuthenticateByName` → recebe `AccessToken` e `User.Id`.
3. App envia o `AccessToken` ao BFF (`POST /api/v1/session`).
4. BFF valida em `GET /Users/Me` e guarda `userId`, `nome` e `isAdmin`.
5. **Só para o Seerr:** o app manda a senha **uma única vez** para o BFF (sobre TLS, nunca logada). O BFF chama `POST /api/v1/auth/jellyfin` com `{username, password}` no Seerr, recebe o cookie `connect.sid` e o guarda **cifrado em repouso** (Fernet, chave no `.env`, arquivo `600`), mapeado a `(userId, deviceId)`.
6. O BFF devolve ao app um **token de sessão próprio** (HMAC, TTL curto, renovável). O app guarda a senha cifrada no **Keystore do Android** (D7) apenas enquanto “manter conectado” estiver ligado — nunca em texto puro e nunca no servidor.

### Regras

- O BFF **nunca** persiste a senha. A cópia no aparelho (Keystore, D7) existe só para renovar a sessão do Seerr sem perguntar de novo.
- Cookie do Seerr expira conforme o TTL do Seerr. Se expirar, o app **renova sozinho** com a senha do Keystore; só pede senha se “manter conectado” estiver desligado ou se a senha tiver mudado no Jellyfin.
- Sessões são **por dispositivo**, não por usuário: duas TVs podem estar logadas ao mesmo tempo.
- Rate limit e backoff no login do BFF; falhas não revelam se o usuário existe.
- Quick Connect continua disponível como “entrar só para assistir”: cria sessão do BFF com `seerrLinked=false`, e a aba Pedidos pede a senha na primeira utilização.
- Rotas de admin exigem, ao mesmo tempo, `IsAdministrator` (Jellyfin) **e** origem LAN/Tailscale (D6). Fora disso, `403 admin_lan_only`.
- Revogação: deslogar no Jellyfin invalida o token; o BFF apaga o cookie do Seerr correspondente em `POST /api/v1/session/logout`.

### Riscos específicos desta escolha

| Risco | Impacto | Mitigação |
|---|---|---|
| Senha do Jellyfin transita e é usada para abrir sessão no Seerr | Médio | TLS ponta a ponta, senha em memória apenas durante a troca, `Cache-Control: no-store`, nunca em log/telemetria |
| **Senha guardada no Keystore (D7)** | Médio | Cifrada pelo Android no armazenamento privado do app; opção “manter conectado” desligável; nunca em backup automático (`allowBackup=false`) |
| Comprometimento do Pi expõe cookies do Seerr em repouso | Médio | Cifrar com chave fora do git, permissão `600`, e documentar que o Pi passa a ser alvo de credencial |
| Vazamento da API key do Seerr (god-mode, ignora quota e aprovação) | Alto | Chave só no servidor, nunca em resposta, nunca em log; rotas que usam a chave são separadas das rotas por usuário |
| Sessões do Seerr quebram em silêncio após atualização da imagem | Médio | Fixar a versão da imagem `seerr/seerr`; healthcheck que testa 1 login por usuário; erro explícito no app |
| API do Seerr mudar de `/auth/jellyfin` | Médio | Spike da etapa 0 valida o endpoint e o formato; teste de contrato no BFF |

## Bibliotecas e licenças

| Biblioteca | Uso | Licença |
|---|---|---|
| Jellyfin Kotlin SDK | opcional: WebSocket/sync de sessão | MPL-2.0 |
| Media3 / ExoPlayer | reprodução, HLS, legendas, áudio | Apache-2.0 |
| Jetpack Compose | UI Android | Apache-2.0 |
| Coil | carregamento de imagens | Apache-2.0 |
| Retrofit + OkHttp | HTTP (decisão do MVP) | Apache-2.0 |
| Hilt | injeção de dependência | Apache-2.0 |
| Jellyfin server | API | GPL-2.0 (usar a API não obriga o app a ser GPL) |
| Seerr (`seerr/seerr`) | API de pedidos + auth | GPL-3.0 (uso via API, sem fork) |
| App Android do Jellyfin | referência de comportamento | GPL-3.0 — **não** fazer fork neste plano |

> Este plano reutiliza **bibliotecas**, não o app Android inteiro. Se no futuro a opção for “um app só” via fork, a licença GPL-3.0 passa a valer para o app combinado.

## Telas e funcionalidades

| Tela | MVP | Depois |
|---|---|---|
| Início | continuar assistindo, recentes, atalhos, status | recomendações, “minha lista” |
| Biblioteca | filmes/séries/animes, busca, gênero | filtros avançados, coleções |
| Item | sinopse, capa, temporadas/episódios, play | trailer, elenco, similares |
| Player | direct play, legendas, áudio, retomar, progresso | offline, casting, PiP |
| Pedidos | buscar/Seerr, pedir, ativos, histórico | aprovação, prioridade, notificações |
| Legendas | quota, faltantes, fila no servidor | sincronização automática, múltiplos idiomas |
| Casa | CPU/RAM/temp, storage, serviços, WOL | histórico, alertas, migração |
| Perfil | usuários da família, modo admin, servidor, qualidade | limites por criança, downloads |

### Início (estilo Netflix)

- Hero “continuar assistindo” com progresso real do Jellyfin.
- Fileiras: “Adicionados recentemente”, “Filmes”, “Séries”, “Animes”.
- Busca global.
- Atalhos: pedir filme/série, legendas, ligar PC.
- Status discreto: “Tudo funcionando”.

### Player

- Direct play como padrão.
- Se precisar transcode, usar HLS e limitar a qualidade.
- Legendas: preferir faixas externas; converter para VTT quando necessário.
- Faixas de áudio e sincronização.
- Retomada e progresso a cada 10–30 s; enviar ao pausar/parar.
- Bloquear rotação indevida, manter tela ligada, tratar foco de áudio.
- Erros claros: “formato não suportado”, “sem banda”, “servidor offline”.

### Pedidos

- Buscar no Seerr **com a sessão da pessoa**, nunca com a chave de admin.
- Esconder “Pedir” quando `mediaInfo.status == 5` (disponível): o Seerr aceita o pedido e cria um registro inútil, não devolve `409`.
- “Cancelar” só aparece se o usuário tiver `MANAGE_REQUESTS`; sem isso o Seerr responde `401` e o app deve orientar a falar com o admin.
- Mostrar o status vindo do Seerr por pedido (pendente/aprovado/processando/disponível/falhou).

## Integrações

### Jellyfin

- Auth: Quick Connect (`/QuickConnect/Initiate`, `/QuickConnect/Connect`) ou `/Users/AuthenticateByName`.
- Usuário atual: `/Users/Me`.
- Continuar assistindo: `/Users/{userId}/Items/Resume`.
- Recentes: `/Users/{userId}/Items/Latest`.
- Busca: `/Users/{userId}/Items?searchTerm=...`.
- Detalhe: `/Users/{userId}/Items/{itemId}`.
- Temporadas/episódios: `/Shows/{seriesId}/Seasons`, `/Shows/{seriesId}/Episodes`.
- Imagens: `/Items/{itemId}/Images/Primary`.
- Playback: `POST /Items/{itemId}/PlaybackInfo`.
- Progresso: `/Sessions/Playing`, `/Sessions/Playing/Progress`, `/Sessions/Playing/Stopped`.

> Validar a versão da API do Jellyfin instalado. Com Retrofit, os endpoints são chamados direto.

### Seerr

- **Identidade: sessão por pessoa (D4).** O BFF chama `POST /api/v1/auth/jellyfin` com `{username, password}` uma vez, guarda o cookie `connect.sid` cifrado por `userId` e reaproveita enquanto a sessão viver.
- Busca e criação de pedidos via API REST **com o cookie da pessoa**, não com a API key.
- A API key de admin fica restrita a rotas administrativas do BFF (importar usuários, saúde do serviço).
- Status agregado continua vindo do `media-agent` (`/arr/pending?status=1`, `/requests`), que já usa a chave no servidor — mas **somente leitura**. Histórico e criação de pedido por pessoa usam o cookie dela.
- Admin do Seerr (usuários, configurações) continua no navegador.
- **Ponto do spike:** confirmar o endpoint de login, os atributos do cookie (`HttpOnly`, `SameSite`, TTL) e o comportamento de renovação na versão `seerr/seerr` instalada. O Seerr substituiu o Jellyseerr em 2026-02 e o login antigo por Jellyfin falha — não assumir compatibilidade.

### media-agent

- `/arr/pending?status=1` — pedidos ativos, progresso e erros.
- `/requests` — ativos e histórico.
- `/subs/quota` — quota do OpenSubtitles.
- `/bazarr` — proxy da API do Bazarr.
- `/status`, `/storage` — saúde do Pi e armazenamento.
- `/imports/active`, `/migration/status` — importações.
- `/sonarr/*` — adicionar série, episódios, monitoramento.
- `/arr/*` — buscar, trocar perfil, verificar PT-BR.
- `gaming-agent` — WOL e status do PC.

### Formato do BFF

- Rotas novas: `GET /api/v1/me`, `GET /api/v1/status`, `GET /api/v1/requests`, `POST /api/v1/requests`, `GET /api/v1/subs/quota`, `GET /api/v1/bazarr/*`, `GET /api/v1/sonarr/*`, `POST /api/v1/session`, `POST /api/v1/session/logout`.
- Erros: `{"code": "...", "message": "..."}` com HTTP coerente (`401 seerr_session_expired`, `403 admin_required`, `409 already_requested`).
- Rotas legadas ficam em `:8097` para o Homepage; `:8099` serve só `/api/v1`.

### Mudanças necessárias no backend

- [x] **Listener novo `:8099`** servindo só `/api/v1/*` (rotas legadas ficam no `:8097`).
- [x] Middleware de auth: valida token Jellyfin em `/Users/Me`, cache 5–10 min, cache negativo para revogado.
- [x] `POST /api/v1/session` e `/session/logout`: troca senha→cookie do Seerr, cifra em repouso, sessão HMAC própria.
- [x] `GET /api/v1/me`: identidade, `isAdmin`, `seerrLinked`.
- [x] Proxy do Seerr por usuário (não com a API key) para busca/pedido/histórico.
- [ ] Cancelar pedido só com `MANAGE_REQUESTS`; esconder “Pedir” para mídia disponível (`status == 5`). *(app)*
- [x] Rotas de admin separadas, checando `IsAdministrator` do Jellyfin **e** origem LAN/Tailscale.
- [ ] `allowBackup=false` e Keystore no app (D7). *(app)*
- [ ] Fila de legendas no servidor (hoje é `localStorage`).
- [ ] Contrato OpenAPI enxuto dos endpoints usados pelo app + erros `{code, message}`.
- [x] Rate limit no login e nos endpoints caros; logs sem senha, token ou API key.
- [x] `cloudflared` instalado e conectado no Pi (4 conexões QUIC). Falta o hostname, que depende do DNS.
- [ ] Notificações (ntfy primeiro; FCM só se valer o esforço).

## Etapas

A ordem segue o risco, não a camada: primeiro o que pode mudar a abordagem, depois a UI.

| Etapa | Duração | Entregável | Critério de saída |
|---|---|---|---|
| **0. Spike de API** | ~~2–3 dias~~ **concluída** | `spike_seerr_auth.py` rodado no Pi; plano C confirmado | OK: `auth/jellyfin`, cookie 30d, isolamento por pessoa |
| **1a. Auth no BFF** | ~~1 semana~~ **concluída** | `api_v1.py` + 37 testes; listener `8099`/`8092` | 401 sem token; 200 com token; Homepage intacto na `8097` |
| **1b. Túnel** | 2 dias | `cloudflared` + hostname público | `curl` do 4G funciona |
| **2. Vertical slice** | 1 semana | App mínimo: login, 1 fileira, 1 player Media3 direct play | 30 min de HEVC sem transcode; progresso salvo |
| **3. Fundação** | 1–2 semanas | Gradle, Compose, Hilt, Retrofit, dois endereços (LAN/público), CI + APK | APK instala, loga e alterna de rede |
| **4. Catálogo** | 2 semanas | Home, biblioteca, busca, detalhe, temporadas/episódios | Navegação completa |
| **5. Player de produção** | 2–3 semanas | Retomada, faixas, legendas externas, erros, PiP | 30 min sem buffering na rede real |
| **6. Pedidos/Legendas/Casa** | 2 semanas | Telas sobre o BFF, inclusão de série, quota e fila | Pedir, acompanhar e ver status |
| **7. Distribuição** | 1 semana | APK assinado + update checker ou Play interno | Família instala sem cabo |

**Total estimado:** 13–15 semanas para um desenvolvedor (a sessão por pessoa do Seerr adiciona ~1 semana sobre a estimativa anterior).
**MVP utilizável (login + catálogo + player + pedidos):** 7–9 semanas.

### Etapa 0 — como rodar o spike

O script é `deploy/raspberry/media-agent/spike_seerr_auth.py` (só stdlib, não altera nada). No Pi:

```bash
JELLYFIN_URL=http://127.0.0.1:8096 \
SEERR_URL=http://127.0.0.1:5055 \
SEERR_CONFIG=<CONFIG_ROOT>/seerr/settings.json \
SPIKE_USER=<usuario> SPIKE_PASS='<senha>' \
python3 spike_seerr_auth.py
```

O que olhar no veredito:

- `seerr_per_user_login` OK, com `connect.sid` `HttpOnly` → **plano C viável**.
- `rolling: sim` → a sessão renova a cada uso. `não` → TTL fixo, e o Keystore (D7) passa a ser obrigatório para cumprir “login único”.
- `pedidos pelo cookie` menor que `pela API key` → confirma que a visão por pessoa é diferente da visão de admin.
- `--search <termo>` valida leitura; `--request movie:<tmdbId>` cria um pedido **real** (pede confirmação).
- `--json` guarda o resultado para comparar depois de atualizar a imagem do Seerr.

Código de saída 0 = os quatro checks essenciais passaram.

### Resultado da etapa 0 (medido no Pi em 2026-11-24)

Rodado com o usuário de família `<USUARIO_FAMILIA>` contra o ambiente real:

| Item | Medido |
|---|---|
| Jellyfin | `10.11.11`, servidor `jellyfinCasa` |
| Seerr | `3.5.1`, `mediaServerType=2` (Jellyfin), `mediaServerLogin=true` |
| `POST /api/v1/auth/jellyfin` | **funciona** com usuário/senha; `401 INVALID_CREDENTIALS` quando erra |
| Cookie | `connect.sid`, `HttpOnly`, `SameSite=Lax`, `Secure=false` (LAN HTTP), `Path=/`, `Max-Age` = 30 dias |
| Renovação | **não** — TTL fixo contado do login. **D7 (Keystore) é obrigatório** para manter “login único” |
| Isolamento por pessoa | cookie de `<USUARIO_FAMILIA>` vê 16 pedidos; chave de admin vê 26 |
| Mapeamento | 3 usuários Jellyfin ↔ 3 usuários Seerr, `jellyfinUserId` idêntico |
| Pedido com o cookie | `201`, criado com a identidade da pessoa |
| Cancelar pedido | usuário de família recebe `401` (falta `MANAGE_REQUESTS`) |
| Mídia já disponível | pedido retorna **`201`**, não `409` |

**Status: etapa 0 concluída. Plano C confirmado.**

Duas consequências que entram no app:

1. **Não usar `409` como sinal de “já existe”.** O Seerr aceita pedido de mídia já disponível e cria um registro. O app deve esconder/desabilitar “Pedir” quando `mediaInfo.status == 5`, consultando o estado antes.
2. **“Cancelar pedido” depende da permissão do usuário no Seerr**, não da UI. Sem `MANAGE_REQUESTS`, o app recebe `401`; a tela deve esconder a ação e explicar “peça ao admin para cancelar”.

### Etapa 1a — implementada (2026-11-24)

Arquivos em `deploy/raspberry/media-agent/`:

| Arquivo | Papel |
|---|---|
| `api_v1.py` | BFF completo, stdlib apenas |
| `test_api_v1.py` | 37 testes contra Jellyfin/Seerr falsos |

Rodar os testes:

```bash
cd deploy/raspberry/media-agent
python3 -m unittest test_api_v1 -v
```

Rodar o BFF:

```bash
V1_STATE_DIR=/state python3 api_v1.py \
  --host 127.0.0.1 --port 8099 \
  --admin-host <LAN_IP> --admin-port 8092
```

> **Portas:** o `gaming-agent` foi movido de `8099` para **`8100`** (LAN), liberando `8099` para o BFF. A `8098` pública do gaming não mudou. O BFF usa **`8099` público** (preso a `127.0.0.1`, atrás do cloudflared) e **`8092` admin** (preso ao IP da LAN).

O que está pronto:

- `POST /api/v1/session` — troca o `AccessToken` do Jellyfin por um token HMAC próprio (1 h, renovável).
- `POST /api/v1/session/seerr` — vincula a conta do Seerr por pessoa; cookie `connect.sid` **cifrado em repouso** (chave `0600` em `/state`).
- `GET /api/v1/me`, `POST /api/v1/session/logout`.
- `GET/POST /api/v1/requests` e `GET /api/v1/search` usando **o cookie da pessoa**, não a API key.
- `GET /api/v1/house` — status do Pi + storage, recortados (sem expor internos).
- `GET /api/v1/subs/quota` — quota da OpenSubtitles **sem** `username`/`user_id` da conta compartilhada.
- `GET /api/v1/admin/downloads` — fila do Radarr/Sonarr com progresso, só no listener de admin.
- Listener de **LAN** (`:8091`, rotas públicas, sem admin) para o app funcionar em casa sem depender do DNS.
- Rate limit por IP: `20/min` no login, `240/min` no resto (`429 rate_limited` + `Retry-After`).
- `GET /api/v1/admin/ping` — só existe no listener de admin, exige `IsAdministrator` e origem na LAN/Tailscale.
- Cache de validação do Jellyfin (5 min) e cache negativo (30 s).
- Erros `{code, message}`: `invalid_token`, `seerr_session_expired`, `seerr_not_linked`, `admin_lan_only`, etc.

O que falta para entrar no ar: copiar os dois arquivos para `${CONFIG_ROOT}/media-agent`, adicionar o serviço `media-bff` no compose e apontar o `cloudflared` para `127.0.0.1:8099` (etapa 1b).

> **Redeploy:** `MEDIA_STACK.md` §Comandos úteis → **Redeploy do BFF (`media-bff`)**. Só código: `cp` do `api_v1.py` + `docker compose restart media-bff`; compose mudou: `up -d media-bff`; imagem mudou: `build media-agent` + `--force-recreate`.

**Status: rodando em produção** (container `media-bff`, volume Docker `media-bff-state`). Verificado no Pi: `/api/v1/status` → `200` em `127.0.0.1:8099`; admin → `401` em `<LAN_IP>:8092`; admin → `404` no listener público.

> **Armadilha do NTFS:** `<CONFIG_ROOT>` é `fuseblk` (NTFS) e **ignora chmod** — todo arquivo aparece `775`, mesmo pedindo `600`. Por isso o estado do BFF (chaves + sessões cifradas) foi para o volume Docker `media-bff-state`, em ext4, onde `0600` funciona de verdade.

> **Porta do gaming:** o `gaming-agent` foi movido de `8099` para `8100` (LAN). A `8098` pública não mudou. O Homepage já aponta para `8100` (`deploy/homepage/src/shared.js` e o `custom.js` servido em `/api/config/custom.js`).

### Etapa 1b — concluída (2026-11-25)

- Domínio `<DOMAIN>` na Cloudflare, NS `arch.ns.cloudflare.com` / `deb.ns.cloudflare.com`.
- `cloudflared` instalado e conectado no Pi (4 conexões QUIC), token em `/etc/cloudflared/token` (`600 root`).
- Rota `<BFF_HOST> → http://127.0.0.1:8099` criada; Registro.br delegou para `arch/deb.ns.cloudflare.com`; TLS Let's Encrypt válido.
- `check_public.py https://<BFF_HOST>` → **9/9** (TLS 1.3, status 200, 401 sem token, Jellyfin alcançável, admin 404).
- **Resolvido (2026-11-25):** o `403 error code: 1010` vinha de uma regra de **User Agent Blocking** para `Python-urllib` — produto fora da fase de custom rules, por isso o Skip não pegava. Regra removida; `Python-urllib` responde 200 e o `check_public.py` segue 9/9.
- **Always Use HTTPS:** ativo (HTTP → `301` para HTTPS).

**Funnel do Jellyfin:** `tailscale funnel --bg 8096` ativo em `https://<PI>.<TAILNET>.ts.net` (validado pelo IP de ingress público, não só pelo tailnet).

**Integração do app (2026-11-25):** o app Android `FamiliaApp 0.1.0` já autenticou como `<USUARIO_FAMILIA>`, reproduziu mídia com progresso (`/Sessions/Playing`), vinculou o Seerr (`POST /session/seerr` 200) e consumiu `requests`, `search`, `house` e `subs/quota` pelo listener de LAN.

**Correção:** `BffServer.handle_error` passou a ignorar `ConnectionResetError`/`BrokenPipeError` (Cloudflare e o app fecham keep-alive o tempo todo; o log enchia de traceback sem erro real).
- Verificador pronto: `check_public.py` faz 9 checks sem senha (status, 401, Jellyfin alcançável, admin ausente no público).
- Handoff do app: `plans/APP_ANDROID_ESPECIFICACAO.md` (contratos, marcos, armadilhas).

### Acesso remoto do Jellyfin com domínio próprio (decisão pendente)

- O Funnel **não aceita domínio próprio**: a documentação da Tailscale diz que ele só usa nomes `*.ts.net`.
- A casa está atrás de **CGNAT**: o WAN do roteador é `100.100.7.75` e o IP público `<IP_PUBLICO>` é o NAT da operadora. Portanto **port forwarding não funciona**, nem com acesso ao roteador (UPnP responde, mas é inútil para entrada).
- Opções para usar `<DOMAIN>` no Jellyfin:
  - **Cloudflare Tunnel** (`jellyfin.<DOMAIN>`) — grátis, funciona atrás de CGNAT, mas o vídeo passa pelo CDN (cláusula 2.8 do contrato).
  - **VPS + WireGuard** — sem risco de contrato, custa um VPS.
  - **Funnel** (atual) — grátis e sem risco, mas a URL é `*.ts.net`.
- URLs medidas: `https://<DOMAIN>` (21 chars), `https://jellyfin.<DOMAIN>` (30), `https://<PI>.<TAILNET>.ts.net` (35).
- Decisão adiada; o app e a TV usam o Funnel por enquanto.

## Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| Pi 4 não transcode bem | Alto | Direct play, limites de bitrate, testar codecs reais |
| Upload da casa baixo | Alto | Testar Funnel; fallback gateway/VPS; limitar qualidade |
| **Sessão do Seerr por pessoa** | Alto | **Confirmado no spike**: login por usuário funciona, cookie 30d fixo |
| **Jellyfin fora derruba o BFF** | Alto | Cache de token validado; health público separado; `/status` não depende de auth |
| **Cloudflare com vídeo** | Alto | Vídeo fica no Funnel; Cloudflare só recebe JSON do `8099` |
| **API key do Seerr é god-mode** | Alto | Só no servidor, nunca em log; rotas por usuário não usam a chave |
| Senha do Jellyfin transita até o BFF | Médio | TLS, uso único em memória, `no-store`, nada em log |
| API/SDK do Jellyfin mudar | Médio | Fixar versão, testes de contrato, camada de abstração |
| Player com muitos formatos | Médio | Media3 + perfil de dispositivo; testar HEVC/AV1/legendas ASS |
| Anime com ASS exige burn-in | Médio | Aceitar ASS simples no Media3; senão, transcode controlado com aviso |
| App store/distribuição | Baixo | APK direto + update checker; Play interno só se necessário |

## Estrutura sugerida

```text
apps/mobile/
  app/
  core/
    network/
    auth/
    design/
    player/
  feature/
    home/
    library/
    item/
    player/
    requests/
    subtitles/
    house/
    profile/
server/
  api/          # BFF /api/v1
  media-agent/  # evolução do agente atual
```

> O `server/` do diagrama é conceitual. Na prática, o BFF é `deploy/raspberry/media-agent/api_v1.py`, roda em container próprio com a mesma imagem e o mesmo `/state`, e o app entra em `apps/mobile/`.

## Critérios de conclusão do MVP

- [x] Um membro da família faz login sem abrir o navegador. *(app `FamiliaApp 0.1.0`, 2026-11-25)*
- [ ] Encontra um título, vê detalhes e assiste em 1080p direct play. *(reproduziu; falta confirmar `DirectPlay` no aparelho)*
- [ ] Sai no meio e retoma do ponto correto.
- [ ] Legendas PT-BR funcionam.
- [x] **Cada pessoa pede no Seerr com a própria identidade**, e o pedido aparece com o nome dela. *(vínculo e busca observados)*
- [ ] **Login único de verdade:** depois do primeiro login, Pedidos e Casa não pedem senha de novo; a renovação usa o Keystore em silêncio.
- [x] Vê a quota e busca legendas. *(quota consumida pelo app)*
- [ ] Admin vê serviços, storage e importações **apenas** na LAN/Tailscale.
- [ ] Funciona na LAN e fora de casa. *(LAN ok; Funnel ativo, falta teste no 4G)*
- [x] Nenhuma chave de Radarr/Sonarr/Bazarr/Seerr e nenhuma senha ficam no app.
- [ ] 30 minutos de reprodução sem buffering relevante na rede de teste.

## Decisões em aberto

- FCM/APNs ou ntfy para push? (recomendação: ntfy no MVP)
- O app precisa de Android TV no MVP ou depois?
- Domínio e hostname definitivos para o Cloudflare Tunnel.
- Downloads offline entram no MVP ou fase 2? (recomendação: fase 2)
- Quais celulares/TVs entram no teste de codecs da etapa 2.
- Limite de quantas sessões do Seerr o BFF mantém ativas por pessoa.
