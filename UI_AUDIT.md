# Auditoria de Interface — Início, Pedidos e Legendas

> **Nota:** IPs/caminhos de deploy foram substituídos por placeholders.

- **Data:** 2026-10-27
- **Status:** **todas as etapas (1, 0.5, 2, 3, 4, 5, 6 e 7) concluídas em 2026-10-28**. O `custom.js` agora é buildado de `deploy/homepage/src`. Pendências opcionais: estado de filtros na URL e tema claro.
- **Escopo:** Início, Pedidos (Ativos/Histórico), Legendas, modal de episódios, painel de armazenamento
- **Método:** inspeção do `custom.js`, `media_agent.py` e configs do Homepage; Chrome headless em 1400×2200 e 390×844; chamadas reais a `/arr/pending`, `/requests`, `/storage` e `/subs/quota`; capturas de tela dos estados ativos, histórico, Legendas, mobile e modal de episódios.

## 1. Resumo executivo

A interface está funcional e visualmente coerente. O maior gap não é estético: é de **contexto e descoberta**. Quem montou o sistema sabe que a busca do topo vai para o Seerr, que “Pedidos” mostra perfis dublados + pedidos do Seerr, que “Adicionar série/anime” adiciona no Sonarr e que o histórico é a fonte da verdade. Quem chega agora não sabe nada disso.

Os três pontos que mais impactam um usuário novo são:

1. **Falta de onboarding/contexto** e de um caminho claro para pedir filmes/séries no Seerr.
2. **Densidade no mobile**: widgets do topo + toolbar + chips empurram o conteúdo para baixo da dobra.
3. **Modal de episódios não escala**: 18 temporadas e 423 episódios abertos de uma vez, com uma ação “Marcar não baixados” que seleciona centenas de episódios sem escopo/confirmação.

Há também inconsistências de texto, estados de carregamento e semântica do histórico que são baratas de corrigir e melhoram muito a percepção de acabamento.

Do ponto de vista técnico, o `custom.js` é um monólito de ~2.4k linhas e o Homepage só serve esse arquivo (JS extra em `/api/config` retorna 422). Por isso o plano inclui a **Etapa 0.5 — Modularização**, com código-fonte em módulos e build para um único `custom.js` clássico.

## 2. O que já está bom

- Navegação fixa e consistente (Home / Pedidos / Legendas), com contagem nas abas.
- Status com **cor + texto** (não depende só de cor) e chips de resumo clicáveis.
- Confirmação nas ações destrutivas (remover/arquivar/apagar).
- Rodapé fixo no modal de episódios (“Aplicar aos selecionados” sempre acessível).
- Painel de armazenamento claro, com detalhamento por partição e alerta visual pela pior partição.
- Layout mobile sem overflow horizontal; alvos de toque razoáveis na maior parte.
- Estados de erro e toasts presentes; o painel de armazenamento tem estado de erro próprio.
- O `custom.js` já usa `MutationObserver` para sobreviver a re-renders do Homepage; o padrão está validado.

## 3. Achados

Legenda de prioridade: **P0** = bloqueia/atrapalha muito o usuário novo ou envolve risco; **P1** = clareza/acabamento; **P2** = acessibilidade/polimento/nice-to-have.

### P0 — Contexto, segurança e escala

- **F-01 — O sistema não se apresenta.** Não há explicação curta do que é cada aba, do recorte “dublado” em Pedidos, do ciclo de status, nem da diferença entre Pedidos e Legendas.
- **F-02 — Caminho para pedir filmes não é óbvio em Pedidos.** A busca global do topo vai para o Seerr, mas o placeholder é “Search...”; em Pedidos não há botão “Abrir Seerr”. O usuário pode concluir que “Adicionar série/anime” é o único jeito de pedir conteúdo.
- **F-03 — Modal de episódios não escala.** Bleach tem 18 temporadas, 423 episódios e 14.071 px de rolagem; tudo aberto, sem seletor de temporada nem busca.
- **F-04 — “Marcar não baixados” é perigoso.** No Bleach, no estado da auditoria, selecionaria 416 episódios (423 − 7 com arquivo); centenas de qualquer forma. Um clique + “Aplicar” monitora e busca centenas de episódios sem confirmação de escopo.
- **F-05 — “Buscar original” muda o perfil sem aviso.** Troca para o perfil Original e inicia busca; o item sai dos perfis dublados. Falta confirmar/explicar a consequência.
- **F-06 — Mobile: muito chrome antes do conteúdo.** Em Pedidos/Legendas os widgets CPU/memória/busca/hora continuam no topo; o conteúdo só começa por volta de 530 px numa tela de 844 px, e a toolbar ocupa ~5 linhas.
- **F-07 — Filtro “Arquivados” no Ativos é um beco sem saída.** O Ativos só mostra não arquivados; selecionar “Arquivados” resulta em “Nenhum pedido corresponde ao filtro”.
- **F-08 — Arquivados não aparecem no Ativos.** Com os 3 filmes arquivados, o topo mostra “0 item(ns) nos perfis dublados” e nada indica que há 3 itens no histórico.

### P1 — Clareza, semântica e acabamento

