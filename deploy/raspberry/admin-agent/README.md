# Admin Agent

Agente LAN-only para administrar os containers Docker do stack de mídia pelo
Homepage. Ele **não** lê o `docker-compose.yml`, o `.env` nem arquivos de
configuração dos serviços.

## Escopo

- Lista os containers do projeto Compose `media` e mostra estado, health,
  uptime, imagem e portas.
- Ações permitidas: `start`, `stop` e `restart`.
- Serviços protegidos: `admin-agent`, `docker-socket-proxy` e `autoheal`.
- Sem `exec`, imagens, volumes, redes, compose ou `.env`.
- Acesso somente pela LAN, com senha dedicada e auditoria.

## Segurança

- O único componente com `/var/run/docker.sock` é o `docker-socket-proxy`.
- O proxy fica em uma rede Docker interna (`admin-internal`), sem porta
  publicada e sem acesso dos demais containers do stack.
- O proxy libera apenas `CONTAINERS`, `POST`, `ALLOW_START`, `ALLOW_STOP` e
  `ALLOW_RESTARTS`; todo o resto é negado.
- O `admin-agent` escuta em `<LAN_IP>:8093` (porta publicada só no IP da
  LAN), valida a rede de origem, a origem CORS e a senha.
- A senha fica em `<ADMIN_PASSWORD_PATH>` (600, fora do
  git) e é montada em `/run/secrets/admin_password`; é lida a cada request, então
  trocar o arquivo não exige restart.
- Após 5 falhas de senha por minuto, o IP fica bloqueado por 1 minuto.
- Toda ação e falha de autenticação vai para `state/admin-audit.jsonl`.

O proxy permite `GET /containers/*` (incluindo inspect) porque a API do Docker
não separa "listar" de "inspecionar" nessa imagem. Por isso ele só existe na
rede interna, compartilhada apenas com o `admin-agent`. Nunca publique a porta
`2375`.

## Arquivos no Pi

```
<CONFIG_ROOT>/admin-agent/
├── admin_agent.py
├── Dockerfile
└── state/
    └── admin-audit.jsonl

$HOME/.config/admin-agent/
└── password             # 600, montado em /run/secrets/admin_password
```

## Configuração

Variáveis principais (já definidas no compose versionado):

| Variável | Padrão | Uso |
|---|---|---|
| `LISTEN_PORT` | `8093` | porta do agente |
| `ADMIN_ALLOWED_NETWORKS` | `127.0.0.0/8,::1/128,<LAN_SUBNET>` | redes que podem acessar |
| `ADMIN_ALLOWED_ORIGINS` | `http://<LAN_IP>:3000,...` | origens CORS do Homepage |
| `ADMIN_PASSWORD_FILE` | `/run/secrets/admin_password` | senha dedicada (mount externo) |
| `ADMIN_PASSWORD_PATH` | `<ADMIN_PASSWORD_PATH>` | caminho da senha no host (compose) |
| `DOCKER_URL` | `http://docker-socket-proxy:2375` | proxy interno |
| `COMPOSE_PROJECT` | `media` | projeto Compose gerenciado |
| `AUDIT_FILE` | `/state/admin-audit.jsonl` | auditoria |

Se o Homepage for acessado por outro hostname da LAN, inclua a origem em
`ADMIN_ALLOWED_ORIGINS` (ex.: `http://<LAN_HOSTNAME>:3000`). Em modo remoto/Tailscale a
aba Admin fica oculta, por decisão de escopo.

## Gerar a senha

```sh
mkdir -p $HOME/.config/admin-agent
chmod 700 $HOME/.config/admin-agent
printf '%s' "$(openssl rand -base64 24)" > <ADMIN_PASSWORD_PATH>
chmod 600 <ADMIN_PASSWORD_PATH>
mkdir -p <CONFIG_ROOT>/admin-agent/state
chown <PUID>:<PGID> <CONFIG_ROOT>/admin-agent/state
```

O caminho do host é montado pelo compose via `ADMIN_PASSWORD_PATH`. O motivo de
não deixar a senha em `<CONFIG_ROOT>` é que esse filesystem (fuseblk) não
respeita `chmod 600`.

Para trocar depois, basta reescrever o arquivo; não precisa reiniciar.

## Subir

```sh
cd <STACK_ROOT>
docker compose up -d --build docker-socket-proxy admin-agent
docker compose ps docker-socket-proxy admin-agent
docker logs --tail 50 admin-agent
```

## Testar

```sh
PASS="$(cat <ADMIN_PASSWORD_PATH>)"
curl -s http://<LAN_IP>:8093/health
curl -s -H "X-Admin-Password: $PASS" http://<LAN_IP>:8093/admin/services | python3 -m json.tool
curl -s -o /dev/null -w '%{http_code}\n' -H 'X-Admin-Password: errada' http://<LAN_IP>:8093/admin/services
```

Reiniciar um serviço de teste (FlareSolverr costuma ser seguro):

```sh
curl -s -X POST \
  -H "X-Admin-Password: $PASS" \
  -H 'Content-Type: application/json' \
  -d '{"confirm":"solvearr"}' \
  http://<LAN_IP>:8093/admin/services/solvearr/restart
```

Auditoria:

```sh
curl -s -H "X-Admin-Password: $PASS" 'http://<LAN_IP>:8093/admin/audit?limit=20' | python3 -m json.tool
```

## Desenvolvimento

```sh
python3 -m py_compile admin_agent.py
python3 -m unittest test_admin_agent -v
```

## Rollback

```sh
cd <STACK_ROOT>
docker compose stop admin-agent docker-socket-proxy
docker compose rm -f admin-agent docker-socket-proxy
# restaurar o docker-compose.yml.bak.<timestamp> se necessário
```
