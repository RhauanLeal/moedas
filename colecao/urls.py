from django.urls import path

from . import views, views_app, views_catalogo

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("serie/<int:pk>/", views.serie_detalhe, name="serie"),
    path("faltando/", views.faltando, name="faltando"),
    path("compartilhar/", views.compartilhar, name="compartilhar"),
    path("buscar/", views.buscar, name="buscar"),
    path("moeda/<int:pk>/marcar/", views.marcar, name="marcar"),
    path("moeda/<int:pk>/", views.ficha, name="ficha"),
    # coleções e catálogo próprio
    path("colecoes/", views_catalogo.colecoes, name="colecoes"),
    path("colecoes/nova/", views_catalogo.nova_colecao, name="nova_colecao"),
    path("colecoes/backup/", views_catalogo.exportar_tudo, name="exportar_tudo"),
    path("colecoes/importar/", views_catalogo.importar_backup, name="importar_backup"),
    path("colecao/<int:pk>/", views.abrir_colecao, name="abrir_colecao"),
    path("colecao/<int:pk>/editar/", views_catalogo.editar_colecao, name="editar_colecao"),
    path("colecao/<int:pk>/ocultar/", views_catalogo.ocultar_colecao, name="ocultar_colecao"),
    path("colecao/<int:pk>/zerar/", views_catalogo.zerar_colecao, name="zerar_colecao"),
    path("colecao/<int:pk>/exportar/", views_catalogo.exportar_colecao, name="exportar_colecao"),
    path("colecao/<int:pk>/valores/", views_catalogo.valores_colecao, name="valores_colecao"),
    path("colecao/<int:pk>/serie/nova/", views_catalogo.nova_serie, name="nova_serie"),
    path("serie/<int:pk>/editar/", views_catalogo.editar_serie, name="editar_serie"),
    path("serie/<int:pk>/moeda/nova/", views_catalogo.nova_moeda, name="nova_moeda"),
    path("moeda/<int:pk>/editar/", views_catalogo.editar_moeda, name="editar_moeda"),
    path("media/fotos/<int:dono_id>/<str:nome>", views_catalogo.foto, name="foto_enviada"),
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
