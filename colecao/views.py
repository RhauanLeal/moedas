import re
from urllib.parse import parse_qs, urlparse

from django import forms
from django.contrib.auth.decorators import login_required
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Colecao, ItemColecao, Moeda, Serie, normalizar

CHAVE_COLECAO_ATUAL = "colecao_atual"


# ---------- coleções (o que cada usuário pode ver) ----------

def colecoes_visiveis(user):
    """Oficiais + as do próprio usuário. Toda busca de série/moeda por pk passa por aqui."""
    return Colecao.objects.visiveis_para(user)


def moedas_visiveis(user):
    return Moeda.objects.filter(serie__colecao__in=colecoes_visiveis(user))


def series_visiveis(user):
    return Serie.objects.filter(colecao__in=colecoes_visiveis(user))


def colecao_atual(request):
    """Coleção que a pessoa está vendo (guardada na sessão; padrão: a primeira ativa, o Real).

    None quando todas estão ocultas (ou não há nenhuma): as telas mandam para "Coleções".
    """
    pk = request.session.get(CHAVE_COLECAO_ATUAL)
    if pk:
        # aberta de propósito vale mesmo se estiver oculta
        colecao = colecoes_visiveis(request.user).filter(pk=pk).first()
        if colecao:
            return colecao
    return Colecao.objects.ativas_para(request.user).first()


def definir_colecao_atual(request, colecao):
    request.session[CHAVE_COLECAO_ATUAL] = colecao.pk


# ---------- consultas ----------

def moedas_com_colecao(user, qs=None):
    """Moedas do catálogo anotadas com a quantidade/estado da coleção DESTE usuário."""
    qs = qs if qs is not None else moedas_visiveis(user)
    meus = ItemColecao.objects.filter(user=user, moeda=OuterRef("pk"))
    return qs.select_related("serie__colecao", "denominacao").annotate(
        qtd=Coalesce(Subquery(meus.values("quantidade")[:1]), Value(0)),
        estado=Subquery(meus.values("estado")[:1]),
    )


def _pct(tenho, total):
    return round(100 * tenho / total) if total else 0


def progresso(user, colecao=None, serie=None):
    """Totais de uma série ou, sem série, da coleção inteira."""
    itens = ItemColecao.objects.filter(user=user, quantidade__gt=0)
    if serie is not None:
        moedas = Moeda.objects.filter(serie=serie)
        itens = itens.filter(moeda__serie=serie)
    else:
        moedas = Moeda.objects.filter(serie__colecao=colecao)
        itens = itens.filter(moeda__serie__colecao=colecao)
    total, tenho = moedas.count(), itens.count()
    return {
        "total": total,
        "tenho": tenho,
        "pct": _pct(tenho, total),
        "faltam": total - tenho,
        "pct_faltam": _pct(total - tenho, total),
    }


def series_com_progresso(user, colecao):
    tenho_por_serie = dict(
        ItemColecao.objects.filter(user=user, quantidade__gt=0, moeda__serie__colecao=colecao)
        .values_list("moeda__serie")
        .annotate(n=Count("id"))
    )
    series = list(
        Serie.objects.filter(colecao=colecao).annotate(total=Count("moedas")).order_by("ordem", "nome")
    )
    for s in series:
        s.tenho = tenho_por_serie.get(s.pk, 0)
        s.pct = _pct(s.tenho, s.total)
    return series


def agrupar_por_denominacao(moedas):
    """[(denominacao, [moedas...]), ...] preservando a ordem."""
    grupos = []
    for m in moedas:
        if not grupos or grupos[-1][0].pk != m.denominacao_id:
            grupos.append((m.denominacao, []))
        grupos[-1][1].append(m)
    return grupos


def agrupar_por_serie(moedas):
    grupos = []
    for m in moedas:
        if not grupos or grupos[-1]["serie"].pk != m.serie_id:
            grupos.append({"serie": m.serie, "moedas": []})
        grupos[-1]["moedas"].append(m)
    for g in grupos:
        g["por_denominacao"] = agrupar_por_denominacao(g["moedas"])
    return grupos


# ---------- busca ----------

VALORES_VALIDOS = {1, 5, 10, 25, 50, 100}
PALAVRAS_REAL = {"real", "reais", "r$"}
PALAVRAS_CENTAVO = {"centavo", "centavos", "cent", "cents", "ct", "cts", "c"}


