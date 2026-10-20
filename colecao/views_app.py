"""Telas e endpoints do "app": conta, novidades, privacidade, PWA e notificações."""
import json

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.http import require_POST

from django.conf import settings
from django.http import Http404

from .models import Aviso, InscricaoPush, PerfilPublico, novo_token
from .pix import payload_pix, qr_svg
from .views import agrupar_por_serie, moedas_com_colecao, progresso, series_com_progresso

VERSAO_CACHE = "v7"  # aumente quando mudar o service worker para forçar atualização


# ---------- conta ----------

@login_required
def conta(request):
    perfil, _ = PerfilPublico.objects.get_or_create(
        user=request.user, defaults={"nome": request.user.first_name[:40]}
    )
    return render(
        request,
        "colecao/conta.html",
        {
            "perfil": perfil,
            "link_publico": request.build_absolute_uri(reverse("colecao_publica", args=[perfil.token])),
            "tem_senha": request.user.has_usable_password(),
            "contas_sociais": request.user.socialaccount_set.all(),
        },
    )


@login_required
@require_POST
def compartilhar_colecao(request):
    """Liga/desliga o link público da coleção, troca o link ou as opções de compartilhamento."""
    perfil, _ = PerfilPublico.objects.get_or_create(user=request.user)
    acao = request.POST.get("acao")
    if acao == "ativar":
        perfil.nome = request.POST.get("nome", "").strip()[:40] or perfil.nome
        perfil.compartilhar_estado = request.POST.get("compartilhar_estado") == "1"
        perfil.ativo = True
        messages.success(request, "Link ativado. Quem tiver o link poderá ver sua coleção.")
    elif acao == "desativar":
        perfil.ativo = False
        messages.success(request, "Link desativado.")
    elif acao == "novo_link":
        perfil.token = novo_token()
        messages.success(request, "Novo link gerado. O anterior deixou de funcionar.")
    elif acao in ("nome", "salvar", "atualizar"):
        perfil.nome = request.POST.get("nome", "").strip()[:40]
        perfil.compartilhar_estado = request.POST.get("compartilhar_estado") == "1"
        messages.success(request, "Opções atualizadas.")
    perfil.save()
    return redirect(reverse("conta") + "#compartilhar-colecao")


@never_cache
def colecao_publica(request, token):
    """Coleção de alguém em modo somente leitura, aberta por link (sem login)."""
    perfil = get_object_or_404(PerfilPublico.objects.select_related("user"), token=token, ativo=True)
    ver = request.GET.get("ver")
    ver = ver if ver in ("faltam", "repetidas") else "todas"
    moedas = moedas_com_colecao(perfil.user)
    if ver == "faltam":
        moedas = moedas.filter(qtd=0)
    elif ver == "repetidas":
        moedas = moedas.filter(qtd__gte=2)
    por_serie = {s.pk: s for s in series_com_progresso(perfil.user)}
    grupos = agrupar_por_serie(list(moedas))
    for g in grupos:
        g["resumo"] = por_serie[g["serie"].pk]
    dados = progresso(perfil.user)
    resp = render(
        request,
        "colecao/publica.html",
        {
            "perfil": perfil,
            "ver": ver,
            "grupos": grupos,
            "progresso": dados,
            "og_titulo": f"Coleção de moedas do Real de {perfil.nome_exibido} – {dados['tenho']}/{dados['total']}",
            "og_imagem": request.build_absolute_uri(static("icones/icone-512.png")),
        },
    )
    resp["X-Robots-Tag"] = "noindex, nofollow"
    resp["Referrer-Policy"] = "no-referrer"
    return resp


