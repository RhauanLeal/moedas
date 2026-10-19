from django.urls import path

from . import views, views_app

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("serie/<int:pk>/", views.serie_detalhe, name="serie"),
    path("faltando/", views.faltando, name="faltando"),
    path("compartilhar/", views.compartilhar, name="compartilhar"),
    path("buscar/", views.buscar, name="buscar"),
    path("moeda/<int:pk>/marcar/", views.marcar, name="marcar"),
    path("moeda/<int:pk>/", views.ficha, name="ficha"),
    # conta e páginas do app
    path("conta/", views_app.conta, name="conta"),
    path("conta/compartilhar/", views_app.compartilhar_colecao, name="compartilhar_colecao"),
    path("c/<str:token>/", views_app.colecao_publica, name="colecao_publica"),
    path("conta/excluir/", views_app.excluir_conta, name="excluir_conta"),
    path("novidades/", views_app.novidades, name="novidades"),
    path("apoie/", views_app.apoie, name="apoie"),
    path("privacidade/", views_app.privacidade, name="privacidade"),
    # PWA
    path("manifest.webmanifest", views_app.manifest, name="manifest"),
    path("sw.js", views_app.service_worker, name="service_worker"),
    path("offline/", views_app.offline, name="offline"),
    # notificações
    path("push/inscrever/", views_app.push_inscrever, name="push_inscrever"),
    path("push/cancelar/", views_app.push_cancelar, name="push_cancelar"),
]
