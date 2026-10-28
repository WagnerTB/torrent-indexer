# Auditoria de Segurança — arquivos versionados e stack vivo

- **Data:** 2026-10-27
- **Status:** verificação e remediação concluídas; nenhum serviço essencial ficou fora do ar
- **Escopo:** arquivos rastreados pelo Git, templates de deploy, runbooks e configuração viva do Pi
- **Método:** `git ls-files`, varredura por regex (credenciais, IPs privados/Tailscale/públicos, MAC, e-mail, usuário e caminhos), inspeção mascarada dos configs, conferência do histórico do `docker-compose.yml` e validação com `docker compose config`.

> Os valores sensíveis foram mascarados nesta auditoria. O relatório bruto da varredura fica fora do repositório, em arquivo temporário local.

## 1. Resumo

- **54 arquivos rastreados** analisados; nenhuma API key pessoal encontrada.
- O `docker-compose.yml` usava o **default público do projeto** (`my-secret-key`) para o Meilisearch. Foi substituído por `${MEILI_MASTER_KEY:?set MEILI_MASTER_KEY in .env}`.
- O histórico do compose (7 commits) contém **apenas esse default**; nenhum valor não-default apareceu.
- Os templates de deploy tinham chave real do Meilisearch, IPs LAN/Tailscale e MAC; foram sanitizados para placeholders/`${...}`.
- Os runbooks tinham IPs privados/Tailscale, MAC, IP público, usuário e caminhos; foram sanitizados. As versões com valores reais ficaram em `*.local.md` (ignoradas).
- O **stack vivo** foi ajustado: `.env` com os valores reais (600), compose parametrizado (600), Meilisearch alinhado à chave forte do `.env`, senha do WOL movida para `.env` e agente lendo ambiente. O `.gaming_password` legado foi removido.
- `meilisearch`, `torrent-indexer` e `gaming-agent` foram recriados. Busca no indexer retornou **HTTP 200**; status e wake do gaming retornaram **HTTP 200**.

## 2. Achados e ações

### 2.1 Arquivos rastreados

| Arquivo | Achado | Classificação | Ação |
|---|---|---|---|
| `docker-compose.yml` | `MEILI_MASTER_KEY`/`MEILISEARCH_KEY` com o default público `my-secret-key` | Default público, não chave pessoal | Variável `${MEILI_MASTER_KEY:?...}`; `.env.example` criado; README atualizado |
| `docker-compose.yml` (comentários) | Caminhos `/home/<usuário>/cache` | Caminho pessoal em comentário | Genericizado para `/home/<user>/cache` |
| `cache/redis.go` | `Password: <identificador>` | **Falso positivo** (variável, não literal) | Nenhuma |
| `search/meilisearch.go` | `APIKey: <identificador>` | **Falso positivo** (variável, não literal) | Nenhuma |
| `utils/constant.go` | “IP público” dentro do User-Agent do Chrome | **Falso positivo** (versão do Chrome) | Nenhuma |
| `Dockerfile`, `.github/workflows/pipeline.dockerfile` | E-mail de maintainer | Contato público do projeto upstream | Mantido; remover apenas se desejado |

### 2.2 Templates de deploy

| Arquivo | Achado | Ação |
|---|---|---|
| `deploy/raspberry/.env.example` | Chave real do Meilisearch; IP Tailscale, MAC e broadcast reais | Placeholders para `MEILI_MASTER_KEY`, `LAN_IP`, `TAILSCALE_IP`, `PC_IP`, `PC_MAC`, `LAN_BROADCAST`, `GAMING_PASSWORD`, `ALLOWED_NETWORKS` |
| `deploy/raspberry/docker-compose.yml` | Chave real do Meilisearch; IPs LAN/Tailscale e MAC | `${MEILI_MASTER_KEY:?}`, `${LAN_IP:?}`, `${ALLOWED_NETWORKS:?}`, `${PC_IP:?}`, `${PC_MAC:?}`, `${GAMING_PASSWORD:?}`, `${LAN_BROADCAST:?}` |
| `deploy/raspberry/media-stack.service` | `WorkingDirectory=/home/<usuário>/media-stack` | `/opt/media-stack` com comentário para ajustar ao caminho real |

