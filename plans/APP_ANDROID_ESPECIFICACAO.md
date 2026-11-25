# App Android — especificação de implementação (handoff)

> **Para quem:** a instância do opencode na máquina com Android Studio.
> **Fonte da verdade do backend:** `deploy/raspberry/media-agent/api_v1.py` (BFF `:8091` na LAN, `:8099` público atrás do Cloudflare Tunnel) e o Jellyfin `10.11.11`.
> **Plano de produto:** `plans/PLANO_APP_NATIVO_JELLYFIN.md`.
> **Status:** backend pronto e no ar; app ainda não existe.

---

## 0. Prompt pronto para colar no opencode

```text
Implemente o app Android descrito em APP_ANDROID_ESPECIFICACAO.md, começando pelo
Marco 1 (fatia vertical). Leia o documento inteiro antes de escrever código.
Regras inegociáveis:
- nenhuma API key de Radarr/Sonarr/Bazarr/Seerr no app;
- pedidos e Casa falam só com o BFF, nunca direto com Seerr/Radarr;
- catálogo e playback falam direto com o Jellyfin;
- direct play como padrão, sem transcode silencioso;
- "manter conectado" usa Keystore e allowBackup=false.
Ao terminar o Marco 1, rode ./gradlew test e descreva como testar no aparelho.
```

---

## 1. O que já está pronto (não reimplementar)

| Peça | Onde | Estado |
|---|---|---|
| BFF `/api/v1` | `api_v1.py`, container `media-bff` | no ar, 50 testes (1 falha só no Windows) |
| Auth Jellyfin + sessão HMAC | `POST /api/v1/session` | ok |
| Sessão do Seerr por pessoa | `POST /api/v1/session/seerr` | ok, cookie 30 d |
| Pedidos (listar/criar/buscar/descobrir) | `/api/v1/requests`, `/api/v1/search`, `/api/v1/discover` | ok |
| Casa, serviços e legendas | `/api/v1/house`, `/api/v1/services`, `/api/v1/pc`, `/api/v1/subs/quota`, `/api/v1/subs/queue` | ok |
| Download/importações (admin) | `/api/v1/admin/downloads` | ok, só LAN |
| Túnel | `cloudflared` + `<BFF_HOST>` | rota criada, DNS em propagação |

Endereços:

| Uso | URL |
|---|---|
| Jellyfin (LAN) | `http://<LAN_IP>:8096` |
| BFF (LAN) | `http://<LAN_IP>:8091` |
| BFF (público) | `https://<BFF_HOST>` (aguardando DNS) |
| Jellyfin (remoto) | **ainda não existe** — depende do `PLANO_FUNNEL_TAILSCALE.md` |

> **Consequência:** no MVP o vídeo funciona em casa (LAN). Playback fora de casa só depois de configurar o Funnel/reverse proxy do Jellyfin. Não bloqueie o app por causa disso; trate a URL do Jellyfin como configurável.

---

## 2. Projeto e dependências

Criar um projeto Android novo, **módulo único `app`** (não modularizar no dia 1).

- Kotlin + Jetpack Compose (Material 3), `minSdk 26`, `targetSdk` atual do Studio.
- AGP/Kotlin/Compose: usar as versões do template do Android Studio e o `libs.versions.toml`; não fixar versões antigas.
- Bibliotecas: Retrofit + OkHttp + kotlinx.serialization (ou Moshi), Coil, Hilt, Navigation Compose, DataStore, `androidx.security:security-crypto`, Media3 (`exoplayer`, `exoplayer-hls`, `ui`, `session`).

`AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
<uses-permission android:name="android.permission.WAKE_LOCK" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
<!-- fase 2: FOREGROUND_SERVICE_MEDIA_PLAYBACK + MediaSessionService -->
<application
    android:allowBackup="false"
    android:networkSecurityConfig="@xml/network_security_config"
    ...>
```

`res/xml/network_security_config.xml` — HTTP só na LAN, nunca na internet:

```xml
<network-security-config>
  <base-config cleartextTrafficPermitted="false" />
  <domain-config cleartextTrafficPermitted="true">
    <domain includeSubdomains="false"><LAN_IP></domain>
    <domain includeSubdomains="false">127.0.0.1</domain>
  </domain-config>
</network-security-config>
```

