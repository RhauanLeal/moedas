"""Backup da coleção em planilha CSV (abre no Excel): exportar e importar.

Uma linha por moeda, com a coleção, o catálogo (para recriar as coleções próprias numa conta
nova) e o que a pessoa marcou. Serve para trocar de e-mail: baixa na conta antiga e importa na
nova. No Real (oficial) nada do catálogo é criado: só as marcações voltam. As fotos enviadas
não vão na planilha.
"""
import csv
import io
from dataclasses import dataclass, field
from datetime import datetime

from django.db import transaction
from django.db.models import Max

from .models import Colecao, Denominacao, ItemColecao, Moeda, Serie, normalizar

COLUNAS = [
    "Coleção", "Símbolo", "Série", "Tipo da série", "Valor", "Valor em centavos", "Ano", "Variante",
    "Descrição", "Cor do metal", "Como identificar", "Quantidade", "Estado", "Data em que achei", "Observação",
]
TAMANHO_MAX = 5 * 1024 * 1024
LINHAS_MAX = 20000
MAX_COLECOES = 20
MAX_MOEDAS_POR_COLECAO = 2000


# ---------- exportar ----------

def _celula(valor):
    """Evita que o Excel trate um texto como fórmula (ex.: observação começando com "=")."""
    texto = str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@") else texto


def escrever(saida, user, colecoes):
    """Escreve a planilha (com BOM, para o Excel abrir os acentos certo) das coleções dadas."""
    saida.write("﻿")
    planilha = csv.writer(saida, delimiter=";")
    planilha.writerow(COLUNAS)
    for colecao in colecoes:
        itens = {i.moeda_id: i for i in ItemColecao.objects.filter(user=user, moeda__serie__colecao=colecao)}
        for m in Moeda.objects.filter(serie__colecao=colecao).select_related("serie", "denominacao"):
            item = itens.get(m.pk)
            planilha.writerow([_celula(v) for v in (
                colecao.nome, colecao.simbolo, m.serie.nome, m.serie.get_tipo_display(),
                m.denominacao.nome, m.denominacao.valor_centavos, m.ano, m.variante, m.descricao,
                m.get_cor_metal_display() if m.cor_metal else "", m.como_identificar,
                item.quantidade if item else 0,
                item.estado if item else "",
                item.adquirida_em.strftime("%d/%m/%Y") if item and item.adquirida_em else "",
                item.observacao if item else "",
            )])


# ---------- importar ----------

class ErroPlanilha(Exception):
    """O arquivo inteiro não serve (formato, tamanho, colunas)."""


class ErroLinha(Exception):
    """Uma linha não pôde ser importada; as outras continuam."""


@dataclass
class Resultado:
    colecoes_criadas: int = 0
    moedas_criadas: int = 0
    marcacoes: int = 0
    ignoradas: int = 0
    avisos: list = field(default_factory=list)


def _chave(texto):
    return normalizar(texto).strip()


CABECALHOS = {_chave(c): c for c in COLUNAS}
TIPOS = {**{_chave(t.label): t.value for t in Serie.Tipo}, **{_chave(t.value): t.value for t in Serie.Tipo}}
METAIS = {**{_chave(m.label): m.value for m in Moeda.Metal}, **{_chave(m.value): m.value for m in Moeda.Metal}}
ESTADOS = {_chave(e.value): e.value for e in ItemColecao.Estado}