- O `media-agent` continua com `LISTEN_HOST: 0.0.0.0`; apenas o listener privado do `gaming-agent` usa `${LAN_IP}`.
- As portas LAN e as URLs de Bazarr/Radarr/Sonarr/Seerr usam `${LAN_IP}`.
- O template não contém mais IPs/MAC/chave/senha reais.

### 2.3 Runbooks e docs

| Arquivo | Achado | Ação |
|---|---|---|
| `MEDIA_STACK.md` | IPs privados, Tailscale, MAC, IP público, usuário e caminhos | Sanitizado com placeholders; nota de segurança no topo |
| `SITE_STATUS.md` | IPs privados/Tailscale e IP público | Sanitizado |
| `RASPBERRY_PI.md` | IPs privados, usuário e caminhos | Sanitizado |
| `PROJECT_OVERVIEW.md` | IPs privados e caminhos | Sanitizado |
| `UI_AUDIT.md` | IP Tailscale e caminho absoluto | Sanitizado |

- As versões com valores reais foram copiadas para `MEDIA_STACK.local.md`, `SITE_STATUS.local.md`, `RASPBERRY_PI.local.md` e `PROJECT_OVERVIEW.local.md`; estão no `.gitignore` (`*.local.md`) e **não devem ser commitadas**.
- `RASPBERRY_PI.md` tinha `PWD=$PWD`; é variável de shell, **falso positivo**, não senha.
- As ocorrências de `.gaming_password`, `.bazarr_key`, `config.xml`, `settings.json` e `.env` nos docs são **nomes de arquivos/caminhos**, não valores.

### 2.4 WOL

- A senha do WOL agora vem de **`GAMING_PASSWORD` no `.env`** (600, fora do Git). O arquivo `.gaming_password` legado foi removido do host.
- `PC_IP`, `PC_MAC` e `LAN_BROADCAST` também vêm do `.env`; o compose passa esses valores ao agente.
- O `gaming-agent` no Pi agora lê `PC_IP`/`PC_MAC`/`LAN_BROADCAST`/`GAMING_PASSWORD` do ambiente e não tem mais IP/MAC como defaults no código.
- O `wake()` ganhou guarda para `PC_MAC` vazio; o endpoint público continua exigindo a senha. O status público não expõe IP/MAC.
- Teste real: status **200** e wake com a senha do `.env` **200**; o arquivo legado foi removido e o wake foi repetido com sucesso usando só o `.env`.
- O `gaming-agent` no Pi roda a partir de `<MEDIA_ROOT>/docker/gaming-agent/agent.py` (NTFS); o arquivo ficou 775, mas **não contém mais segredos**. A senha está no `.env` 600.

## 3. Histórico do Git

- O `docker-compose.yml` foi tocado em **7 commits**.
- Os únicos valores encontrados para `MEILI_MASTER_KEY`/`MEILISEARCH_KEY` são o default público `my-secret-key`.
- **Nenhum valor não-default/não-variável** apareceu nesses 7 commits.
- Os templates de deploy, os runbooks pessoais e o `UI_AUDIT.md` estavam **untracked**; não há valores deles no histórico deste repositório.
- Se esses arquivos já foram compartilhados/commitados em outro lugar, as chaves reais antigas devem ser rotacionadas.

## 4. Mudanças aplicadas no repositório

- `.gitignore`: `.env`, `.env.*`, `!.env.example`, `.gaming_password`, `.bazarr_key`, `*.pem`, `*.key`, `requests.db`, `state/`, `*.local.md`, `*.bak.*` e artefatos de build locais.
- `.env.example` raiz: criado com `MEILI_MASTER_KEY` placeholder.
- `docker-compose.yml`: chave do Meilisearch via `.env`; comentários com caminho pessoal genericizados.
- `deploy/raspberry/.env.example`: placeholders para chave, LAN/Tailscale, PC_IP/PC_MAC/LAN_BROADCAST e `GAMING_PASSWORD`.
- `deploy/raspberry/docker-compose.yml`: parâmetros de ambiente em vez de valores reais, incluindo `GAMING_PASSWORD`.
- `deploy/raspberry/media-stack.service`: caminho genérico `/opt/media-stack`.
- `README.md`: passo de `.env` no deploy e seção “Secrets and local configuration”, incluindo WOL.
- Runbooks e `UI_AUDIT.md`: placeholders; backups locais `.local.md`.
- `SECURITY_AUDIT.md`: este documento.

