"""Versão 2.0: o catálogo atual passa a ser a coleção oficial "Real".

Todas as séries e denominações que já existem são ligadas a ela. Os itens que as
pessoas marcaram (ItemColecao) apontam para as moedas e não mudam.
Numa base nova a coleção também é criada; o carregar_catalogo preenche as moedas.
"""
from django.db import migrations


def criar_real(apps, schema_editor):
    Colecao = apps.get_model("colecao", "Colecao")
    Serie = apps.get_model("colecao", "Serie")
    Denominacao = apps.get_model("colecao", "Denominacao")
    real, _ = Colecao.objects.get_or_create(slug="real", defaults={"nome": "Real", "simbolo": "R$"})
    Serie.objects.filter(colecao__isnull=True).update(colecao=real)
    Denominacao.objects.filter(colecao__isnull=True).update(colecao=real)


def desfazer(apps, schema_editor):
    # Só funciona antes de existirem coleções criadas por usuários (os nomes voltam a ser únicos).
    Colecao = apps.get_model("colecao", "Colecao")
    apps.get_model("colecao", "Serie").objects.update(colecao=None)
    apps.get_model("colecao", "Denominacao").objects.update(colecao=None)
    Colecao.objects.filter(slug="real").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("colecao", "0007_colecoes"),
    ]

    operations = [
        migrations.RunPython(criar_real, desfazer),
    ]