def interpretar_busca(q, valores_validos=VALORES_VALIDOS):
    """Transforma '50 2008', '1 real 2019', '5c 2019a' ou 'natacao' em filtros.

    valores_validos: valores (em centavos) das denominações da coleção onde se busca.
    """
    tokens = normalizar(q).replace(",", " ").replace("$", "$ ").split()
    tem_real = any(t in PALAVRAS_REAL for t in tokens)
    tem_centavo = any(t in PALAVRAS_CENTAVO for t in tokens)
    anos, variantes, valores, textos = set(), set(), set(), []

    for t in tokens:
        if t in PALAVRAS_REAL or t in PALAVRAS_CENTAVO:
            continue
        m = re.fullmatch(r"(1[6-9]\d{2}|20\d{2})([a-z]?)", t)
        if m:
            anos.add(int(m.group(1)))
            if m.group(2):
                variantes.add(m.group(2).upper())
            continue
        m = re.fullmatch(r"(\d{1,4})(c|ct|cts|cent|centavos?)?", t)
        if m and int(m.group(1)) in valores_validos:
            n = int(m.group(1))
            if n == 1 and not m.group(2):
                if tem_real and not tem_centavo:
                    valores.add(100)
                elif tem_centavo and not tem_real:
                    valores.add(1)
                else:
                    valores.update({1, 100} & set(valores_validos))
            else:
                valores.add(n)
            continue
        if len(t) >= 2:
            textos.append(t)

    if tem_real and not valores and 100 in valores_validos:
        valores.add(100)
    return {"anos": anos, "variantes": variantes, "valores": valores, "textos": textos}


def buscar_moedas(user, q, colecao):
    validos = set(colecao.denominacoes.values_list("valor_centavos", flat=True))
    f = interpretar_busca(q, validos)
    if not any(f.values()):
        return None
    qs = Moeda.objects.filter(serie__colecao=colecao)
    if f["anos"]:
        qs = qs.filter(ano__in=f["anos"])
    if f["variantes"]:
        qs = qs.filter(variante__in=f["variantes"])
    if f["valores"]:
        qs = qs.filter(denominacao__valor_centavos__in=f["valores"])
    for t in f["textos"]:
        qs = qs.filter(busca__contains=t)
    return moedas_com_colecao(user, qs)[:200]


# ---------- páginas ----------

@login_required
def inicio(request):
    colecao = colecao_atual(request)
    if colecao is None:
        return redirect("colecoes")
    series = series_com_progresso(request.user, colecao)
    return render(
        request,
        "colecao/inicio.html",
        {
            "colecao": colecao,
            "colecoes": Colecao.objects.ativas_para(request.user),
            "pode_editar": colecao.dono_id == request.user.pk,
            "progresso": progresso(request.user, colecao),
            "secoes": [
                (rotulo, [s for s in series if s.tipo == tipo])
                for tipo, rotulo in Serie.Tipo.choices
                if any(s.tipo == tipo for s in series)
            ],
        },
    )


@login_required
def abrir_colecao(request, pk):
    definir_colecao_atual(request, get_object_or_404(colecoes_visiveis(request.user), pk=pk))
    return redirect("inicio")


@login_required
def serie_detalhe(request, pk):
    serie = get_object_or_404(series_visiveis(request.user).select_related("colecao"), pk=pk)
    definir_colecao_atual(request, serie.colecao)  # "‹ Início" volta para a coleção desta série
    faltando = request.GET.get("faltando") == "1"
    moedas = moedas_com_colecao(request.user, serie.moedas.all())
    if faltando:
        moedas = moedas.filter(qtd=0)
    return render(
        request,
        "colecao/serie.html",
        {
            "serie": serie,
            "faltando": faltando,
            "pode_editar": serie.colecao.dono_id == request.user.pk,
            "grupos": agrupar_por_denominacao(list(moedas)),
            "progresso_serie": progresso(request.user, serie=serie),
        },
    )


@login_required
def faltando(request):
    colecao = colecao_atual(request)
    if colecao is None:
        return redirect("colecoes")
    moedas = moedas_com_colecao(request.user, Moeda.objects.filter(serie__colecao=colecao)).filter(qtd=0)
    return render(
        request,
        "colecao/faltando.html",
        {
            "colecao": colecao,
            "grupos": agrupar_por_serie(list(moedas)),
            "progresso": progresso(request.user, colecao),
        },
    )


@login_required
def buscar(request):
    colecao = colecao_atual(request)
    q = request.GET.get("q", "").strip()[:100]
    moedas = buscar_moedas(request.user, q, colecao) if q and colecao else None
    return render(
        request,
        "colecao/_resultados.html",
        {
            "q": q,
            "colecao": colecao,
            "pode_editar": colecao is not None and colecao.dono_id == request.user.pk,
            "grupos": agrupar_por_serie(list(moedas)) if moedas is not None else None,
        },
    )


# ---------- compartilhar ----------

