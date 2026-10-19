from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

admin.site.site_header = "Moedas do Real"
admin.site.site_title = "Moedas"
admin.site.index_title = "Catálogo, avisos e usuários"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("contas/", include("allauth.urls")),
    # endereço antigo de login
    path("entrar/", RedirectView.as_view(pattern_name="account_login", permanent=False)),
    path("", include("colecao.urls")),
]
