"""Coleção passa a ser por usuário.

Os itens que já existem (a coleção feita antes do multiusuário) ficam com o
primeiro superusuário cadastrado — no seu caso, o "rhauan".
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def atribuir_ao_dono(apps, schema_editor):
    ItemColecao = apps.get_model("colecao", "ItemColecao")
    if not ItemColecao.objects.exists():
        return
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    dono = (
        User.objects.filter(is_superuser=True).order_by("id").first()
        or User.objects.order_by("id").first()
    )
    if dono is None:
        # Sem nenhum usuário não há a quem atribuir; os itens órfãos são descartados.
        ItemColecao.objects.all().delete()
        return
    ItemColecao.objects.update(user=dono)


class Migration(migrations.Migration):
    dependencies = [
        ("colecao", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="itemcolecao",
            name="moeda",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="itens",
                to="colecao.moeda",
            ),
        ),
        migrations.AddField(
            model_name="itemcolecao",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="itens_colecao",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(atribuir_ao_dono, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="itemcolecao",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="itens_colecao",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="itemcolecao",
            constraint=models.UniqueConstraint(
                fields=("user", "moeda"), name="item_unico_por_usuario"
            ),
        ),
    ]