- **F-09 — Mensagens e datas de status inconsistentes.** O card do Nightmare mostra “Baixado” e “Pedido concluido no Seerr”. Mensagens de fontes diferentes não são limpas quando o status muda. Além disso, para pedidos Seerr-only já concluídos, `completed_at` é gravado no momento em que o painel viu o pedido, não no `updatedAt` do Seerr; isso faz “Buddy” aparecer como “concluído 27/10 21:24” e ordenar no topo, mesmo tendo sido pedido em 26/10.
- **F-10 — “pedido em”/“concluído em” enganam em itens que não vieram do Seerr.** Para itens do Radarr/Sonarr, a data é a primeira vez que o painel viu o item, não a data de um pedido. Melhor “adicionado em”/“visto em”. Para Seerr-only concluídos, usar o `updatedAt` do Seerr como referência de conclusão (ou deixar explícito que é aproximado).
- **F-11 — “Backfill” é jargão.** No histórico, “Backfill” não comunica para um usuário novo. “Importado do Sonarr”/“Histórico inicial” é melhor.
- **F-12 — “Remover” e “Arquivar” são a mesma ação com nomes diferentes.** No Ativos o botão é “Remover”; no Histórico, “Arquivar”.
- **F-13 — Inconsistências de idioma/acentuação.** “Home”, “Search...”, “Filmes e series”, “Pedidos de filmes e series”, “Documentacao”, “episodio(s)”, “Concluido”, “Nao”, “Ultimo”, “reset em ?”, `[pb]`.
- **F-14 — Quota de legendas mostra “reset em ?”.** A API `/subs/quota` real **não retorna** `reset_time` nem `reset_time_utc`; o campo não existe na resposta. Não é só formatação: não há horário exato para mostrar. Melhor “renovação diária” ou ocultar o trecho.
- **F-15 — Buscas/sincronização de Legendas sem feedback por item.** `runBatch` pode levar até 65 s por episódio; o status fica no topo (fora da tela no mobile), os botões não desabilitam e um segundo clique é ignorado silenciosamente.
- **F-16 — Fila de legendas só aparece quando tem item.** É `localStorage` (por navegador) e não há estado “Fila vazia” nem aviso de que a fila não acompanha outro dispositivo.
- **F-17 — Formulário de adicionar série sem rótulos visíveis.** Os três selects (perfil, pasta raiz, tipo) têm só `aria-label`; visualmente o usuário vê três dropdowns sem título.
- **F-18 — “Apagar arquivados” apaga só o que está carregado.** O botão usa as chaves dos itens da página atual, mas o rótulo sugere “todos os arquivados”. Se houver mais de uma página, o comportamento não bate com o texto.
- **F-19 — Episódios pedidos não mostram o perfil da série.** No caso do Bleach (perfil 6, HD 720/1080), o card de episódios aparece sem explicar por que a série não está na lista de títulos dublados.
- **F-20 — Número absoluto de episódio em todas as séries.** `#407 (S17E41)` é ótimo para anime/Bleach, mas pode confundir em séries padrão; mostrar o absoluto só quando fizer sentido (ou como tag secundária).

### P2 — Acessibilidade, consistência e nice-to-have

- **F-21 — Acessibilidade.** Sub-abas usam `aria-selected` em botões sem `role="tab"`; barras de progresso sem `role="progressbar"`/`aria-valuenow`; modal sem `role="dialog"`/`aria-modal` e sem foco preso; toast sem `aria-live`.
- **F-22 — Contraste/tamanho e toque.** Textos secundários de 11 px e `#7d838b` são pequenos/baixo contraste; o “Remover” dos episódios tem 28 px de altura no mobile (ideal ≥40 px); o “Atualizar” do storage é um link de 11 px.
- **F-23 — Painéis custom com cores fixas de tema dark.** Se o Homepage mudar para tema claro, os painéis continuam escuros. Usar variáveis do tema quando possível.
- **F-24 — Estado das sub-abas/filtros não vai para a URL.** Recarregar `?tab=pedidos` sempre volta para Ativos; não dá para compartilhar/favoritar o Histórico com filtro.
- **F-25 — Auto-refresh do Histórico reseta paginação/scroll.** `refreshSilent` recarrega o Histórico a cada 60 s com `loadHistory(true)`, podendo perder a página 2+ e a posição de leitura.
- **F-26 — Histórico verboso.** Cards grandes com muitas linhas; com 16 registros já ocupa várias telas. Um layout compacto (linha/accordion) com badge Ativo/Arquivado e filtro por origem melhoraria a leitura.
- **F-27 — Sem links diretos para Sonarr/Radarr/Jellyfin nos itens.** Útil para troubleshoot; só faz sentido em modo LAN (os cards de gestão já são escondidos no Tailscale).
- **F-28 — Datas absolutas.** “27/10/2026, 20:29:02” é preciso, mas “há 2 h” ajudaria a leitura rápida; pode ser complementar.
- **F-29 — Storage: “Sistema MICROSD” como tag.** O rótulo principal é “Sistema” e a tag “MICROSD”; para quem não conhece, “Sistema (microSD)” no rótulo seria mais claro.
- **F-30 — Busca global não é host-aware.** O `widgets.yaml` aponta para `http://<TAILSCALE_IP>:5055/search?query=`. O `custom.js` reescreve os links dos cards, mas **não** reescreve a busca. Em LAN sem Tailscale, a busca pode falhar.
- **F-31 — Placeholder da busca global não é configurável no `widgets.yaml`.** O “Search...” é padrão do Homepage; para traduzir/rotular é preciso ajustar via `custom.js` (e sobreviver a re-render).
- **F-32 — Legendas usa só a primeira legenda faltante.** `missing_subtitles[0]` define o idioma; se houver mais de um idioma pendente, o usuário não escolhe. Feature futura, não quick win.
- **F-33 — Sem noção de retenção/limpeza do histórico.** O usuário escolheu “tudo, com filtro”; o banco cresce. Já existe apagar por item/arquivados; uma visão de retenção/limpeza em massa seria opcional.
- **F-34 — “No Seerr” é jargão.** Um tooltip “pedido aguardando aprovação no Seerr” ajudaria.
- **F-35 — “Verificar PT-BR”/“Sincronizar existentes” não se explicam.** Tooltips curtos reduziriam o medo de clicar.
- **F-36 — Filtros duplicados e fora de contexto.** Os chips e o select fazem a mesma função; no Ativos, opções como “Arquivados” não se aplicam; no Histórico, “No Seerr”/“Episódios” mudam de sentido. Um único mecanismo (chips + “mais filtros”) ou opções contextuais reduziria confusão.
- **F-37 — Senha do WOL sem explicação.** No modo remoto, “Ligar PC” abre `window.prompt('Senha do gaming:')`; um usuário novo não sabe qual é a senha nem onde obtê-la. O texto “gaming” é jargão.
- **F-38 — Falta de contexto do modo remoto e do escopo.** No Tailscale os cards de gestão somem; “Pedidos” é dublado + Seerr; “Legendas” é vídeo vs legenda; o histórico começa na implementação (pedidos antigos não aparecem). Nada disso é dito na tela.
- **F-39 — Itens não monitorados somem do Ativos.** O `/arr/pending` exige `monitored` e perfil 8/9; ao desmarcar tudo, o item pode desaparecer do Ativos sem explicação (o Histórico mantém).
- **F-40 — `custom.js` monolítico (habilitador técnico).** São 2.383 linhas em um único IIFE, com helpers/estado compartilhados e todas as features no mesmo arquivo. As etapas 1–6 mexem em quase tudo; sem módulos, o risco de regressão e o custo de manutenção crescem.
- **F-41 — O Homepage só serve `custom.js`/`custom.css`.** Teste real: `GET /api/config/__probe.js` retorna **422 “Unsupported file”**. O `<script src="/api/config/custom.js">` é clássico (não `type=module`). Logo, separar em vários arquivos **em runtime** pelo config do Homepage não é possível; a modularidade precisa ser feita no código-fonte e **empacotada para um único `custom.js` clássico** (ou servida por outro serviço, o que não recomendo).