Estrutura de pacotes:

```text
data/remote/jellyfin   JellyfinApi, DTOs, interceptor X-Emby-Token
data/remote/bff        BffApi, DTOs, interceptor Authorization Bearer
data/repo              AuthRepository, CatalogRepository, RequestRepository, HouseRepository
core/auth              SessionStore (DataStore + Keystore), SessionManager (renovação)
core/net               ServerConfig (LAN/público), fallback, erros
ui/login ui/home ui/library ui/item ui/player ui/requests ui/house ui/profile
di                     módulos Hilt
```

---

## 3. Configuração de servidor (fazer antes de tudo)

O app guarda **dois pares de URLs** e escolhe em tempo de execução:

| Chave | LAN | Público |
|---|---|---|
| Jellyfin | `http://<LAN_IP>:8096` | (Funnel, quando existir) |
| BFF | `http://<LAN_IP>:8091` | `https://<BFF_HOST>` |

- Tela "Conexões" no Perfil para editar e testar (`GET /System/Info/Public` no Jellyfin, `GET /api/v1/status` no BFF).
- Seleção: tentar LAN com timeout de ~1,5 s; se falhar, público. Guardar a escolha e revalidar ao abrir o app.
- `GET /api/v1/status` não exige token: serve de health check.

---

## 4. Autenticação (fluxo exato)

### 4.1 Login

1. `POST {jellyfin}/Users/AuthenticateByName`
   Header: `Authorization: MediaBrowser Client="FamiliaApp", Device="<Build.MODEL>", DeviceId="<uuid>", Version="0.1.0"`
   Body: `{"Username":"<USUARIO_FAMILIA>","Pw":"..."}`
   Resposta: `{"User":{...},"AccessToken":"...","ServerId":"..."}`
2. Guardar `AccessToken` (Keystore/EncryptedSharedPreferences) e `User.Id`.
3. `POST {bff}/api/v1/session` body `{"access_token":"...","device_id":"<uuid>"}`
   Resposta:

```json
{"token":"<bff>","expires_at":"2026-11-24T23:00:00+00:00",
 "user":{"id":"<USER_ID>","name":"<USUARIO_FAMILIA>","is_admin":false},
 "seerr_linked":false,"seerr_expires_at":null}
```

4. Vincular o Seerr **uma vez** (obrigatório para Pedidos):
   `POST {bff}/api/v1/session/seerr` com `Authorization: Bearer <bff>`
   body `{"username":"<USUARIO_FAMILIA>","password":"...","device_id":"<uuid>"}`
   Resposta `{"seerr_linked":true,"seerr_expires_at":"..."}`
5. Se "manter conectado", cifrar a senha com chave do Android Keystore (AES/GCM) e guardar só o blob.

`device_id`: UUID v4 gerado no primeiro uso e persistido. **É a chave do vínculo do Seerr** — se mudar, o usuário perde o vínculo.

### 4.2 Renovação e erros

| Situação | Código | Ação do app |
|---|---|---|
| BFF token venceu (1 h) | `401 session_expired` | `POST /session` de novo com o `AccessToken` do Jellyfin |
| Token do Jellyfin morreu | `401 invalid_token` | relogin silencioso com a senha do Keystore; senão, tela de login |
| Cookie do Seerr venceu (30 d) | `401 seerr_session_expired` | `POST /session/seerr` com a senha do Keystore; senão, pedir senha |
| Seerr não vinculado | `409 seerr_not_linked` | abrir o fluxo de vínculo |
| Muitas tentativas | `429 rate_limited` | respeitar `Retry-After` (segundos) |
| Admin fora da LAN | `403 admin_lan_only` | esconder a ação |

Regras: um único `Authenticator`/interceptor centraliza isso; telas nunca tratam 401 individualmente. Se a senha não estiver no Keystore, **só então** mostrar prompt.

### 4.3 Logout

`POST {bff}/api/v1/session/logout` (Bearer) → apaga o vínculo do Seerr daquele aparelho. Depois limpar DataStore/Keystore. O token do Jellyfin continua válido no servidor; opcionalmente chamar `POST /Sessions/Logout` no Jellyfin.

