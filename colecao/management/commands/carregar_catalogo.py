"""Carrega o catálogo de moedas do Plano Real (lista de controle 1994–2026).

Cria a coleção oficial "Real" (sem dono, igual para todos) se ainda não existir.
Moedas novas do Real entram aqui (get_or_create) ou pelo admin, e aparecem para todos.

Idempotente: pode rodar quantas vezes quiser; só cria o que ainda não existe
e nunca apaga nada nem mexe na sua coleção.

    python manage.py carregar_catalogo
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from colecao.models import Colecao, Denominacao, Moeda, Serie

DENOMINACOES = [
    ("1 Centavo", 1),
    ("5 Centavos", 5),
    ("10 Centavos", 10),
    ("25 Centavos", 25),
    ("50 Centavos", 50),
    ("1 Real", 100),
]


def anos(inicio, fim, *, sem=(), extras=()):
    """Lista de anos de inicio..fim (inclusive), pulando 'sem' e somando 'extras' (ex.: '2019A')."""
    lista = [str(a) for a in range(inicio, fim + 1) if a not in sem]
    lista.extend(extras)
    return lista


FAMILIAS = {
    "1ª Família": {
        1: anos(1994, 1997),
        5: anos(1994, 1997),
        10: anos(1994, 1997),
        25: anos(1994, 1995),
        50: anos(1994, 1995),
        100: anos(1994, 1994),
    },
    "2ª Família": {
        1: anos(1998, 2004),
        5: anos(1998, 2026, extras=["2019A"]),
        10: anos(1998, 2026),
        25: anos(1998, 2026),
        50: anos(1998, 2026, sem=(1999, 2004), extras=["2019A"]),
        100: anos(1998, 2026, sem=(2000, 2001)),
    },
}

# (centavos, ano, descrição)
COMEMORATIVAS = [
    (10, 1995, "FAO Alimentos para o Mundo"),
    (25, 1995, "FAO Alimentos para o Mundo"),
    (100, 1998, "50 Anos Declaração Direitos Humanos"),
    (100, 2002, "100 Anos Juscelino Kubitschek"),
    (100, 2005, "40 Anos Banco Central do Brasil"),
    (100, 2015, "50 Anos Banco Central do Brasil"),
    (100, 2019, "25 Anos do Plano Real"),
    (100, 2024, "30 Anos do Plano Real"),
    (100, 2025, "60 Anos Banco Central do Brasil"),
]

# série: (ano, [temas]) — todas são de 1 Real
OLIMPIADAS = [
    ("Olimpíadas 2012 – Entrega da Bandeira", 2012, ["Entrega da Bandeira"]),
    ("Olimpíadas 2014 – 1ª Série", 2014, ["Atletismo", "Paratriatlo", "Golf", "Natação"]),
    ("Olimpíadas 2015 – 2ª Série", 2015, ["Basquete", "Paracanoagem", "Vela", "Rugby"]),
    ("Olimpíadas 2015 – 3ª Série", 2015, ["Futebol", "Volei", "Atletismo Paralímpico", "Judo"]),
    (
        "Olimpíadas 2016 – 4ª Série",
        2016,
        ["Natação Paralímpica", "Boxe", "Mascote Olímpico", "Mascote Paralímpico"],
    ),
]


def separar_variante(rotulo: str):
    """'2019A' -> (2019, 'A'); '2008' -> (2008, '')."""
    return int(rotulo[:4]), rotulo[4:]


class Command(BaseCommand):
    help = "Cria/atualiza o catálogo de moedas do Plano Real sem mexer na coleção."

    @transaction.atomic
    def handle(self, *args, **opts):
        criadas = 0
        real, _ = Colecao.objects.get_or_create(
            slug=Colecao.SLUG_REAL, defaults={"nome": "Real", "simbolo": "R$"}
        )
        denom = {}
        for nome, valor in DENOMINACOES:
            denom[valor], _ = Denominacao.objects.get_or_create(
                colecao=real, valor_centavos=valor, defaults={"nome": nome}
            )

        ordem_serie = 0

        def serie(nome, tipo):
            nonlocal ordem_serie
            ordem_serie += 10
            obj, _ = Serie.objects.get_or_create(
                colecao=real, nome=nome, defaults={"tipo": tipo, "ordem": ordem_serie}
            )
            return obj

        def moeda(s, valor, ano, variante="", descricao="", ordem=0):
            nonlocal criadas
            _, nova = Moeda.objects.get_or_create(
                serie=s,
                denominacao=denom[valor],
                ano=ano,
                variante=variante,
                descricao=descricao,
                defaults={"ordem": ordem},
            )
            criadas += int(nova)

        for nome_familia, por_denom in FAMILIAS.items():
            s = serie(nome_familia, Serie.Tipo.CIRCULACAO)
            for valor, rotulos in por_denom.items():
                for rotulo in rotulos:
                    ano, variante = separar_variante(rotulo)
                    moeda(s, valor, ano, variante)

        s = serie("Comemorativas", Serie.Tipo.COMEMORATIVA)
        for i, (valor, ano, descricao) in enumerate(COMEMORATIVAS):
            moeda(s, valor, ano, descricao=descricao, ordem=i)

        for nome_serie, ano, temas in OLIMPIADAS:
            s = serie(nome_serie, Serie.Tipo.COMEMORATIVA)  # na seção Comemorativas, depois da série "Comemorativas"
            for i, tema in enumerate(temas):
                moeda(s, 100, ano, descricao=tema, ordem=i)

        total = Moeda.objects.filter(serie__colecao=real).count()
        self.stdout.write(
            self.style.SUCCESS(f"Catálogo pronto: {criadas} moeda(s) nova(s), {total} no total.")
        )