## 4. Etapas propostas

> **Todas as etapas concluídas** (2026-10-28), na ordem **1 → 0.5 → 2 → 3 → 4 → 5 → 6 → 7**. O estado detalhado está no topo do documento e no checklist da seção 8; restam apenas itens opcionais (URL state e tema claro).

### Etapa 0 — Registro e validação (concluída)

- [x] Auditar desktop/mobile, modal, histórico, Legendas e storage.
- [x] Registrar achados e evidências neste documento.
- [x] Reavaliar consistência e dependências (seção 5).
- [x] Confirmar escopo/ordem com o usuário — ordem **1 → 0.5 → 2 → 3 → 4 → 5 → 6 → 7**.

**Critério de aceite:** documento revisado e etapas aprovadas.

### Etapa 0.5 — Modularização preparatória (habilitador)

**Status:** concluída em 2026-10-28. Fonte em `deploy/homepage/src`, build esbuild para um IIFE clássico e paridade validada.

Objetivo: separar o `custom.js` em módulos por feature, **sem mudar comportamento**, antes das mudanças grandes.

- **Fonte de verdade no repo:** `deploy/homepage/src/` (ou `homepage/src/`). O `custom.js` do Pi passa a ser artefato de build; os `.bak` continuam.
- **Layout sugerido:**
  - `shared.js` — constantes (`MEDIA`, `REMOTE`, `SERVICE_HOST`), `h`, `btn`, `toast`, `fmtDate`, `norm`, `sleep`, `injectStyles`, `setTabCount`, fetch helpers.
  - `storage.js` — painel de armazenamento.
  - `orders/active.js`, `orders/history.js`, `orders/episodes.js`, `orders/add-series.js` (ou um `orders.js` inicialmente).
  - `subs.js` — Legendas (quota, fila, lista, sync).
  - `nav.js` — navegação/abas.
  - `wake.js` — WOL.
  - `main.js` — `init()`.
- **Build para um único IIFE clássico** (`custom.js`), porque o Homepage carrega script clássico e rejeita outros arquivos (F-41).
- **Opções de build:**
  - **A (recomendada):** ES modules + `esbuild --bundle --format=iife --target=es2020` (dev dependency só no diretório do homepage).
  - **B:** IIFEs com namespace `window.__hx` + script de concatenação sem dependências.
- **Teste de paridade antes/depois:** screenshots 1400/390 de Início/Pedidos/Legendas, modal, histórico, storage e WOL (sem acionar), console sem erros, comparação de textos/classes.
- **Deploy igual:** copiar o `custom.js` gerado para `<MEDIA_ROOT>/docker/homepage/custom.js`; hard refresh no navegador.
- **Não misturar correções de comportamento nesta etapa**; ela é behavior-preserving.

**Critério de aceite:** build reproduzível; `custom.js` gerado é classic script; paridade visual/funcional em desktop/mobile; zero erros de console; nenhum arquivo extra necessário em runtime; comandos de build documentados no repo.

