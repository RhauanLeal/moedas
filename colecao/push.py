"""Envio de notificações Web Push (as que aparecem no celular)."""
import json
import logging

from django.conf import settings

from .models import Aviso, InscricaoPush

log = logging.getLogger(__name__)


def push_configurado():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def enviar_aviso(aviso: Aviso) -> int:
    """Manda o aviso para todos os aparelhos inscritos. Devolve quantos receberam."""
    if not push_configurado():
        return 0
    from pywebpush import WebPushException, webpush

    url = (aviso.link or "/novidades/").strip()
    if not url.startswith("/"):
        url = "/novidades/"
    payload = json.dumps({"title": aviso.titulo, "body": aviso.texto, "url": url})
    email_vapid = (settings.VAPID_EMAIL or "admin@localhost").strip()
    if email_vapid.startswith("mailto:"):
        email_vapid = email_vapid[7:]
    claims = {"sub": f"mailto:{email_vapid}"}
    enviados = 0
    for inscricao in InscricaoPush.objects.all().iterator():
        try:
            webpush(
                subscription_info={
                    "endpoint": inscricao.endpoint,
                    "keys": {"p256dh": inscricao.p256dh, "auth": inscricao.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims=dict(claims),
                ttl=60 * 60 * 24,
                timeout=5,
            )
            enviados += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                # aparelho desinstalou o app ou cancelou: remove a inscrição
                inscricao.delete()
            else:
                log.warning("Falha no push para %s: %s", inscricao.pk, e)
        except Exception as e:  # rede, timeout etc. — não derruba o envio dos outros
            log.warning("Falha no push para %s: %s", inscricao.pk, e)
    return enviados
