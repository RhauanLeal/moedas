# Moedas do Real

Controle da coleção de moedas do Plano Real (1994–2026), feito para o celular.
Django 5.2 + HTMX + PostgreSQL, rodando em Docker.

- **Busca rápida**: achou uma moeda? Digite `50 2008`, `1 real 2019`, `5c 2019a` ou `natação`.
- **Um toque** numa moeda que você não tem marca 1 unidade.
- **Toque numa moeda que você tem** abre a ficha: quantidade (− / +), estado de conservação (UTGC, BC, MBC, SOB, FC), data e observação.
- **Faltando**: lista tudo o que ainda falta, por série.
- **Contas**: cada pessoa tem a sua coleção. Cadastro por e-mail ou "Continuar com Google".
- **App instalável (PWA)**: ícone na tela inicial, tela cheia e páginas já visitadas abrem sem internet.
- **Notificações**: aviso no celular quando sai moeda nova (você dispara pelo admin).
- **Admin** (`/admin/`): cadastrar moedas novas (ex.: 2027 ou uma nova comemorativa) e mandar avisos.
- **LGPD**: política de privacidade em `/privacidade/` e exclusão da conta pelo próprio usuário.

O catálogo das 193 moedas da lista de controle é carregado automaticamente na primeira subida.
A coleção que já existia antes das contas fica com o primeiro administrador (o usuário `rhauan`).

---

## 1. Banco — na VM `ubuntu-postgresql` (VMID 101)

Entre na VM do Postgres e abra o `psql` como administrador:

```bash
# >>> rodar na VM ubuntu-postgresql
sudo -u postgres psql
```

Dentro do `psql`, crie usuário e banco (troque a senha):

```sql
CREATE USER moedas WITH PASSWORD 'troque-esta-senha-do-banco';
CREATE DATABASE moedas OWNER moedas;
\q
```

Se o SNFISC já conecta nessa VM a partir da `ubuntu-server`, o Postgres já aceita conexões dela.
Para conferir, veja se existe uma linha liberando o IP `192.168.30.6` no `pg_hba.conf`:

```bash
# >>> rodar na VM ubuntu-postgresql
sudo grep -n "192.168.30" /etc/postgresql/*/main/pg_hba.conf
```

Se a linha liberar só o banco do SNFISC (e não `all`), acrescente esta e recarregue:

```bash
# >>> rodar na VM ubuntu-postgresql
echo "host  moedas  moedas  192.168.30.6/32  scram-sha-256" | sudo tee -a /etc/postgresql/*/main/pg_hba.conf
sudo systemctl reload postgresql
```

## 2. App — na VM `ubuntu-server` (192.168.30.6)

Copie a pasta do projeto para `/srv/projects/moedas` (por `scp`, a partir de uma das máquinas que têm acesso SSH à VM). Depois:

```bash
# >>> rodar na VM ubuntu-server
cd /srv/projects/moedas
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # copie o resultado
nano .env
```

No `.env`, preencha pelo menos:

- `DJANGO_SECRET_KEY`: o valor gerado acima.
- `DJANGO_SUPERUSER_PASSWORD`: a senha que você vai usar para entrar no app.
- `DB_HOST`: o IP da VM `ubuntu-postgresql`.
- `DB_PASSWORD`: a senha criada no passo 1.

Suba o container:

```bash
# >>> rodar na VM ubuntu-server, dentro de /srv/projects/moedas
docker compose up -d --build
docker compose logs -f moedas      # Ctrl+C para sair dos logs
```

Nos logs deve aparecer `Catálogo pronto: 193 moeda(s) nova(s), 193 no total.`

Teste no celular (na rede de casa): **http://192.168.30.6:8010**

> Se o celular estiver na VLAN da casa (192.168.1.x) e não abrir, confira no UniFi se a VLAN 1 pode acessar a rede 192.168.30.x na porta 8010.

**Dica:** no navegador do celular, use "Adicionar à tela inicial" para abrir como se fosse um app.

## 3. Publicar em moedas.linario.dev.br (Cloudflare Tunnel)

1. **No painel da Cloudflare** (Zero Trust › Networks › Tunnels), no túnel que já publica o SNFISC, adicione um *Public Hostname*:
   - `moedas.linario.dev.br` → `HTTP` → `192.168.30.6:8010`
   - Se o `cloudflared` roda na própria `ubuntu-server`, use `localhost:8010`.
2. **Na VM `ubuntu-server`**, no `.env`, troque as três linhas da "fase de testes" pelas de "produção" (estão comentadas no arquivo). Depois recrie o container:

```bash
# >>> rodar na VM ubuntu-server, dentro de /srv/projects/moedas
docker compose up -d
```

Com `DJANGO_SECURE_COOKIES=True`, o login só funciona pelo endereço https. Para voltar a testar por `http://192.168.30.6:8010`, volte o valor para `False`.

## 4. Login com Google