Quick Connect: **fase 2**. Não entrega senha, então não serve para o Seerr.

---

## 5. Contratos do Jellyfin

Base = URL do Jellyfin. Header em todas: `X-Emby-Token: <AccessToken>`.

| Uso | Chamada |
|---|---|
| Views (bibliotecas) | `GET /Users/{userId}/Views` |
| Continuar assistindo | `GET /Users/{userId}/Items/Resume?Limit=20&MediaTypes=Video&Fields=PrimaryImageAspectRatio,ProductionYear,UserData` |
| Recentes por biblioteca | `GET /Users/{userId}/Items/Latest?ParentId={viewId}&Limit=20&Fields=PrimaryImageAspectRatio,ProductionYear,UserData` |
| Lista da biblioteca | `GET /Users/{userId}/Items?ParentId={viewId}&Recursive=true&IncludeItemTypes=Movie,Series&SortBy=SortName&Fields=...` |
| Busca | `GET /Users/{userId}/Items?searchTerm={q}&Recursive=true&IncludeItemTypes=Movie,Series&Limit=50` |
| Detalhe | `GET /Users/{userId}/Items/{itemId}?Fields=Overview,Genres,RunTimeTicks,UserData,MediaSources,MediaStreams,People` |
| Temporadas | `GET /Shows/{seriesId}/Seasons?userId={userId}` |
| Episódios | `GET /Shows/{seriesId}/Episodes?userId={userId}&seasonId={seasonId}` |
| Próximo episódio | `GET /Shows/NextUp?UserId={userId}&SeriesId={seriesId}&Limit=1` |
| Imagem | `GET /Items/{itemId}/Images/Primary?maxHeight=400&quality=90&api_key={token}` |
| Backdrop | `GET /Items/{itemId}/Images/Backdrop/0?maxWidth=1280&api_key={token}` |

Imagens e vídeo aceitam `api_key` na query — mais simples que header no Coil/Media3. Trate `ImageTags.Primary` para cache (`&tag=`).

---

## 6. Player (a parte de risco)

### 6.1 PlaybackInfo

`POST /Items/{itemId}/PlaybackInfo?UserId={userId}`

```json
{
  "DeviceProfile": {
    "MaxStreamingBitrate": 20000000,
    "DirectPlayProfiles": [{
      "Container": "mp4,mkv", "Type": "Video",
      "VideoCodec": "h264,hevc", "AudioCodec": "aac,mp3,ac3,eac3,flac,opus"
    }],
    "TranscodingProfiles": [{
      "Container": "ts", "Type": "Video", "VideoCodec": "h264",
      "AudioCodec": "aac", "Context": "Streaming"
    }],
    "SubtitleProfiles": [
      {"Format": "vtt", "Method": "External"},
      {"Format": "srt", "Method": "External"},
      {"Format": "ass", "Method": "External"}
    ]
  }
}
```

Resposta: `MediaSources[]` com `Id`, `SupportsDirectPlay`, `DirectStreamUrl`, `TranscodingUrl`, `RunTimeTicks`, `MediaStreams[]` (Type `Video`/`Audio`/`Subtitle`, `Index`, `Codec`, `Language`, `IsExternal`), `PlaySessionId`.

### 6.2 Direct play

```
{base}/Videos/{itemId}/stream?static=true&mediaSourceId={mediaSourceId}&api_key={token}
```

- Só use se `SupportsDirectPlay` for verdadeiro e o codec estiver no perfil do aparelho.
- Se não suportar: **não transcode em silêncio**. Mostre "formato não suportado neste aparelho" com opção explícita "converter no servidor" (o Pi 4 sofre).
- Media3: `ExoPlayer.Builder(context).build()` + `DefaultMediaSourceFactory(DefaultDataSource.Factory(context, DefaultHttpDataSource.Factory()))`. A URL já leva `api_key`; não precisa de header.

### 6.3 Legendas

