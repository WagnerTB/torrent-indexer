# Homepage custom.js

Fonte de verdade do `custom.js` do Homepage. O arquivo servido pelo Homepage no
Raspberry Pi é um **artefato de build**; não edite o `custom.js` do Pi à mão.

## Estrutura

- `src/shared.js` — constantes, helpers de DOM, fetch, modo remoto e textos.
- `src/styles.js` — CSS injetado pelo painel.
- `custom.css` — tema do Homepage (fundo, cartões e cores globais).
- `src/subs.js` — aba Legendas.
- `src/orders/index.js` — controlador de Pedidos.
- `src/orders/active.js` — Ativos e episódios pedidos.
- `src/orders/filters.js` — modal de filtros (tipo/perfil/status) e paginação.
- `src/orders/history.js` — Histórico.
- `src/orders/episodes.js` — modal de episódios.
- `src/orders/add-series.js` — busca e inclusão de séries.
- `src/status.js` — card “Status Raspberry” (CPU, RAM, temperatura, voltagem, uptime e armazenamento).
- `src/admin.js` — aba Admin (login dedicado, containers Docker e auditoria).
- `src/nav.js` — navegação por abas.
- `src/wake.js` — Wake-on-LAN.
- `src/main.js` — entrada e `init()`.

## Aba Admin

A aba **Admin** só aparece no modo local (LAN). Ela fala com o `admin-agent`
em `http://<LAN_IP>:8093` usando a senha dedicada guardada em
`$HOME/.config/admin-agent/password` no Pi.

- Lista os containers do projeto Compose `media` com estado, health, uptime,
  imagem e portas.
- Permite **Iniciar**, **Parar** e **Reiniciar**, com confirmação; serviços
  críticos exigem digitar o nome.
- Mostra as últimas ações e falhas de autenticação.
- **Não** lê `docker-compose.yml`, `.env` nem arquivos de configuração.

O agente e o proxy restrito do Docker estão em
`deploy/raspberry/admin-agent/README.md` e no compose do Pi.

## Build

Requer Node.js 20+ e npm. Na primeira vez:

```sh
npm ci
npm run build
```

Se a Pi não tiver Node, use o container oficial:

```sh
docker run --rm -v "$PWD":/app -w /app node:20-alpine \
  sh -c "npm ci && npm run build && npm run check"
```

O build gera `dist/custom.js` como um único IIFE clássico (o Homepage não
carrega `type=module`). Para validar a sintaxe:

```sh
npm run check
```

## Deploy

O Homepage só serve `custom.js` e `custom.css`; não divida em arquivos em
runtime. Copie os artefatos para o Pi, mantendo backup:

```sh
ssh <pi> 'cp -p /srv/PiMedia/docker/homepage/custom.js /srv/PiMedia/docker/homepage/custom.js.bak.$(date +%Y%m%d-%H%M%S)'
scp dist/custom.js <pi>:/srv/PiMedia/docker/homepage/custom.js
ssh <pi> 'cp -p /srv/PiMedia/docker/homepage/custom.css /srv/PiMedia/docker/homepage/custom.css.bak.$(date +%Y%m%d-%H%M%S)'
scp custom.css <pi>:/srv/PiMedia/docker/homepage/custom.css
```

O `custom.js` e o `custom.css` são lidos a cada carregamento; faça hard refresh
no navegador. Se
alterar `services.yaml`/`bookmarks.yaml` (fora deste diretório), reinicie o
container do Homepage. `dist/` e `node_modules/` não são versionados.

## Status Raspberry

O card consome `GET /status` do `media-agent`. Para voltagem e throttling, instale
o probe no host do Pi:

```sh
sudo sh deploy/raspberry/pi-status-probe.sh --install
```

O padrão grava em `/srv/PiMedia/docker/media-agent/state/pi-status.json`. Se o
`CONFIG_ROOT` for outro, use `--output <CONFIG_ROOT>/media-agent/state/pi-status.json`.

O aviso de subtensão/throttling aparece no card até ser reconhecido. Abra o card
e use **Limpar aviso**; se ocorrer de novo, o aviso volta.

## Antes de publicar

- `npm run build && npm run check`
- Testar desktop (1400×2200) e mobile (390×844): Início, Pedidos (Ativos,
  Histórico), Legendas, modal de episódios, add-series, card Status Raspberry
  (recolhido e aberto) e aba Admin (login, lista, modais e ações).
- Conferir console sem erros e comparar textos/estado com a versão anterior.