1. Acesse **console.cloud.google.com** com a sua conta Google e crie um projeto (ex.: "Moedas do Real").
2. Em **APIs e serviços › Tela de consentimento OAuth** (ou "Google Auth Platform"):
   - Tipo de usuário: **Externo**. Nome do app: "Moedas do Real". E-mail de suporte: o seu.
   - Escopos: só os básicos (`email`, `profile`, `openid`) — esses não exigem verificação do Google.
   - Enquanto estiver em **Teste**, só os e-mails que você colocar em "Usuários de teste" conseguem entrar. Para abrir para todos, clique em **Publicar app**.
3. Em **Credenciais › Criar credenciais › ID do cliente OAuth**:
   - Tipo: **Aplicativo da Web**.
   - **URIs de redirecionamento autorizados** (cadastre os dois):
     - `http://localhost:8020/contas/google/login/callback/` (testes no seu PC)
     - `https://moedas.linario.dev.br/contas/google/login/callback/` (produção)
4. Copie o **ID do cliente** e a **Chave secreta** para o `.env`:

```dotenv
GOOGLE_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxx
```

5. Recrie o container (`docker compose up -d`). O botão "Continuar com Google" aparece sozinho.

Se alguém entra com o Google usando o mesmo e-mail de uma conta já cadastrada, as duas viram uma só.

## 5. Notificações

Gere as chaves **uma vez só** (se trocar depois, todo mundo precisa ativar de novo):

```bash
# >>> rodar onde o container estiver (PowerShell no PC, ou VM ubuntu-server)
docker compose exec moedas python manage.py gerar_chaves_push
```

Copie as duas linhas que aparecem para o `.env`, preencha `VAPID_EMAIL` com o seu e-mail e rode `docker compose up -d`.

- Cada pessoa ativa em **🔔 Novidades** ou em **Minha conta › Notificações**.
- Para avisar todo mundo: `/admin/` › **Avisos** › Adicionar (título, texto e, se quiser, um link como `/serie/3/`). Ao salvar, o aviso aparece em Novidades e é enviado para os celulares.
- Atalho: em `/admin/` › **Moedas**, marque as moedas novas e use a ação **"Avisar os usuários sobre estas moedas"**.

> Notificações e instalação do app **só funcionam com HTTPS** (ou em `localhost`). Pelo IP da rede (`http://192.168.30.6:8010`) o app funciona, mas sem instalar nem notificar. Pelo `https://moedas.linario.dev.br` funciona tudo.
> No iPhone, a pessoa precisa primeiro **adicionar à Tela de Início** (iOS 16.4 ou mais novo) e abrir por lá para poder ativar as notificações.

## 6. Instalar no celular

- **Android (Chrome)**: abra o site, toque em **Instalar** no topo (ou menu ⋮ › Instalar app).
- **iPhone (Safari)**: Compartilhar › **Adicionar à Tela de Início**.

Para publicar na Play Store mais tarde, dá para empacotar este mesmo site como app Android (TWA) com o **PWABuilder** (pwabuilder.com) ou o **Bubblewrap**, sem reescrever nada.

## 7. Fechar cadastros (fase de testes)

Se quiser só você e convidados por enquanto, coloque `CADASTRO_ABERTO=False` no `.env`. Quem já tem conta continua entrando; você cria contas novas pelo `/admin/`.

## Atualizar o app (quando eu mandar uma versão nova)

```bash
# >>> rodar na VM ubuntu-server, dentro de /srv/projects/moedas
docker compose up -d --build
```

As migrações e o catálogo são aplicados sozinhos. A coleção nunca é apagada.

## Backup da coleção

```bash
# >>> rodar na VM ubuntu-postgresql
sudo -u postgres pg_dump -Fc moedas > ~/moedas-$(date +%F).dump
```

## Comandos úteis

```bash
# >>> rodar na VM ubuntu-server, dentro de /srv/projects/moedas
docker compose exec moedas python manage.py changepassword rhauan   # trocar senha
docker compose exec moedas python manage.py createsuperuser         # criar outro login
docker compose exec moedas python manage.py test colecao            # testes (usa um banco de teste temporário)
```

## Estrutura dos dados

| Tabela | O que é | Exemplo |
|---|---|---|
| `Serie` | Agrupamento, com tipo (família, comemorativa, olimpíadas) | "2ª Família", "Olimpíadas 2015 – 3ª Série" |
| `Denominacao` | Valor da moeda | "50 Centavos" (50) |
| `Moeda` | Cada "bolinha" da lista: série + valor + ano + variante + descrição | 50 Centavos · 2019 · A |
| `ItemColecao` | O que cada usuário tem daquela moeda | rhauan · quantidade 2, estado MBC |
| `Aviso` | Novidade enviada a todos (aparece em Novidades e vira notificação) | "Moeda nova no catálogo" |
| `InscricaoPush` | Celular/navegador que ativou as notificações | — |

Moeda nova (ex.: 2027): em `/admin/` › Moedas › Adicionar, escolha a série, o valor e o ano.
