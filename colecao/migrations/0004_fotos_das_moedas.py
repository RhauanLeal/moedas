from django.db import migrations, models


class Migration(migrations.Migration):
    """Só acrescenta colunas ao catálogo; a coleção de cada usuário não é tocada."""

    dependencies = [
        ("colecao", "0003_avisos_e_notificacoes"),
    ]

    operations = [
        migrations.AddField(
            model_name="moeda",
            name="foto_cara",
            field=models.CharField(
                blank=True, max_length=200, verbose_name="foto da cara",
                help_text='Caminho dentro de static/, ex.: "moedas/f2-5-cara.webp" (lado do retrato/tema).',
            ),
        ),
        migrations.AddField(
            model_name="moeda",
            name="foto_coroa",
            field=models.CharField(
                blank=True, max_length=200, verbose_name="foto da coroa",
                help_text='Caminho dentro de static/, ex.: "moedas/f2-5-coroa.webp" (lado do valor).',
            ),
        ),
        migrations.AddField(
            model_name="moeda",
            name="foto_credito",
            field=models.CharField(blank=True, max_length=400, verbose_name="crédito das fotos"),
        ),
        migrations.AddField(
            model_name="moeda",
            name="como_identificar",
            field=models.TextField(
                blank=True, verbose_name="como identificar",
                help_text='Dica para distinguir esta moeda de outra parecida. Ex.: "Letra A no canto inferior esquerdo".',
            ),
        ),
    ]