**Quando fazer (confirmado):** **depois da Etapa 1** (quick wins primeiro), antes das features grandes (2–6). A Etapa 1 é quase toda texto/feedback simples; a modularização vem em seguida, antes de onboarding/mobile/modal/histórico.

### Etapa 1 — Quick wins de texto, semântica e feedback

**Status:** concluída em 2026-10-28.

Objetivo: eliminar o que parece “inacabado” e evitar mensagens contraditórias, sem mexer em layout.

- Corrigir acentos/pluralização em Pedidos/Legendas: “episódio(s)”, “Concluído”, “Não”, “Último”, “Nenhum episódio”, “N registros”, “0 itens” → texto natural.
- `[pb]` → `PT-BR` (mapa de códigos comuns: `pb`/`pt-br` → PT-BR, `en` → Inglês, `es` → Espanhol).
- Quota: trocar “reset em ?” por “renovação diária” (a API não retorna o horário) ou ocultar o trecho.
- “Backfill” → “Importado do Sonarr”/“Histórico inicial”.
- “pedido em” → “adicionado em”/“visto em” quando `source != 'seerr'`.
- Corrigir a exibição de mensagens antigas: ao mudar para um status sem mensagem, limpar `status_message` (ou na UI, só mostrar a mensagem se ela combinar com a origem/status atual). Exemplo alvo: Nightmare sem “Pedido concluido no Seerr” contraditório. A consolidação de datas Seerr-only fica na Etapa 5.
- “Home” → “Início”; busca global “Search...” → “Buscar no Seerr...”.
- Descriptions/Bookmarks: “Filmes e series” → “Filmes e séries”; “Pedidos de filmes e series” → “Pedidos de filmes e séries”; “Documentacao” → “Documentação”.
- Fila de legendas: mostrar estado “Fila vazia” e nota de que a fila é salva neste navegador.
- Desabilitar/loading nos botões de busca/sincronização de Legendas, nas ações do Histórico e no “Atualizar” do storage.
- “Apagar arquivados” → “Apagar arquivados carregados” (rótulo explícito). A decisão de implementar “todos os arquivados” no backend fica para a Etapa 5.

**Critério de aceite:** nenhuma string “? / episodio / Concluido / Nao / Backfill / [pb]” visível nos fluxos principais; nenhuma mensagem contraditória no histórico; botões indicam carregamento e não aceitam clique duplo; zero erros de JS.

### Etapa 2 — Onboarding e descoberta

**Status:** concluída em 2026-10-28.

Objetivo: um usuário novo entender o sistema sem perguntar.

- Bloco recolhível “Como funciona” no topo de Pedidos e Legendas.
  - Pedidos: perfis dublados + pedidos do Seerr; “Adicionar série/anime” = Sonarr; filmes/pedidos gerais = Seerr.
  - Ciclo: Pendente → Aprovado → Procurando → Baixando → Baixado.
  - Pedidos = vídeo; Legendas = legenda. São fluxos separados.
  - Histórico: tudo que já passou; arquivar não apaga. O histórico começa na implementação; pedidos antigos só aparecem se importados.
  - Itens não monitorados (ou fora dos perfis 8/9) podem sair do Ativos; o Histórico mantém.
  - Modo remoto (Tailscale): os cards de gestão ficam ocultos; use Pedidos/Legendas.
  - Legendas: pendências, quota, fila local do navegador.
- Botão **“Abrir Seerr”** em Pedidos (link para `http://<host>:5055`).
- WOL: renomear o prompt “Senha do gaming:” para “Senha para ligar o PC” e incluir uma linha de ajuda no card/“Como funciona”.
- Link **“N arquivados — ver no Histórico”** no Ativos (usar `hiddenCount` ou consulta dedicada).
- Empty states com ação: “Nada por aqui. Adicione uma série/anime ou peça um filme no Seerr.”
- Tooltips: “No Seerr”, “Verificar PT-BR”, “Buscar original”, “Sincronizar existentes”.
- Explicar o recorte dublado e o caso “série fora do perfil dublado” (Bleach) na seção de episódios.

**Critério de aceite:** em teste com alguém sem contexto, a pessoa encontra “onde pedir um filme” e entende por que um item pode estar só no Histórico em menos de ~1 minuto; empty state sempre oferece próximo passo.

### Etapa 3 — Densidade mobile

**Status:** concluída em 2026-10-28.

Objetivo: conteúdo acima da dobra e menos rolagem antes da lista.

- Recolher/compactar os widgets CPU/memória/busca/hora nas abas Pedidos/Legendas (não remover o relógio/busca sem confirmar).
- Unir busca/filtro/Atualizar em menos linhas; chips em rolagem horizontal.
- Encurtar a linha de status: pluralização natural e, se 0, “Nenhum filme/série dublado no momento”.
- Aumentar alvos de toque: “Remover” dos episódios ≥40 px; “Atualizar” do storage com padding.
- Testar em 390×844 e 360×800.

**Critério de aceite:** em 390×844, o primeiro item de conteúdo aparece acima de ~400 px; toolbar com no máximo 3 linhas; sem overflow horizontal; alvos de toque ≥40 px nos controles principais.

### Etapa 4 — Modal de episódios e ações de risco

**Status:** concluída em 2026-10-28.

Objetivo: achar e pedir um episódio específico sem rolar 14 mil pixels nem selecionar centenas por acidente.