- Enumere `MediaStreams` com `Type == "Subtitle"`.
- Texto (srt/ass/vtt) → `{base}/Videos/{itemId}/{mediaSourceId}/Subtitles/{index}/Stream.vtt?api_key={token}` e use `MediaItem.SubtitleConfiguration`.
- ASS com karaokê/typesetting não é fiel no Media3 e burn-in exigiria transcode: aceite ASS simples; avise quando o estilo importar.
- Preferência PT-BR persistida; fallback "sem legenda".

### 6.4 Progresso

Ticks = milissegundos × 10.000.

- Início: `POST /Sessions/Playing` com `{"ItemId","MediaSourceId","PlaySessionId","PositionTicks","IsPaused":false,"CanSeek":true,"PlayMethod":"DirectPlay"}`
- A cada 15 s e ao pausar: `POST /Sessions/Playing/Progress` (mesmo corpo + `IsPaused`)
- Ao sair: `POST /Sessions/Playing/Stopped`
- Retomar: use `UserData.PlaybackPositionTicks` do item; `player.seekTo(posMs)`.

### 6.5 UX mínima

Manter tela ligada, travar rotação no player (ou landscape fixo), foco de áudio (`AudioAttributes` `USAGE_MEDIA`), PiP (`enterPictureInPictureMode`), botão voltar com confirmação. Erros: "servidor offline", "formato não suportado", "sem banda".

---

## 7. Contratos do BFF

Base = URL do BFF. Header: `Authorization: Bearer <bff>` (exceto `/status`). Erros sempre `{"code":"...","message":"..."}`.

| Rota | Resposta |
|---|---|
| `GET /api/v1/status` | `{"status":"ok","version":"0.1.0","time":"..."}` (sem auth) |
| `GET /api/v1/me` | `{"user":{"id","name","is_admin"},"device_id","seerr_linked","seerr_expires_at"}` |
| `GET /api/v1/requests?take=50&skip=0&filter=all` | payload do Seerr **enriquecido**: `media` traz `title/name`, `posterPath` e `arr:{key,kind,id,profileId,profileName,status,progress,eta,error}` |
| `POST /api/v1/requests` | body `{"media_type":"movie|tv","media_id":<tmdb|tvdb>,"seasons":[1,2]|"all","profile":"dublado|legendado"}` → `201`; `profileId` 8/9 (dublado) ou 7 (legendado) no Seerr |
| `POST /api/v1/requests/hide` | body `{"key":"movie:tmdb:123"}` → arquiva no media-agent (`requests/hide`) |
| `POST /api/v1/requests/profile` | body `{"kind":"movie|series","id":123,"profile":"legendado|dublado"}` → `/arr/switch` (legendado) ou `/arr/search` (dublado) |
| `GET /api/v1/search?q=matrix&page=1&language=pt-BR` | `{"results":[{"id","mediaType","title|name","posterPath","overview","mediaInfo":{...}}]}` |
| `GET /api/v1/discover?media_type=all&genre=action&year_min=2020&year_max=2024&min_rating=7&min_votes=1000&sort=popular&page=1&enrich=0` | `{"ok":true,"items":[...],"page":1,"total_pages":100}` |
| `GET /api/v1/house` | ver abaixo |
| `GET /api/v1/services` | `{"ok":true,"services":[{"id","name","ok","http_code","latency_ms","error"}]}` (cache 15 s) |
| `GET /api/v1/pc` | `{"ok":true,"online":true,"status":"Online","checked_at":"..."}` |
| `POST /api/v1/pc/wake` | magic packet pelo gaming-agent → `{"ok":true,"sent":true}` |
| `GET /api/v1/subs/quota` | `{"level","allowed_downloads","downloads_count","remaining_downloads","reset_time","vip"}` |
| `GET /api/v1/subs/queue` | `{"ok":true,"items":[{"id","kind","title","episode","episodeTitle","languages":["Portuguese (Brazil)"]}],"movies_total":0,"episodes_total":N}` |
| `GET /api/v1/admin/downloads?status=1` | só admin/LAN: `{"ok":true,"items":[{"key","title","status","progress","eta","requested_by","error"}]}` |

