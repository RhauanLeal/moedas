"""Liga as moedas do catálogo às fotos (cara e coroa) de static/moedas/.

Idempotente e seguro: só mexe nas colunas de foto/dica do catálogo, nunca na coleção.
Por padrão não sobrescreve o que você já ajustou no admin; use --forcar para refazer.

    python manage.py carregar_fotos
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from colecao.fotos import DICAS, carregar_mapa, chave_do_desenho
from colecao.models import Moeda


class Command(BaseCommand):
    help = "Preenche foto da cara/coroa, crédito e dica de identificação das moedas."

    def add_arguments(self, parser):
        parser.add_argument("--forcar", action="store_true", help="Sobrescreve fotos já definidas.")

    @transaction.atomic
    def handle(self, *args, **opts):
        mapa = carregar_mapa()
        com_foto = sem_foto = 0
        for moeda in Moeda.objects.select_related("serie", "denominacao"):
            chave = chave_do_desenho(moeda)
            desenho = mapa.get(chave)
            if not desenho:
                sem_foto += 1
                self.stdout.write(f"  sem foto: {moeda}")
                continue
            campos = {}
            if opts["forcar"] or not moeda.foto_cara:
                campos.update(foto_cara=desenho["cara"], foto_coroa=desenho["coroa"], foto_credito=desenho["credito"])
            if chave in DICAS and (opts["forcar"] or not moeda.como_identificar):
                campos["como_identificar"] = DICAS[chave]
            if campos:
                Moeda.objects.filter(pk=moeda.pk).update(**campos)  # update(): não refaz o campo de busca
            com_foto += 1
        self.stdout.write(self.style.SUCCESS(f"Fotos ligadas: {com_foto} moeda(s); sem foto: {sem_foto}."))