def texto_compartilhar(user, tipo, colecao, serie=None):
    """Mensagem pronta para WhatsApp: moedas que faltam ou repetidas para troca, por série."""
    moedas = moedas_com_colecao(user, Moeda.objects.filter(serie__colecao=colecao))
    if serie is not None:
        moedas = moedas.filter(serie=serie)
    repetidas = tipo == "repetidas"
    moedas = list(moedas.filter(qtd__gte=2) if repetidas else moedas.filter(qtd=0))
    if not moedas:
        return ""

    def rotulo(m):
        txt = m.ano_rotulo + (f" ({m.descricao})" if m.descricao else "")
        return f"{txt} +{m.qtd - 1}" if repetidas else txt

    onde = f" da série {serie.nome}" if serie else ""
    if repetidas:
        linhas = [f"🪙 {colecao.titulo} repetidas{onde} (tenho para troca):"]
    else:
        todas = Moeda.objects.filter(serie=serie) if serie else Moeda.objects.filter(serie__colecao=colecao)
        linhas = [f"🪙 {colecao.titulo} que me faltam{onde} ({len(moedas)} de {todas.count()}):"]

    for g in agrupar_por_serie(moedas):
        linhas += ["", f"*{g['serie'].nome}*"]
        for denom, ms in g["por_denominacao"]:
            linhas.append(f"• {denom.nome}: " + ", ".join(rotulo(m) for m in ms))
    linhas += ["", "Alguma dessas te interessa? 🙂" if repetidas else "Você tem alguma para trocar? 🙂"]
    return "\n".join(linhas)


@login_required
def compartilhar(request):
    tipo = "repetidas" if request.GET.get("tipo") == "repetidas" else "faltam"
    serie = None
    if request.GET.get("serie", "").isdigit():
        serie = get_object_or_404(series_visiveis(request.user), pk=int(request.GET["serie"]))
        definir_colecao_atual(request, serie.colecao)
    colecao = colecao_atual(request)
    if colecao is None:
        return redirect("colecoes")
    return render(
        request,
        "colecao/compartilhar.html",
        {
            "tipo": tipo,
            "serie": serie,
            "colecao": colecao,
            "texto": texto_compartilhar(request.user, tipo, colecao, serie),
            "series": colecao.series.all(),
        },
    )


# ---------- ações (HTMX) ----------

def resposta_moeda(request, moeda_id, extra_headers=None):
    """Devolve o chip atualizado + contadores de progresso (out-of-band)."""
    moeda = moedas_com_colecao(request.user).get(pk=moeda_id)
    html = render_to_string("colecao/_chip.html", {"m": moeda, "oob": True}, request=request)
    # Atualiza só o contador que existe na tela atual (série ou total).
    url_atual = urlparse(request.headers.get("HX-Current-URL", ""))
    na_serie = url_atual.path.startswith("/serie/")
    html += render_to_string(
        "colecao/_barra.html",
        {
            "dados": progresso(request.user, serie=moeda.serie)
            if na_serie
            else progresso(request.user, moeda.serie.colecao),
            "serie": moeda.serie if na_serie else None,
            # Em "O que falta" e no filtro "Só as que faltam" a barra mostra quantas faltam.
            "faltam": url_atual.path == reverse("faltando")
            or (na_serie and parse_qs(url_atual.query).get("faltando") == ["1"]),
            "oob": True,
        },
        request=request,
    )
    resp = HttpResponse(html)
    for k, v in (extra_headers or {}).items():
        resp[k] = v
    return resp


@login_required
@require_POST
def marcar(request, pk):
    """Um toque numa moeda que não tenho: marca 1 unidade."""
    moeda = get_object_or_404(moedas_visiveis(request.user), pk=pk)
    item, _ = ItemColecao.objects.get_or_create(user=request.user, moeda=moeda)
    if item.quantidade == 0:
        item.quantidade = 1
        item.save()
    return resposta_moeda(request, pk)


class ItemForm(forms.ModelForm):
    class Meta:
        model = ItemColecao
        fields = ["quantidade", "estado", "adquirida_em", "observacao"]
        widgets = {
            "quantidade": forms.NumberInput(attrs={"min": 0, "inputmode": "numeric"}),
            "adquirida_em": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "observacao": forms.Textarea(attrs={"rows": 2, "placeholder": "Ex.: achei no troco da padaria"}),
        }
        labels = {
            "quantidade": "Quantidade",
            "estado": "Estado de conservação",
            "adquirida_em": "Data em que achei",
            "observacao": "Observação",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["estado"].choices = [("", "Não informado")] + list(ItemColecao.Estado.choices)


@login_required
def ficha(request, pk):
    """Ficha da moeda (abre num painel por baixo da tela)."""
    moeda = get_object_or_404(moedas_visiveis(request.user).select_related("serie__colecao", "denominacao"), pk=pk)
    item, _ = ItemColecao.objects.get_or_create(user=request.user, moeda=moeda)

    if request.method == "POST":
        if request.POST.get("acao") == "remover":
            item.quantidade = 0
            item.save()
            return resposta_moeda(request, pk, {"HX-Trigger": "fechar-ficha"})
        form = ItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            return resposta_moeda(request, pk, {"HX-Trigger": "fechar-ficha"})
        # inválido: devolve a ficha com os erros (status 200 para o htmx trocar o conteúdo)
    else:
        form = ItemForm(instance=item)

    return render(
        request,
        "colecao/_ficha.html",
        {
            "moeda": moeda,
            "item": item,
            "form": form,
            "pode_editar": moeda.serie.colecao.dono_id == request.user.pk,
        },
    )