@login_required
def excluir_conta(request):
    """Exclusão definitiva da conta e da coleção (exigência da LGPD e da Play Store)."""
    tem_senha = request.user.has_usable_password()
    if request.method == "POST":
        if request.POST.get("confirmacao", "").strip().upper() != "EXCLUIR":
            messages.error(request, "Digite EXCLUIR para confirmar.")
            return redirect("excluir_conta")
        if tem_senha:
            senha = request.POST.get("senha", "")
            if not request.user.check_password(senha):
                messages.error(request, "Senha incorreta. Não foi possível excluir a conta.")
                return redirect("excluir_conta")
        user = request.user
        logout(request)
        user.delete()  # apaga também a coleção, inscrições de notificação e logins do Google
        messages.success(request, "Sua conta e sua coleção foram excluídas.")
        return redirect("account_login")
    return render(request, "colecao/excluir_conta.html", {"tem_senha": tem_senha})


def privacidade(request):
    return render(request, "colecao/privacidade.html")


def apoie(request):
    if not settings.PIX_CHAVE:
        raise Http404
    codigo = payload_pix(settings.PIX_CHAVE, settings.PIX_NOME, settings.PIX_CIDADE)
    return render(request, "colecao/apoie.html", {"pix_codigo": codigo, "pix_qr": qr_svg(codigo)})


# ---------- novidades ----------

@login_required
def novidades(request):
    return render(request, "colecao/novidades.html", {"avisos": Aviso.objects.all()[:30]})


# ---------- PWA ----------

@cache_control(max_age=3600)
def manifest(request):
    dados = {
        "name": "Moedas do Real",
        "short_name": "Moedas",
        "description": "Controle da sua coleção de moedas do Plano Real.",
        "lang": "pt-BR",
        "start_url": reverse("inicio") + "?origem=app",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#f6f3ee",
        "theme_color": "#7a4a12",
        "icons": [
            {"src": static("icones/icone-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("icones/icone-512.png"), "sizes": "512x512", "type": "image/png"},
            {
                "src": static("icones/icone-maskable-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
        "shortcuts": [
            {"name": "O que falta", "url": reverse("faltando")},
            {"name": "Novidades", "url": reverse("novidades")},
        ],
    }
    return HttpResponse(json.dumps(dados, ensure_ascii=False), content_type="application/manifest+json")


@cache_control(no_cache=True)
def service_worker(request):
    resp = render(
        request,
        "sw.js",
        {
            "versao": VERSAO_CACHE,
            "precache": [
                reverse("offline"),
                static("css/app.css"),
                static("js/htmx.min.js"),
                static("js/app.js"),
                static("icones/icone-192.png"),
            ],
        },
        content_type="application/javascript",
    )
    resp["Service-Worker-Allowed"] = "/"
    return resp


def offline(request):
    return render(request, "colecao/offline.html")


from urllib.parse import urlparse

DOMINIOS_PUSH_CONFIÁVEIS = (
    "googleapis.com",
    "push.apple.com",
    "notify.windows.com",
    "push.services.mozilla.com",
)


def endpoint_push_valido(endpoint: str) -> bool:
    try:
        parsed = urlparse(endpoint)
        if parsed.scheme != "https":
            return False
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        return any(host == d or host.endswith("." + d) for d in DOMINIOS_PUSH_CONFIÁVEIS)
    except Exception:
        return False


# ---------- notificações ----------

@login_required
@require_POST
def push_inscrever(request):
    try:
        dados = json.loads(request.body)
        endpoint = dados["endpoint"]
        chaves = dados["keys"]
        p256dh, auth = chaves["p256dh"], chaves["auth"]
    except (ValueError, KeyError, TypeError):
        return HttpResponseBadRequest("inscrição inválida")
    if not endpoint_push_valido(endpoint):
        return HttpResponseBadRequest("endpoint inválido")
    InscricaoPush.objects.update_or_create(
        endpoint=endpoint, defaults={"user": request.user, "p256dh": p256dh, "auth": auth}
    )
    return JsonResponse({"ok": True})


@login_required
@require_POST
def push_cancelar(request):
    try:
        endpoint = json.loads(request.body)["endpoint"]
    except (ValueError, KeyError, TypeError):
        return HttpResponseBadRequest("pedido inválido")
    InscricaoPush.objects.filter(user=request.user, endpoint=endpoint).delete()
    return JsonResponse({"ok": True})
