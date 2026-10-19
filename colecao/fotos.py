"""Liga cada moeda do catálogo à foto do seu desenho (cara e coroa).

O desenho de uma moeda não muda de um ano para outro (só a data), então as fotos são
por desenho: família + valor, ou a própria comemorativa/olímpica. Os arquivos ficam em
static/moedas/ e o mapa (com créditos) em fotos.json — gerados por _fotos_rascunho/.
"""
import json
from pathlib import Path

from django.utils.text import slugify

from .models import Serie

# (valor em centavos, ano) -> chave do desenho nas comemorativas
COMEMORATIVAS = {
    (10, 1995): "com-fao10",
    (25, 1995): "com-fao25",
    (100, 1998): "com-dh1998",
    (100, 2002): "com-jk2002",
    (100, 2005): "com-bc2005",
    (100, 2015): "com-bc2015",
    (100, 2019): "com-25anos",
    (100, 2024): "com-30anos",
    (100, 2025): "com-60anos",
}

DICAS = {
    "f2-5A": (
        "Versão 2019A: tem a letra “A” no canto inferior esquerdo do lado do valor (coroa). "
        "Segundo a Wikimedia Commons, o “A” indica cunhagem pela Casa da Moeda holandesa (Royal Dutch Mint). "
        "A 2019 sem a letra é a versão comum."
    ),
    "f2-50A": (
        "Versão 2019A: tem a letra “A” no canto inferior esquerdo do lado do valor (coroa). "
        "Segundo a Wikimedia Commons, o “A” indica cunhagem pela Casa da Moeda holandesa (Royal Dutch Mint). "
        "A 2019 sem a letra é a versão comum."
    ),
}


def carregar_mapa():
    caminho = Path(__file__).with_name("fotos.json")
    return json.loads(caminho.read_text(encoding="utf-8"))


def chave_do_desenho(moeda):
    """Chave do desenho em fotos.json, ou None se não houver foto para esta moeda."""
    tipo = moeda.serie.tipo
    valor = moeda.denominacao.valor_centavos
    if tipo == Serie.Tipo.FAMILIA:
        familia = "f1" if moeda.serie.nome.startswith("1") else "f2"
        return f"{familia}-{valor}{moeda.variante}"
    if tipo == Serie.Tipo.COMEMORATIVA:
        return COMEMORATIVAS.get((valor, moeda.ano))
    if tipo == Serie.Tipo.OLIMPIADA:
        return "oli-" + slugify(moeda.descricao)
    return None
