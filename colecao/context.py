from django.conf import settings


def app(request):
    """Variáveis disponíveis em todos os templates."""
    return {
        "provedores_sociais": [p for p in ("google", "apple", "microsoft") if p in settings.SOCIALACCOUNT_PROVIDERS],
        "push_ativo": bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY),
        "vapid_public_key": settings.VAPID_PUBLIC_KEY,
        "cadastro_aberto": settings.CADASTRO_ABERTO,
        "contato_email": settings.CONTATO_EMAIL,
    }
