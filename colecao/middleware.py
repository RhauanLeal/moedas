"""Middleware de verificação de saúde (healthcheck do Docker / Beszel)."""
from django.db import connection
from django.http import HttpResponse

CAMINHO_SAUDE = "/saude/"


class SaudeMiddleware:
    """Responde em /saude/ antes dos demais middlewares.

    O healthcheck roda dentro do container (Host: localhost), que pode não estar
    em ALLOWED_HOSTS em produção; por isso a resposta sai daqui, sem validar o
    host nem passar por sessão/login. Confere também se o banco responde.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path != CAMINHO_SAUDE:
            return self.get_response(request)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            return HttpResponse("banco indisponível", status=503, content_type="text/plain; charset=utf-8")
        return HttpResponse("ok", content_type="text/plain; charset=utf-8")