def ler(arquivo):
    """Lê o CSV enviado e devolve as linhas como dicionários com os nomes de COLUNAS."""
    if arquivo.size > TAMANHO_MAX:
        raise ErroPlanilha("O arquivo passa de 5 MB.")
    bruto = arquivo.read()
    for codificacao in ("utf-8-sig", "cp1252"):  # cp1252: CSV salvo de novo pelo Excel no Windows
        try:
            texto = bruto.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ErroPlanilha("Não consegui ler o arquivo. Envie a planilha baixada em “Baixar backup”.")
    primeira = texto.split("\n", 1)[0]
    separador = max((";", ",", "\t"), key=primeira.count)
    leitor = csv.reader(io.StringIO(texto), delimiter=separador)
    try:
        cabecalho = [CABECALHOS.get(_chave(c)) for c in next(leitor)]
    except StopIteration:
        raise ErroPlanilha("O arquivo está vazio.")
    faltando = [c for c in ("Coleção", "Série", "Valor", "Ano") if c not in cabecalho]
    if faltando:
        raise ErroPlanilha("A planilha não tem as colunas: " + ", ".join(faltando) + ". Use o arquivo de “Baixar backup”.")
    linhas = []
    for valores in leitor:
        if not any(v.strip() for v in valores):
            continue
        linhas.append({c: v.strip() for c, v in zip(cabecalho, valores) if c})
        if len(linhas) > LINHAS_MAX:
            raise ErroPlanilha(f"A planilha passa de {LINHAS_MAX} linhas.")
    return linhas


def _texto(linha, coluna):
    valor = linha.get(coluna, "")
    return valor[1:] if valor.startswith("'") else valor  # tira a proteção de fórmula do exportar


def _inteiro(linha, coluna, padrao=None):
    valor = _texto(linha, coluna)
    if valor.endswith(".0"):  # número que o Excel salvou como decimal
        valor = valor[:-2]
    if not valor:
        if padrao is None:
            raise ErroLinha(f"falta {coluna.lower()}")
        return padrao
    try:
        return int(valor)
    except ValueError:
        raise ErroLinha(f"{coluna.lower()} inválido: “{valor}”")


def _data(texto):
    if not texto:
        return None
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ErroLinha(f"data inválida: “{texto}” (use dia/mês/ano)")


