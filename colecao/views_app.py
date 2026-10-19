"""Telas e endpoints do "app": conta, novidades, privacidade, PWA e notificações."""
import json

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST

from .models import Aviso, InscricaoPush

VERSAO_CACHE = "v4"  # aumente quando mudar o service worker para forçar atualização


# ---------- conta ----------

@login_required
def conta(request):
    return render(
        request,
        "colecao/conta.html",
        {
            "tem_senha": request.user.has_usable_password(),
            "contas_sociais": request.user.socialaccount_set.all(),
        },
    )


@login_required
def excluir_conta(request):
    """Exclusão definitiva da conta e da coleção (exigência da LGPD e da Play Store)."""
    if request.method == "POST":
        if request.POST.get("confirmacao", "").strip().upper() != "EXCLUIR":
            messages.error(request, 'Digite EXCLUIR para confirmar.')
            return redirect("excluir_conta")
        user = request.user
        logout(request)
        user.delete()  # apaga também a coleção, inscrições de notificação e logins do Google
        messages.success(request, "Sua conta e sua coleção foram excluídas.")
        return redirect("account_login")
    return render(request, "colecao/excluir_conta.html")


def privacidade(request):
    return render(request, "colecao/privacidade.html")


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
    if not endpoint.startswith("https://"):
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