- Temporadas recolhíveis; seletor “ir para temporada”; busca por número/título.
- Filtro “somente monitorados”/“somente sem arquivo”.
- “Marcar não baixados” com escopo da temporada e confirmação com contagem; manter um “selecionar todos” explícito, se desejado.
- Badge “Pedido” nos episódios já rastreados (cruzar com `/requests?kind=episode`).
- Rótulos visíveis no formulário de adicionar: “Perfil”, “Pasta raiz”, “Tipo”.
- Confirmação no “Buscar original” com o efeito (“muda para o perfil Original e o item sai dos dublados”).
- Opcional: mostrar o perfil da série na seção de episódios pedidos.

**Critério de aceite:** chegar à temporada 17 do Bleach em ≤2 interações; “Marcar não baixados” mostra quantos serão afetados e exige confirmação; episódios já pedidos têm badge; nenhum clique acidental monitora >20 episódios sem confirmação.

### Etapa 5 — Histórico mais claro

**Status:** concluída em 2026-10-28. Datas Seerr-only usam `updatedAt` como aproximado e “concluído sem data” quando ausente; filtros contextuais (chips + select) e filtro por origem; “Apagar arquivados carregados” mantido; auto-refresh pausado. Estado de sub-aba/filtros na URL **não** implementado (opcional).

Objetivo: transformar o histórico em algo escaneável e sem contradições.

- Layout compacto/accordion com colunas: data, título, tipo, status, origem, ações.
- Badge **Ativo/Arquivado**; agrupar por data ou série.
- Filtro por origem (Seerr/Manual/Importado) além do status.
- Consolidar datas de conclusão Seerr-only (`updatedAt`) e ordenação; o texto “pedido em” e as mensagens antigas já foram tratados na Etapa 1.
- Resolver o delete em massa: manter o rótulo “apagar carregados” ou backend para “todos os arquivados”.
- Preservar paginação/scroll no auto-refresh ou pausar o refresh enquanto o usuário lê.
- Opcional: estado da sub-aba/filtros na URL (`&view=history&status=...`).

**Critério de aceite:** 20 registros cabem em ~2 telas no desktop; nenhum card mostra status e mensagem contraditórios; “apagar arquivados” deixa claro o escopo; recarregar mantém a visão (se URL implementada).

### Etapa 6 — Acessibilidade e polimento

**Status:** concluída em 2026-10-28. Toast e regiões de status com `aria-live`; sub-abas com `aria-pressed` e navegação por setas; modal com `role="dialog"`, `aria-modal`, foco preso e retorno de foco; barras com `role="progressbar"`/`aria-valuenow`; contraste e tamanhos secundários revisados; links Radarr/Sonarr apenas em LAN; datas relativas complementares. Tema claro continua fora (painéis dark-only).

- Sub-abas com `role=tablist/tab/tabpanel` (ou `aria-pressed` consistente).
- Barras com `role="progressbar"`/`aria-valuenow`.
- Modal com `role="dialog"`, `aria-modal`, foco preso e retorno de foco.
- Toast com `aria-live="polite"`.
- Contraste/tamanho de textos secundários; revisar 11 px.
- Painéis custom usando variáveis do tema (suportar claro/escuro) — se viável.
- Links diretos para Sonarr/Radarr/Jellyfin apenas em modo LAN; ocultar no Tailscale.
- Datas relativas complementares (“há 2 h”).

**Critério de aceite:** navegação por teclado nas sub-abas e no modal; leitor de tela anuncia status/toast; contraste mínimo AA nos textos principais; sem regressão visual nos temas.

### Etapa 7 — Reavaliação e testes finais

**Status:** concluída em 2026-10-28. Chrome headless em 1400×2200 e 390×844; teclado/foco/modal/filtros/empty/error; mocks para Seerr fora, Sonarr fora, quota 0, histórico com 120 registros e 2 discos; zero erros de console. Estado de filtros na URL segue opcional.

- Reexecutar Chrome headless em 1400×2200 e 390×844.
- Testar teclado, foco, modal, filtros, empty/error states.
- Testar cenários: Seerr fora, Sonarr fora, quota 0, histórico >100, 2 discos.
- Atualizar `MEDIA_STACK.md`/`SITE_STATUS.md` se necessário.
- Revisar este documento e marcar o que foi feito.

**Critério de aceite:** zero erros de console; fluxos principais completos em desktop/mobile; estados de erro claros; documentação sincronizada.

### Mapa etapa → achados

| Etapa | Achados principais |
|---|---|
| 1 — Quick wins | F-09, F-10, F-11, F-13, F-14, F-15, F-16, F-18, F-20, F-35 |
| 0.5 — Modularização | F-40, F-41 |
| 2 — Onboarding/descoberta | F-01, F-02, F-08, F-19, F-30, F-31, F-34, F-37, F-38, F-39 |
| 3 — Mobile/densidade | F-06, F-13, F-22 |
| 4 — Modal de episódios | F-03, F-04, F-05, F-17, F-19, F-20 |
| 5 — Histórico | F-07, F-08, F-09, F-10, F-12, F-18, F-24, F-25, F-26, F-33, F-36 |
| 6 — Acessibilidade/polimento | F-21, F-22, F-23, F-27, F-28, F-29 |
| 7 — Reavaliação/testes | Todos (regressão e consistência) |

## 5. Reavaliação (consistência e pontos ainda abertos)

### 5.1 Correções em relação ao rascunho inicial