class _Importador:
    def __init__(self, user):
        self.user = user
        self.resultado = Resultado()
        self.esquecer()

    def esquecer(self):
        """Recarrega do banco o que fica em memória (depois de uma linha desfeita)."""
        self.colecoes = {_chave(c.nome): c for c in Colecao.objects.visiveis_para(self.user)}
        self.series, self.valores, self.total_moedas = {}, {}, {}

    def colecao(self, linha):
        nome = _texto(linha, "Coleção")
        if not nome:
            raise ErroLinha("falta o nome da coleção")
        colecao = self.colecoes.get(_chave(nome))
        if colecao is None:
            if self.user.colecoes.count() >= MAX_COLECOES:
                raise ErroLinha(f"limite de {MAX_COLECOES} coleções atingido")
            ordem = (self.user.colecoes.aggregate(m=Max("ordem"))["m"] or 0) + 10
            colecao = Colecao.objects.create(
                dono=self.user, nome=nome[:60], simbolo=_texto(linha, "Símbolo")[:8], ordem=ordem
            )
            self.colecoes[_chave(nome)] = colecao
            self.resultado.colecoes_criadas += 1
        return colecao

    def serie(self, colecao, linha, editavel):
        nome = _texto(linha, "Série")
        if not nome:
            raise ErroLinha("falta a série")
        cache = self.series.setdefault(colecao.pk, {_chave(s.nome): s for s in colecao.series.all()})
        serie = cache.get(_chave(nome))
        if serie is None:
            if not editavel:
                raise ErroLinha(f"a série “{nome}” não existe em {colecao.nome}")
            ordem = (colecao.series.aggregate(m=Max("ordem"))["m"] or 0) + 10
            tipo = TIPOS.get(_chave(_texto(linha, "Tipo da série")), Serie.Tipo.CIRCULACAO)
            serie = cache[_chave(nome)] = Serie.objects.create(colecao=colecao, nome=nome[:120], tipo=tipo, ordem=ordem)
        return serie

    def valor(self, colecao, linha, editavel):
        nome = _texto(linha, "Valor")
        centavos = _inteiro(linha, "Valor em centavos", padrao=0)
        cache = self.valores.setdefault(colecao.pk, list(colecao.denominacoes.all()))
        for d in cache:
            if (centavos and d.valor_centavos == centavos) or (nome and _chave(d.nome) == _chave(nome)):
                return d
        if not editavel:
            raise ErroLinha(f"o valor “{nome}” não existe em {colecao.nome}")
        if not nome or centavos <= 0:
            raise ErroLinha("para criar o valor, preencha o nome e o valor em centavos")
        valor = Denominacao.objects.create(colecao=colecao, nome=nome[:40], valor_centavos=centavos)
        cache.append(valor)
        return valor

    def moeda(self, colecao, serie, valor, linha, editavel):
        ano = _inteiro(linha, "Ano")
        if not 1500 <= ano <= 2100:
            raise ErroLinha(f"ano fora do intervalo: {ano}")
        campos = dict(
            serie=serie, denominacao=valor, ano=ano,
            variante=_texto(linha, "Variante").upper()[:10], descricao=_texto(linha, "Descrição")[:150],
        )
        moeda = Moeda.objects.filter(**campos).first()
        if moeda is None:
            if not editavel:
                raise ErroLinha(f"a moeda {valor.nome} {ano} não existe em {colecao.nome}")
            if colecao.pk not in self.total_moedas:
                self.total_moedas[colecao.pk] = Moeda.objects.filter(serie__colecao=colecao).count()
            if self.total_moedas[colecao.pk] >= MAX_MOEDAS_POR_COLECAO:
                raise ErroLinha(f"limite de {MAX_MOEDAS_POR_COLECAO} moedas por coleção")
            moeda = Moeda.objects.create(
                **campos,
                cor_metal=METAIS.get(_chave(_texto(linha, "Cor do metal")), ""),
                como_identificar=_texto(linha, "Como identificar"),
            )
            self.total_moedas[colecao.pk] += 1
            self.resultado.moedas_criadas += 1
        return moeda

    def marcacao(self, moeda, linha):
        quantidade = _inteiro(linha, "Quantidade", padrao=0)
        if quantidade < 0:
            raise ErroLinha("quantidade negativa")
        estado_texto = _texto(linha, "Estado")
        estado = ESTADOS.get(_chave(estado_texto.split()[0])) if estado_texto else ""
        if estado is None:
            raise ErroLinha(f"estado inválido: “{estado_texto}” (use UTGC, BC, MBC, SOB ou FC)")
        dados = dict(
            quantidade=quantidade, estado=estado,
            adquirida_em=_data(_texto(linha, "Data em que achei")), observacao=_texto(linha, "Observação"),
        )
        existe = ItemColecao.objects.filter(user=self.user, moeda=moeda).exists()
        if not existe and not (quantidade or estado or dados["adquirida_em"] or dados["observacao"]):
            return  # nada marcado nesta moeda
        ItemColecao.objects.update_or_create(user=self.user, moeda=moeda, defaults=dados)
        self.resultado.marcacoes += 1

    def linha(self, linha):
        colecao = self.colecao(linha)
        editavel = colecao.dono_id == self.user.pk
        serie = self.serie(colecao, linha, editavel)
        valor = self.valor(colecao, linha, editavel)
        moeda = self.moeda(colecao, serie, valor, linha, editavel)
        self.marcacao(moeda, linha)


@transaction.atomic
def importar(user, linhas):
    """Cria o que faltar das coleções próprias e deixa as moedas da planilha marcadas como nela."""
    importador = _Importador(user)
    r = importador.resultado
    for numero, linha in enumerate(linhas, start=2):  # linha 1 é o cabeçalho
        antes = (r.colecoes_criadas, r.moedas_criadas, r.marcacoes)
        try:
            with transaction.atomic():  # a linha com erro é desfeita inteira; as outras continuam
                importador.linha(linha)
        except ErroLinha as erro:
            r.colecoes_criadas, r.moedas_criadas, r.marcacoes = antes
            importador.esquecer()
            r.ignoradas += 1
            if len(r.avisos) < 5:
                r.avisos.append(f"linha {numero}: {erro}")
    return r
