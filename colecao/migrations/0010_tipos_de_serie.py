"""Tipos de série iguais para todas as coleções: Circulação, Comemorativa e Outra.

No Real, a 1ª e a 2ª Família passam para Circulação e as Olimpíadas para Comemorativa
(aparecem na seção Comemorativas, depois da série "Comemorativas").
"""
from django.db import migrations, models

MUDANCAS = {"FAMILIA": "CIRCULACAO", "OLIMPIADA": "COMEMORATIVA"}


def unificar_tipos(apps, schema_editor):
    Serie = apps.get_model("colecao", "Serie")
    for antigo, novo in MUDANCAS.items():
        Serie.objects.filter(tipo=antigo).update(tipo=novo)


def desfazer(apps, schema_editor):
    Serie = apps.get_model("colecao", "Serie")
    Serie.objects.filter(colecao__slug="real", tipo="CIRCULACAO").update(tipo="FAMILIA")
    Serie.objects.filter(colecao__slug="real", nome__startswith="Olimpíadas").update(tipo="OLIMPIADA")


class Migration(migrations.Migration):
    dependencies = [
        ("colecao", "0009_colecao_obrigatoria"),
    ]

    operations = [
        migrations.RunPython(unificar_tipos, desfazer),
        migrations.AlterField(
            model_name="serie",
            name="tipo",
            field=models.CharField(
                choices=[("CIRCULACAO", "Circulação"), ("COMEMORATIVA", "Comemorativa"), ("OUTRA", "Outra")],
                max_length=20,
            ),
        ),
    ]
