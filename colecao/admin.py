from django.contrib import admin, messages

from .models import Aviso, Colecao, Denominacao, InscricaoPush, ItemColecao, Moeda, PerfilPublico, Serie
from .push import enviar_aviso, push_configurado


@admin.register(Colecao)
class ColecaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "dono", "simbolo", "slug", "ordem")
    list_filter = (("dono", admin.EmptyFieldListFilter),)
    search_fields = ("nome", "dono__email", "dono__username")
    raw_id_fields = ("dono",)
    exclude = ("ocultada_por",)


@admin.register(Serie)
class SerieAdmin(admin.ModelAdmin):
    list_display = ("nome", "colecao", "tipo", "ordem")
    list_editable = ("ordem",)
    list_filter = ("colecao", "tipo")
    list_select_related = ("colecao",)


@admin.register(Denominacao)
class DenominacaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "valor_centavos", "colecao")
    list_filter = ("colecao",)
    list_select_related = ("colecao",)


@admin.register(Moeda)
class MoedaAdmin(admin.ModelAdmin):
    list_display = ("denominacao", "ano", "variante", "descricao", "serie", "dono", "com_foto")
    list_filter = ("serie__colecao", "serie__tipo")
    search_fields = ("busca", "serie__colecao__dono__email", "serie__colecao__dono__username")
    list_select_related = ("serie__colecao__dono", "denominacao")

    @admin.display(description="Dono", ordering="serie__colecao__dono")
    def dono(self, obj):
        return obj.serie.colecao.dono
    actions = ["criar_aviso"]

    @admin.display(boolean=True, description="Foto")
    def com_foto(self, obj):
        return obj.tem_foto

    @admin.action(description="Avisar os usuários sobre estas moedas (notificação)")
    def criar_aviso(self, request, queryset):
        if queryset.filter(serie__colecao__dono__isnull=False).exists():
            self.message_user(request, "Avisos só para moedas de coleções oficiais (as dos usuários são privadas).", messages.ERROR)
            return
        moedas = list(queryset.select_related("serie", "denominacao")[:5])
        if not moedas:
            return
        nomes = ", ".join(
            f"{m.denominacao} {m.ano_rotulo}" + (f" ({m.descricao})" if m.descricao else "")
            for m in moedas
        )
        titulo = "Moeda nova no catálogo" if len(moedas) == 1 else "Moedas novas no catálogo"
        aviso = Aviso.objects.create(
            titulo=titulo,
            texto=f"{nomes}. Confira se já está na sua coleção!"[:240],
            link=f"/serie/{moedas[0].serie_id}/",
        )
        _enviar_e_informar(self, request, aviso)


@admin.register(ItemColecao)
class ItemColecaoAdmin(admin.ModelAdmin):
    list_display = ("moeda", "user", "quantidade", "estado", "atualizado_em")
    list_filter = ("estado", "moeda__serie__colecao")
    search_fields = ("moeda__busca", "user__email", "user__username")
    autocomplete_fields = ("moeda",)
    raw_id_fields = ("user",)


def _enviar_e_informar(modeladmin, request, aviso):
    if not push_configurado():
        modeladmin.message_user(
            request,
            "Aviso publicado em Novidades. Notificações push não estão configuradas (faltam as chaves VAPID no .env).",
            messages.WARNING,
        )
        return
    n = enviar_aviso(aviso)
    aviso.enviados = n
    aviso.save(update_fields=["enviados"])
    modeladmin.message_user(request, f"Aviso publicado e enviado para {n} aparelho(s).")


@admin.register(Aviso)
class AvisoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "criado_em", "enviados")
    readonly_fields = ("enviados",)
    actions = ["reenviar"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:  # só envia ao criar; editar não reenvia
            _enviar_e_informar(self, request, obj)

    @admin.action(description="Reenviar notificação")
    def reenviar(self, request, queryset):
        for aviso in queryset:
            _enviar_e_informar(self, request, aviso)


@admin.register(InscricaoPush)
class InscricaoPushAdmin(admin.ModelAdmin):
    list_display = ("user", "criado_em", "endpoint")
    raw_id_fields = ("user",)


@admin.register(PerfilPublico)
class PerfilPublicoAdmin(admin.ModelAdmin):
    list_display = ("user", "nome", "ativo", "compartilhar_estado")
    list_filter = ("ativo", "compartilhar_estado")
    search_fields = ("user__email", "user__username", "nome")
    raw_id_fields = ("user",)