1. **Reset da quota não é só formatação.** A API real `/subs/quota` não retorna `reset_time` nem `reset_time_utc`; portanto não há horário exato. A recomendação correta é “renovação diária”/ocultar, não “formatar o campo existente”.
2. **Placeholder da busca não é configurável no `widgets.yaml`.** O “Search...” é padrão do Homepage. A tradução/rotulagem precisa ser feita no `custom.js` (com observer para re-render).
3. **Renomear grupos tem dependência no `custom.js`.** `applyMode` esconde os grupos pelo nome “Atalhos” e “Media Services Status” no modo remoto. Se renomear “Media Services Status” para português, é obrigatório atualizar essa comparação; caso contrário, os cards LAN-only aparecem no Tailscale.
4. **“Apagar arquivados” não apaga todos.** O código envia só as chaves carregadas; o rótulo precisa refletir isso ou o backend precisa de um modo “todos os arquivados”.
5. **Formulário de adicionar série não tem rótulos visíveis.** Os três selects têm apenas `aria-label`; adicionar labels visíveis é uma melhoria real, não cosmética.
6. **Busca global não é host-aware.** O `widgets.yaml` aponta para o IP Tailscale; o `custom.js` reescreve os links dos cards, mas não a busca. Em LAN sem Tailscale, a busca pode falhar.
7. **Sub-abas não têm estado na URL.** Recarregar/favoritar o Histórico sempre volta para Ativos.
8. **Auto-refresh do Histórico pode resetar paginação/scroll.** `refreshSilent` chama `loadHistory(true)` a cada 60 s enquanto a aba está ativa.
9. **Episódios pedidos não mostram o perfil da série.** O Bleach (perfil 6) aparece só como “SÉRIE Bleach”; um usuário novo pode não entender por que não há card na lista de títulos.
10. **Número absoluto em todas as séries.** O `#407` é útil para Bleach/anime, mas pode confundir em séries padrão; precisa de regra por tipo ou apresentação secundária.

### 5.2 Consistência com o código/config

- **Pedidos/Histórico/Legendas/Storage:** tudo é frontend (`custom.js`) + endpoints do `media_agent.py`; não há migração de banco necessária para as etapas 1–6, exceto a correção opcional de `status_message` no rastreamento.
- **Modularização:** a fonte pode ser ES modules, mas o artefato tem que ser um único IIFE clássico; o Homepage rejeita `/api/config/*.js` (422). Build local + cópia do `custom.js` mantém o runtime intacto.
- **`services.yaml` contém segredos** (API keys). O documento não os reproduz; qualquer alteração de labels/descrições deve ser feita no arquivo do Pi e não deve ser copiada para o repositório.
- **Renomear “Media Services Status”/“Atalhos”** exige atualizar `custom.js` (`applyMode`) para o modo remoto.
- **Traduzir “Home”** é seguro: está no `custom.js`.
- **Traduzir a busca global** exige `custom.js`; o `widgets.yaml` não tem opção de placeholder.
- **“Backfill” → “Importado do Sonarr”** é só exibição; o valor `source` no banco pode continuar `backfill`.
- **“pedido em” vs “adicionado em”** é só exibição; usa `source`.
- **Confirmação do “Buscar original”** é JS-only; o endpoint `arr_switch` não muda.
- **Escopo do “Marcar não baixados”** é JS-only; pode ser resolvido com os checkboxes já renderizados.
- **Collapse de temporadas** é JS-only; `/sonarr/episodes` já retorna tudo.
- **Histórico compacto** é JS-only; `/requests` já retorna `events`, `status`, `source`, `hidden`.
- **Delete em massa de arquivados** exige uma decisão: só rótulo (mais simples) ou novo parâmetro no backend (mais correto).
- **Estado da sub-aba na URL** é JS-only; a navegação principal já usa `?tab=`.
- **Links LAN-only** precisam respeitar `REMOTE`/`SERVICE_HOST` já existentes no `custom.js`.

### 5.3 Riscos e trade-offs

- **Re-render do Homepage:** qualquer injeção no DOM (busca, painel) precisa de observer; o padrão já existe, mas duplicar observers pode causar loops. Testar.
- **Esconder os widgets no mobile** remove também o relógio/busca global; melhor **compactar/recolher** do que remover, e confirmar.
- **Renomear grupos** pode quebrar o modo remoto; atualizar `custom.js` junto.
- **Alterar “Remover” para “Arquivar”** é decisão de produto; o usuário já escolheu “Remover” antes. Confirmar antes.
- **Corrigir `status_message` no backend** afeta registros existentes; testar com o Nightmare e com itens Seerr-only.
- **Delete em massa** não pode apagar itens ativos; limitar a `hidden_at IS NOT NULL`.
- **Busca host-aware** não pode quebrar o acesso via Tailscale; usar `SERVICE_HOST` e testar os dois modos.
- **Modal com 423 episódios** continua pesado; colapsar ajuda, mas o seletor de temporada deve evitar renderizar tudo de uma vez (ou pelo menos esconder via CSS).
- **Acessibilidade** exige teste com teclado/leitor de tela; não é só adicionar atributos.
- **Tema claro** pode não ter variáveis suficientes no Homepage; validar antes de prometer.
- **Modularização:** o Homepage só serve `custom.js`/`custom.css` (422 para outros arquivos) e carrega script clássico; o bundle precisa sair como IIFE. Introduz um passo de build e muda a fonte de verdade para o repo; exige teste de paridade e disciplina para não editar o artefato do Pi.

### 5.4 Pontos ainda não cobertos (backlog)