**Discover/descobrir:** o endpoint geral `/discover/{movies,tv}` **não** aceita `language`
(retorna 0) nem `withGenres` (400). Para gênero use
`/discover/{movies,tv}/genre/{id}` (só `page`/`language`); o BFF aplica nota/votos/ano em
cima e devolve títulos em pt-BR. Padrão: 1+ ano, nota ≥ 7, ≥ 1000 votos, 20 itens/página.
`enrich=1` (Home) adiciona `mediaInfo`/título; `enrich=0` (sub-tela) abre rápido.

**Perfil do pedido:** `dublado` → perfil 8 (filme) / 9 (série); `legendado` → 7.
Para anime os IDs diferem (10/9 e 10/8); hoje o BFF usa o mapa não-anime.

`GET /api/v1/house` (real):

```json
{"ok":true,"host":{"name":"<USUARIO_FAMILIA>","uptime":"23h 54m"},
 "cpu":{"percent":5.9,"cores":4,"load":[2.28,1.4,0.8]},
 "memory":{"percent":65,"used":"2.4 GB","available":"1.3 GB","total":"3.7 GB","swap_percent":70},
 "temperature":{"celsius":47.7,"status":"ok"},"throttled":false,
 "storage":[{"id":"media","label":"Mídia 2TB","percent":9,"used":"157.1 GB","free":"1.6 TB","total":"1.8 TB"}],
 "generated_at":"2026-11-24T22:00:00Z"}
```

Status do Seerr (para o app mapear):

- request: `1` pendente, `2` aprovado, `3` recusado, `4` falhou, `5` concluído.
- media: `1` desconhecido, `2` pendente, `3` processando, `4` parcial, `5` disponível, `6` removido, `7` bloqueado.

**Regra de produto importante:** se `mediaInfo.status == 5`, **não** ofereça "Pedir" — o Seerr aceita e cria um registro inútil (confirmado no ambiente real, não retorna 409).

Cancelar pedido: só se o usuário tiver permissão; o Seerr responde `401` sem `MANAGE_REQUESTS` (o `<USUARIO_FAMILIA>` não tem). Esconda a ação e diga "peça ao admin".

---

## 8. Telas e navegação do MVP

Bottom bar: **Início · Biblioteca · Pedidos · Casa · Perfil**.

1. **Login**: usuário, senha, URL do servidor (avançado), "manter conectado".
2. **Início**: hero "continuar assistindo" (Resume), fileiras "Adicionados recentemente" (Latest por view), "Filmes", "Séries", "Animes" (views do Jellyfin).
3. **Biblioteca**: grid por view, busca com debounce (300 ms), filtro por gênero.
4. **Item**: backdrop, título, ano, duração, sinopse, gêneros, botão Assistir/Continuar, temporadas → episódios (série).
5. **Player**: ver seção 6.
6. **Pedidos**: busca no BFF, resultado com pôster/ano, badge "Disponível"/"Pedir"; aba "Meus pedidos" com status.
7. **Casa**: cards CPU/RAM/temp/storage + "Tudo funcionando"; admin vê downloads.
8. **Perfil**: usuário, modo admin, conexões (LAN/público), qualidade, sair.

### Modo admin

`is_admin` vem do `/me` (claim do token, assinado). Nunca decida admin por preferência local. Ações de admin só existem no BFF admin (`:8092`) e falham fora da LAN — trate `403 admin_lan_only` com uma mensagem clara, não com crash.

---

## 9. Marcos e critérios de aceite

### Marco 1 — fatia vertical (fazer primeiro)

- [ ] Projeto compila e instala no aparelho.
- [ ] Tela de conexões salva Jellyfin + BFF e testa os dois.
- [ ] Login usuário/senha → Jellyfin → BFF; `AccessToken` e token BFF persistidos.
- [ ] Início mostra **uma** fileira (Resume) com pôster real.
- [ ] Abrir item e tocar em Assistir → Media3 direct play.
- [ ] Progresso enviado ao sair; reabrir retoma do ponto.
- **Aceite:** 30 min de HEVC 1080p sem transcode, sem buffering na LAN.

### Marco 2 — catálogo

- [ ] Views, fileiras, biblioteca, busca, detalhe, temporadas/episódios.
- [ ] Estados de loading/erro/vazio em todas as telas.
- [ ] Cache de imagem (Coil) e de listas (memória, 5 min).

### Marco 3 — pedidos e casa

