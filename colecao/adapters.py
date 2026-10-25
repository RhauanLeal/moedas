from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.providers.base.constants import AuthProcess
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect


class ContaAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        """CADASTRO_ABERTO=False no .env fecha novos cadastros (quem já tem conta continua entrando)."""
        return settings.CADASTRO_ABERTO


class ContaSocialAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return settings.CADASTRO_ABERTO

    def pre_social_login(self, request, sociallogin):
        """Não deixa ligar um Google/Microsoft de outra pessoa a uma conta já aberta.

        Quem pegasse o celular desbloqueado levaria a conta. Entrar com o Google do mesmo
        e-mail do cadastro continua funcionando (é login, não "conectar").
        """
        if sociallogin.state.get("process") == AuthProcess.CONNECT:
            messages.error(request, "Por segurança, não dá para conectar outra conta (Google, Microsoft…) depois do cadastro.")
            raise ImmediateHttpResponse(redirect("conta"))
        super().pre_social_login(request, sociallogin)