- **Seleção de idioma de legenda** quando há mais de um idioma faltante (`missing_subtitles[0]` hoje).
- **Notificações** de conclusão/falha (não pedido; fora de escopo).
- **SMART/saúde dos discos** (uso apenas; fora de escopo).
- **Integração com Jellyfin** para confirmar disponibilidade final (o usuário já confere manualmente).
- **Autenticação/multiusuário** (o media-agent é LAN/Tailscale, sem auth).
- **Retenção automática do histórico** (o usuário escolheu tudo com filtro; limpeza manual).
- **Busca por temporada/episódio no Histórico** (hoje busca textual).
- **Relatórios/exportação** do histórico (não pedido).

### 5.5 Segunda passada — o que a reavaliação acrescentou

- **F-09 ampliado:** além da mensagem antiga, as datas de conclusão de pedidos Seerr-only (`completed_at`) usam o momento da primeira sincronização, não o `updatedAt` do Seerr. Isso gera “concluído” e ordenação enganosos.
- **F-10 ampliado:** a mesma distinção vale para “concluído em”; usar `updatedAt` do Seerr ou rotular como aproximado.
- **F-36 (novo):** chips + select duplicam a filtragem e misturam opções que não se aplicam ao contexto (Ativos vs Histórico). É uma oportunidade de simplificação, não só de correção.
- **F-37 (novo):** o prompt de senha do WOL (`Senha do gaming:`) não se explica; um usuário novo fica bloqueado sem saber o que digitar.
- **F-38 (novo):** o modo remoto (cards de gestão ocultos), o recorte dublado, a diferença Pedidos vs Legendas e o início do histórico não estão na tela. Isso deve entrar no “Como funciona”.
- **F-39 (novo):** itens não monitorados podem sumir do Ativos; o Histórico mantém. Precisa de explicação/aviso.
- **F-14 corrigido:** a API `/subs/quota` não tem `reset_time_utc`; o fallback de 24 h em `parseReset` é uma estimativa. Não prometer horário exato.
- **F-31 corrigido:** o placeholder “Search...” não é configurável no `widgets.yaml`; a tradução/rotulagem precisa de `custom.js`.
- **F-30 confirmado:** a busca global usa o IP Tailscale fixo; o `custom.js` não a reescreve para `SERVICE_HOST` como faz com os cards.
- **F-17 confirmado:** os três selects do formulário de adicionar não têm rótulo visível, só `aria-label`.
- **F-18 confirmado:** “Apagar arquivados” envia só as chaves carregadas; o rótulo não deixa isso claro.
- **F-24/F-25 confirmados:** a sub-aba não vai para a URL e o auto-refresh do Histórico recarrega a página 1.

### 5.6 Conclusão da reavaliação

O plano continua consistente e não há bloqueio novo. As correções acima **não mudam a ordem das etapas**; apenas acrescentam itens às etapas 1 (texto/datas/quota/feedback), 2 (onboarding/modo remoto/Seerr) e 5 (histórico/filtros/datas).

Os dois pontos que exigem decisão de produto antes de codar são:

1. **Filtros:** manter chips + select (com opções contextuais) ou simplificar para um mecanismo só.
2. **Datas Seerr-only:** usar `updatedAt` como “concluído em” (aproximado) ou exibir “concluído (data desconhecida)” — não inventar precisão.

Ordem confirmada: **1 → 0.5 → 2 → 3 → 4 → 5 → 6 → 7** (quick wins primeiro; modularização em seguida; features grandes depois). A modularização é behavior-preserving e não muda a UI.

### 5.7 Modularização do `custom.js` (impacto no plano)

**Restrição confirmada:** o Homepage só serve os arquivos de config suportados. O teste `GET /api/config/__probe.js` retornou **422 “Unsupported file”**. O `custom.js` é carregado como script clássico, sem `type=module`. Então:

- **Não é possível** simplesmente criar `orders.js`, `subs.js`, etc. e carregá-los via `/api/config/...`.
- **Também não dá** para usar `import`/`export` direto no `custom.js` sem um bundle, porque o navegador o carrega como script clássico.
- A modularidade tem que ser feita **no código-fonte** e o resultado **empacotado em um único `custom.js` clássico** (IIFE).

**Impacto concreto no plano:**

- Entra a **Etapa 0.5 — Modularização preparatória** (behavior-preserving).
- As etapas 1–6 passam a editar **módulos por feature**, não o monólito.
- A fonte de verdade sai do arquivo solto no Pi e vai para o repo (`deploy/homepage/src/`), com o `custom.js` do Pi tratado como artefato de build.
- O deploy continua sendo **um arquivo só**; o Homepage não muda.
- O maior módulo é `orders` (Pedidos + Histórico + modal + adicionar série). Se ficar grande, dividir em `orders/active.js`, `orders/history.js`, `orders/episodes.js`, `orders/add-series.js`. Legendas, storage, nav e WOL viram módulos próprios.
- A refatoração deve ser feita **antes** das mudanças grandes (ou logo após a Etapa 1, se você preferir ver quick wins primeiro). Fazer depois de várias features aumenta o retrabalho.

**Opções de build:**

| Opção | Como | Prós | Contras |
|---|---|---|---|
| **A (recomendada)** | ES modules + `esbuild --bundle --format=iife --target=es2020` | Padrão, simples, minificável, output clássico | Adiciona uma dev dependency Node no diretório do homepage |
| B | IIFEs com `window.__hx` + script de concatenação | Zero dependências | Menos idiomático, namespace global manual |
| C | Continuar em um arquivo, só com seções internas | Sem build | Não resolve o tamanho/manutenção; não atende ao pedido de vários arquivos |