## 5. Mudanças aplicadas no stack vivo (Pi)

- `.env` do stack (`<STACK_ROOT>/.env`, 600) agora tem `LAN_IP`, `PC_IP`, `PC_MAC`, `LAN_BROADCAST`, `ALLOWED_NETWORKS` e `GAMING_PASSWORD`.
- `docker-compose.yml` vivo (600) foi parametrizado; a chave do Meilisearch deixou de ser literal e passou a usar `${MEILI_MASTER_KEY}`.
- A chave viva do `.env` tem 64 caracteres; o literal antigo do compose (19) divergia e foi aposentado. O indexer já usava a chave do `.env`; após alinhar o Meilisearch, a busca voltou a funcionar (**HTTP 200**).
- O `gaming-agent` vivo foi ajustado para ler ambiente, sem defaults de IP/MAC; a senha do WOL foi movida para `.env`; o `.gaming_password` foi removido.
- Backups do stack vivo criados com 600: `.env.bak.*` e `docker-compose.yml.bak.*` (sufixos `20261028-000003` e `20261028-000400`). Os backups de `agent.py` e o `__pycache__` foram removidos.
- `meilisearch`, `torrent-indexer` e `gaming-agent` foram recriados. Verificações: indexer `/search` **200**; `/gaming/status` **200**; `/gaming/wake` com a senha do `.env` **200**.

## 6. Ações pendentes / recomendações

1. **Backups do stack vivo:** os arquivos `*.bak.*` acima têm valores antigos (chave/IP/MAC) e estão com 600 no Pi. Apague quando não precisar de rollback; eles não estão no Git.
2. **Chaves antigas compartilhadas:** o literal de 19 caracteres foi aposentado; a chave viva é de 64 caracteres e não está no repositório. Se os templates antigos (18/30 caracteres) foram enviados a alguém, rotacione esses usos específicos — eles não são a chave viva.
3. **Config root no NTFS:** `.bazarr_key`, `config.xml` de Radarr/Sonarr e outros segredos vivos continuam sob `<MEDIA_ROOT>/docker` (NTFS), fora do Git. Se a mídia for exposta por Samba/NFS, considere mover o config root para o ext4 (`<DOCKER_DATA_ROOT>`) com 600.
4. **E-mail de maintainer:** é contato público upstream; mantido. Remova se não quiser expor.
5. **Root `.env` local:** o repositório tem `.env.example`; o `.env` real é local e ignorado. O stack vivo já tem o seu.
6. **Backups `.local.md`:** são locais e ignorados; não commitar.

## 7. Verificação

- `docker compose config` no repositório (raiz) e no template do Raspberry Pi: **exit 0** (com `.env` de teste).
- `docker compose config` no stack vivo: **exit 0**.
- Serviços recriados: `meilisearch`, `torrent-indexer`, `gaming-agent`.
- Indexer `/search?q=bleach`: **HTTP 200** com resultados.
- Gaming `/gaming/status`: **HTTP 200**; `/gaming/wake` com `GAMING_PASSWORD`: **HTTP 200**.
- Varredura repetida: os achados restantes nos arquivos rastreados são falsos positivos (identificadores Go, versão do Chrome) ou o e-mail público de maintainer. Templates/docs não têm mais IP/MAC/chave/senha reais; restam nomes de arquivos.
- Nada foi commitado.

## 8. Falsos positivos registrados

- `cache/redis.go`: `Password:` recebe uma variável, não um literal.
- `search/meilisearch.go`: `APIKey:` recebe uma variável, não um literal.
- `utils/constant.go`: o “IP” é a versão do Chrome no User-Agent.
- `RASPBERRY_PI.md`: `PWD=$PWD` é variável de shell.
- E-mails em `Dockerfile`/workflow: contato público do projeto upstream.
- Caminhos para `.gaming_password`, `.bazarr_key`, `config.xml`, `settings.json` nos docs: nomes de arquivos, não valores.
