from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from colecao.views_app import bloqueado_por_seguranca

admin.site.site_header = "Moedas do Real"
admin.site.site_title = "Moedas"
admin.site.index_title = "Catálogo, avisos e usuários"

urlpatterns = [
    path("admin/", admin.site.urls),
    # trocar o e-mail e conectar outra conta ficam desligados (antes do include, para valerem)
    path("contas/email/", bloqueado_por_seguranca),
    path("contas/3rdparty/", bloqueado_por_seguranca),
    path("contas/", include("allauth.urls")),
    # endereço antigo de login
    path("entrar/", RedirectView.as_view(pattern_name="account_login", permanent=False)),
    path("", include("colecao.urls")),
]