**Recomendação:** opção **A**, com o build rodando localmente (não no Pi) e o `custom.js` gerado copiado para o Pi como hoje. O script de build e a estrutura de origem ficam versionados no repo. O teste de paridade é obrigatório (screenshots 1400/390 + console + fluxos principais).

**Riscos específicos:** regressão silenciosa na refatoração; build esquecido antes do deploy; cache do navegador; a fonte de verdade mudar de lugar e alguém editar o `custom.js` do Pi por engano. Mitigação: README curto no diretório do homepage, script de build único, backups `.bak` no Pi e aviso “não editar o artefato”.

## 6. Decisões a confirmar

1. **Ordem geral:** **confirmada — 1 (quick wins) → 0.5 (modularização) → 2 → 3 → 4 → 5 → 6 → 7.**
2. **Widgets no topo das abas:** compactar/recolher (recomendado) ou remover de Pedidos/Legendas?
3. **Nomenclatura:** padronizar “Remover” → “Arquivar” (recomendado) ou manter “Remover”?
4. **Arquivados:** adicionar link “N arquivados” no Ativos e, ao selecionar “Arquivados”, trocar automaticamente para o Histórico?
5. **Histórico em massa:** manter “apagar carregados” (rótulo explícito) ou implementar “apagar todos os arquivados” no backend?
6. **Busca global:** traduzir/rotular e tornar host-aware (recomendado) ou apenas rotular?
7. **Modal de episódios:** colapsar temporadas + seletor + busca; confirmar “Marcar não baixados” com contagem. Aprova?
8. **“Buscar original”:** adicionar confirmação com o efeito (recomendado)?
9. **Grupos/descrições:** traduzir “Media Services Status” e descrições? Lembrar de atualizar `custom.js` para o modo remoto.
10. **Links diretos** para Sonarr/Radarr/Jellyfin nos itens: apenas LAN (recomendado) ou não incluir?
11. **Acessibilidade:** incluir na Etapa 6 ou desde já junto das etapas que tocam os componentes?
12. **Tema claro:** investir em variáveis de tema ou assumir dark-only?
13. **Datas Seerr-only:** usar `updatedAt` como “concluído em” (aproximado) ou exibir “data desconhecida”?
14. **Filtros:** chips + select com opções contextuais, ou simplificar para um mecanismo só?
15. **WOL:** adicionar ajuda da senha e trocar “Senha do gaming:” por “Senha para ligar o PC”?
16. **Itens não monitorados:** explicar no “Como funciona” ou adicionar um aviso no Ativos quando um item sair por não estar monitorado?
17. **Modo remoto/Pedidos vs Legendas/histórico inicial:** incluir no “Como funciona” (recomendado)?
18. **Modularização — build:** **confirmado — esbuild** (`--bundle --format=iife --target=es2020`).
19. **Modularização — timing:** **confirmado — depois da Etapa 1** (quick wins primeiro).
20. **Fonte de verdade:** **confirmado — sim**, versionar `deploy/homepage/src/` e tratar o `custom.js` do Pi como artefato de build.
21. **Granularidade:** **confirmado — sim, dividir** `orders` em `active.js`, `history.js`, `episodes.js`, `add-series.js`.

## 7. Fora de escopo (por agora)

- Notificações push/e-mail.
- SMART/saúde/temperatura dos discos.
- Integração automática com Jellyfin para “disponível”.
- Multiusuário/autenticação.
- Redesign completo do Homepage.
- Alterações no storage (já implementado e aprovado).
- Migração de dados/retroação de histórico anterior à implementação.

## 8. Checklist de aprovação

- [x] Li o documento e concordo com os achados.
- [x] Etapa 0.5 (modularização) aprovada.
- [x] Build definido: **esbuild** (`--bundle --format=iife`).
- [x] Timing da modularização definido: **depois da Etapa 1**.
- [x] Fonte de verdade/versionamento definidos: **repo (`deploy/homepage/src`) + artefato no Pi**.
- [x] Granularidade do `orders` definida: **dividir em active/history/episodes/add**.
- [x] Etapa 1 (quick wins) aprovada.
- [x] Etapa 2 (onboarding/Seerr) aprovada e concluída.
- [x] Etapa 3 (mobile) aprovada e concluída.
- [x] Etapa 4 (modal de episódios) aprovada e concluída.
- [x] Etapa 5 (histórico) aprovada e concluída.
- [x] Etapa 6 (acessibilidade/polimento) concluída.
- [x] Datas Seerr-only definidas (F-09/F-10): `updatedAt` aproximado; “sem data” quando ausente.
- [x] Filtros definidos (F-36): chips + select contextual; origem separada no Histórico.
- [x] Ajuda do WOL definida (F-37).
- [x] “Como funciona” cobre modo remoto, escopo dublado, Pedidos vs Legendas e início do histórico (F-38/F-39).
- [x] Etapa 7 (reavaliação/testes finais) concluída.
- [ ] Decisões da seção 6 confirmadas.
- [x] Etapas 1, 0.5, 2, 3, 4, 5, 6 e 7 concluídas.

---

**Observação:** este documento é a fonte de verdade do plano. Todas as etapas foram implementadas e publicadas em 2026-10-28; o painel de armazenamento anterior permanece. Itens opcionais ainda em aberto: estado de sub-aba/filtros na URL e tema claro.