- [ ] Vínculo do Seerr no primeiro acesso a Pedidos.
- [ ] Busca, "Pedir" (escondido se disponível), lista de pedidos com status.
- [ ] Casa com dados reais; admin com downloads.
- [ ] Tratamento de `seerr_session_expired` renovando com o Keystore.

### Marco 4 — polimento

- [ ] Keystore + `allowBackup=false` revisados.
- [ ] Fallback LAN↔público com indicador discreto.
- [ ] PiP, retomada após ligação, foco de áudio, tela ligada.
- [ ] Logout limpa tudo; mensagens em português, sem jargão.

### Marco 5 — distribuição

- [ ] APK assinado (`assembleRelease`), versão e update checker próprio (ou Play interno).
- [ ] Teste com `<USUARIO_FAMILIA>` e `admin` em aparelhos reais.

---

## 10. Armadilhas já conhecidas

1. **Cleartext**: sem o `network_security_config`, o app não fala com `http://<LAN_IP>` (Android bloqueia por padrão).
2. **Pi 4 não transcode**: direct play é requisito, não preferência. Nunca caia para transcode sem ação explícita.
3. **DeviceProfile errado** faz o Jellyfin responder `SupportsDirectPlay=false` e o app "decidir" transcodificar. Comece com o perfil da seção 6.1 e ajuste com o aparelho real.
4. **Ticks**: esquecer o ×10.000 faz o progresso voltar para o início.
5. **device_id instável**: quebra o vínculo do Seerr; gere uma vez e persista.
6. **`/Items/Latest` precisa de `ParentId`** por biblioteca; sem isso vem vazio.
7. **Imagens sem `api_key`** retornam 401 e o Coil mostra placeholder para sempre.
8. **AC3/EAC3** podem exigir decoder extra; teste no aparelho antes de prometer.
9. **ASS** não é renderizado fielmente; burn-in = transcode.
10. **BFF público** depende do DNS (`<BFF_HOST>`) e do Jellyfin remoto (Funnel, ainda não feito). Na LAN use `:8091`.
11. **Rate limit**: 20/min no login e 240/min no resto; em teste automatizado, espere `429`.
12. **Nunca** coloque API key de Radarr/Sonarr/Bazarr/Seerr no app.
13. **Cloudflare/WAF**: User Agent Blocking é um produto fora das custom rules (um Skip de custom rules não cobre). Defina um UA estável (`FamiliaApp/0.1 (Android)`) no `OkHttpClient`. Se aparecer HTML em vez de JSON, é WAF — não é o BFF.

---

## 11. Como testar o backend da outra máquina

```bash
# health (sem auth)
curl -s http://<LAN_IP>:8091/api/v1/status

# login completo (pede a senha, não imprime)
read -rsp 'senha: ' P
TOKEN=$(curl -s -X POST http://<LAN_IP>:8096/Users/AuthenticateByName \
  -H 'Content-Type: application/json' \
  -H 'Authorization: MediaBrowser Client="cli", Device="cli", DeviceId="cli", Version="0.1"' \
  -d "{\"Username\":\"<USUARIO_FAMILIA>\",\"Pw\":\"$P\"}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["AccessToken"])')
BFF=$(curl -s -X POST http://<LAN_IP>:8091/api/v1/session \
  -H 'Content-Type: application/json' \
  -d "{\"access_token\":\"$TOKEN\",\"device_id\":\"cli-dev\"}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')
unset P

curl -s -H "Authorization: Bearer $BFF" http://<LAN_IP>:8091/api/v1/me
curl -s -H "Authorization: Bearer $BFF" http://<LAN_IP>:8091/api/v1/house
```

Verificador público (quando o DNS virar): `python3 check_public.py https://<BFF_HOST>`.

---

## 12. O que não fazer

- Não fazer fork do app oficial do Jellyfin (GPL-3.0 contaminaria o app combinado).
- Não reimplementar auth do Seerr no app: a sessão é do BFF.
- Não guardar o cookie do Seerr no aparelho.
- Não usar `Sessions/Playing` sem `PlaySessionId` (o Jellyfin perde a associação).
- Não prometer download offline no MVP (fase 2).
