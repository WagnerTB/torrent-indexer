# Homepage custom.js

Fonte de verdade do `custom.js` do Homepage. O arquivo servido pelo Homepage no
Raspberry Pi é um **artefato de build**; não edite o `custom.js` do Pi à mão.

## Estrutura

- `src/shared.js` — constantes, helpers de DOM, fetch, modo remoto e textos.
- `src/styles.js` — CSS injetado pelo painel.
- `src/subs.js` — aba Legendas.
- `src/orders/index.js` — controlador de Pedidos.
- `src/orders/active.js` — Ativos e episódios pedidos.
- `src/orders/filters.js` — modal de filtros (tipo/perfil/status) e paginação.
- `src/orders/history.js` — Histórico.
- `src/orders/episodes.js` — modal de episódios.
- `src/orders/add-series.js` — busca e inclusão de séries.
- `src/storage.js` — painel de armazenamento.
- `src/nav.js` — navegação por abas.
- `src/wake.js` — Wake-on-LAN.
- `src/main.js` — entrada e `init()`.

## Build

Requer Node.js 20+ e npm. Na primeira vez:

```sh
npm ci
npm run build
```

O build gera `dist/custom.js` como um único IIFE clássico (o Homepage não
carrega `type=module`). Para validar a sintaxe:

```sh
npm run check
```

## Deploy

O Homepage só serve `custom.js` e `custom.css`; não divida em arquivos em
runtime. Copie o artefato para o Pi, mantendo backup:

```sh
ssh <pi> 'cp -p /srv/PiMedia/docker/homepage/custom.js /srv/PiMedia/docker/homepage/custom.js.bak.$(date +%Y%m%d-%H%M%S)'
scp dist/custom.js <pi>:/srv/PiMedia/docker/homepage/custom.js
```

O `custom.js` é lido a cada carregamento; faça hard refresh no navegador. Se
alterar `services.yaml`/`bookmarks.yaml` (fora deste diretório), reinicie o
container do Homepage. `dist/` e `node_modules/` não são versionados.

## Antes de publicar

- `npm run build && npm run check`
- Testar desktop (1400×2200) e mobile (390×844): Início, Pedidos (Ativos,
  Histórico), Legendas, modal de episódios, add-series e armazenamento.
- Conferir console sem erros e comparar textos/estado com a versão anterior.
