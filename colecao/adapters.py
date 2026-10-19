from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings


class ContaAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        """CADASTRO_ABERTO=False no .env fecha novos cadastros (quem já tem conta continua entrando)."""
        return settings.CADASTRO_ABERTO


class ContaSocialAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return settings.CADASTRO_ABERTO
