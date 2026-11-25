# Casa Mídia — prévia do app mobile

Prévia navegável de como o dashboard poderia virar um app mobile family-first.
O desktop continua no Homepage; o app é um cliente novo para celular.

## Arquivos

- `mobile-app.html` — o app de verdade, em HTML/CSS/JS puro e sem dependências.
  Abra no navegador ou no celular.
- `mockup-board.html` — as quatro telas lado a lado (usado para gerar o board).
- `mockup-board.png` / `screen-*.png` — capturas geradas por Chromium headless.

## Telas

- **Início** — saudação da família, busca no Seerr, “continuar assistindo”,
  atalhos (pedir filme/série, legendas, ligar PC), novidades, status do servidor
  e pedidos em andamento.
- **Pedidos** — Ativos/Histórico, filtros por estado, cards com status em
  linguagem simples, progresso, quem pediu e detalhes. O botão **+** abre a
  busca e cria um pedido.
- **Legendas** — quota da OpenSubtitles, títulos sem legenda PT-BR, fila
  (proposta: no servidor, não no `localStorage`) e ações de admin.
- **Casa** — saúde do Raspberry Pi (CPU, RAM, temperatura, uptime), uso das
  quatro partições, serviços, PC da casa com Wake-on-LAN e importações.

## Modos

- **Família** (padrão): pedir, assistir, acompanhar e ligar o PC. Sem expor
  Radarr/Sonarr/Prowlarr, perfis ou ações de risco.
- **Admin**: revela grade de serviços, adicionar série, buscar original,
  verificar PT-BR e sincronizar legendas. Troque pelo avatar no topo.

## O que é clicável

- Abas inferiores e navegação entre telas.
- Busca / **+** → bottom sheet de busca; “Pedir” adiciona um card em Pedidos.
- Ativos/Histórico e chips de filtro.
- “Detalhes” de um pedido → sheet com ações de admin.
- “Buscar” legenda → entra na fila; “Executar fila agora” simula a execução.
- “Ligar PC” → sheet com senha; simula o Wake-on-LAN.
- Avatar → alterna entre modo Família e Admin.

## Como isso mapeia no sistema real

| Tela do app | Fonte atual |
|---|---|
| Início / pedidos | `media-agent` `GET /arr/pending?status=1`, `GET /requests` |
| Busca e pedido | Seerr (`:5055`) via media-agent/Seerr API |
| Adicionar série | `GET /sonarr/lookup`, `POST /sonarr/add` |
| Episódios | `GET /sonarr/episodes`, `POST /sonarr/episodes/monitor` |
| Legendas | `GET /subs/quota`, proxy `/bazarr` |
| Status / storage | `GET /status`, `GET /storage` |
| PC da casa | `gaming-agent` `:8098` (WOL com senha) |
| Importações | `GET /imports/active`, `GET /migration/status` |

## O que ainda não existe e a prévia assume

1. **API versionada + autenticação** para o app (hoje o `media-agent` usa
   allowlist de IP e não tem login).
2. **Fila de legendas no servidor** (hoje é `localStorage` do navegador).
3. **Notificações push** (“seu pedido chegou”) e atualização em background.
4. **Onboarding de rede**: escolher LAN ou Tailscale e validar o host.

## Próximo passo sugerido

Validar esta navegação com a família antes de escolher Flutter/React Native.
O que mais pesa na decisão é o fluxo de Pedidos (busca → pedido →
acompanhamento → aviso) e não a tela de status.
