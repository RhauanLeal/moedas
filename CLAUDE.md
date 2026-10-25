# Moedas do Real — contexto para o Claude Code

App web (mobile-first) para controlar a coleção de moedas do Plano Real (1994–2026).
Responda sempre em português do Brasil.

## Stack
- Python 3.12, Django 5.2, HTMX 2 (arquivo local em `static/js/htmx.min.js`), PostgreSQL
- django-allauth 65 (login por e-mail, Google, Microsoft e Apple), pywebpush (notificações Web Push / VAPID)
- Docker (`Dockerfile` + `docker-compose.yml`), gunicorn, whitenoise
- Sem framework JS/CSS: `static/css/app.css` (variáveis CSS, modo escuro) e `static/js/app.js`

## Estrutura
- `config/` — settings (tudo vem do `.env`), urls
- `colecao/models.py` — catálogo: `Colecao` (sem dono = oficial, igual para todos e mantida pelo admin: só o Real, `slug="real"`;
  com dono = privada do usuário), `Serie` (por coleção; tipo CIRCULACAO/COMEMORATIVA/OUTRA — no Real: 1ª e 2ª Família em
  Circulação, Olimpíadas em Comemorativa), `Denominacao` (por coleção), `Moeda` (série + valor + ano + variante "A" + descrição);
  coleção: `ItemColecao` (por usuário + moeda: quantidade, estado UTGC/BC/MBC/SOB/FC, data, observação);
  notificações: `Aviso`, `InscricaoPush`
- `colecao/views.py` — telas da coleção e ações HTMX (marcar, ficha). Sempre filtrar pela coleção de `request.user`
  e buscar série/moeda por pk só dentro de `colecoes_visiveis(user)` / `moedas_visiveis(user)` (coleções privadas de outros dão 404).
  A coleção aberta fica na sessão (`colecao_atual`); `/`, Faltando, busca e compartilhar valem para ela
- `colecao/views_catalogo.py` + `colecao/forms.py` — lista de coleções (criar/excluir as próprias; ocultar, zerar o que marquei e
  exportar planilha CSV de qualquer uma, inclusive o Real) e cadastro do catálogo próprio (valores, séries, moedas com faixa de anos,
  fotos enviadas). Só edita coleções com `dono=request.user`; o Real só pelo admin e o usuário não pode excluí-lo
- `colecao/planilha.py` — backup em CSV (abre no Excel; uma linha por moeda, com coleção, catálogo e marcações): exportar e importar.
  É o jeito de levar a coleção para outro e-mail: trocar o e-mail e conectar outra conta Google/Microsoft ficam bloqueados por
  segurança (`config/urls.py` + `ContaSocialAdapter.pre_social_login`)
- `colecao/views_app.py` — conta, excluir conta (LGPD), novidades, privacidade, manifest, service worker, push
- `colecao/push.py` — envio de push; `colecao/admin.py` — salvar um Aviso novo dispara o envio
- `colecao/management/commands/carregar_catalogo.py` — cria a coleção oficial Real com as 193 moedas (idempotente, roda no entrypoint)
- `colecao/management/commands/gerar_chaves_push.py` — gera VAPID
- Fotos: `Moeda.foto_cara/foto_coroa/foto_credito/como_identificar`; arquivos em `static/moedas/*.webp` (da Wikimedia Commons, licença livre),
  mapa e créditos em `colecao/fotos.json`, regra moeda→desenho em `colecao/fotos.py`, carga idempotente em `carregar_fotos` (roda no entrypoint,
  só no Real; não sobrescreve ajustes do admin sem `--forcar`). Cara = retrato/tema, coroa = valor. Foto é por desenho (o ano não muda a imagem).
  Os scripts que montaram as imagens estão em `_fotos_rascunho/` (`montar_fotos.py`, `gerar_conferencia.py`).
  Fotos enviadas pelos usuários: `Moeda.imagem_cara/imagem_coroa` em `MEDIA_ROOT/fotos/<dono>/<uuid>.webp` (reduzidas a 800 px),
  servidas só para o dono por `views_catalogo.foto`; no Docker ficam no volume `media`. Use `url_cara`/`url_coroa` nos templates
- `templates/` — base, `sw.js` (service worker renderizado pelo Django), overrides do allauth (`account/`, `allauth/layouts/base.html`)

## Convenções
- HTMX: respostas de marcar/ficha usam `hx-swap-oob` (chip `#moeda-<id>` e barra `#progresso-total` / `#progresso-serie-<id>`); o botão usa `hx-swap="none"`
- Nunca mexer em dados da coleção ao recarregar o catálogo; moedas novas do Real vão em `carregar_catalogo` (get_or_create) ou pelo
  admin, e aparecem para todos (a ação "Avisar os usuários" do admin manda a notificação)
- Excluir coleção/conta: use `Colecao.apagar()` (as moedas têm PROTECT); o arquivo da foto só sai quando nenhuma moeda usa mais
- Mudou o service worker? Aumente `VERSAO_CACHE` em `colecao/views_app.py`
- Migrations devem preservar a coleção existente (ver `0002_colecao_por_usuario.py`)
- Rodar testes antes de terminar: `python manage.py test colecao` (sem DB_HOST usa SQLite)

## Ambiente
- Dev atual: Windows, Docker Desktop, pasta `F:\python\moedas`, app em http://localhost:8020
  Banco: Postgres do container `postgres_snfisc`, acessado do container como `host.docker.internal:5433`, banco/usuário `moedas`
- Produção planejada: VM `ubuntu-server` (192.168.30.6, projetos em `/srv/projects`), Postgres na VM `ubuntu-postgresql`,
  publicado via Cloudflare Tunnel em https://moedas.linario.dev.br
- PWA e push só funcionam em HTTPS ou localhost
- O usuário se considera leigo em administração de servidores: ao passar comandos, diga SEMPRE onde rodar
  (PowerShell do Windows, VM ubuntu-server, VM ubuntu-postgresql, host Proxmox, dentro do container…)

## Próximos passos discutidos
- Configurar credencial OAuth do Google e chaves VAPID no `.env`
- Testar com outras pessoas antes de pensar em monetização; possível app Android via TWA (PWABuilder/Bubblewrap)
