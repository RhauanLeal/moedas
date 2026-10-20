import re
from urllib.parse import urlparse

from django import forms
from django.contrib.auth.decorators import login_required
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from .models import ItemColecao, Moeda, Serie, normalizar


# ---------- consultas ----------

def moedas_com_colecao(user, qs=None):
    """Moedas do catálogo anotadas com a quantidade/estado da coleção DESTE usuário."""
    qs = qs if qs is not None else Moeda.objects.all()
    meus = ItemColecao.objects.filter(user=user, moeda=OuterRef("pk"))
    return qs.select_related("serie", "denominacao").annotate(
        qtd=Coalesce(Subquery(meus.values("quantidade")[:1]), Value(0)),
        estado=Subquery(meus.values("estado")[:1]),
    )


def _pct(tenho, total):
    return round(100 * tenho / total) if total else 0


def progresso(user, serie=None):
    moedas = Moeda.objects.all()
    itens = ItemColecao.objects.filter(user=user, quantidade__gt=0)
    if serie is not None:
        moedas = moedas.filter(serie=serie)
        itens = itens.filter(moeda__serie=serie)
    total, tenho = moedas.count(), itens.count()
    return {"total": total, "tenho": tenho, "pct": _pct(tenho, total)}


def series_com_progresso(user):
    tenho_por_serie = dict(
        ItemColecao.objects.filter(user=user, quantidade__gt=0)
        .values_list("moeda__serie")
        .annotate(n=Count("id"))
    )
    series = list(Serie.objects.annotate(total=Count("moedas")).order_by("ordem", "nome"))
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


def interpretar_busca(q):
    """Transforma '50 2008', '1 real 2019', '5c 2019a' ou 'natacao' em filtros."""
    tokens = normalizar(q).replace(",", " ").replace("$", "$ ").split()
    tem_real = any(t in PALAVRAS_REAL for t in tokens)
    tem_centavo = any(t in PALAVRAS_CENTAVO for t in tokens)
    anos, variantes, valores, textos = set(), set(), set(), []

    for t in tokens:
        if t in PALAVRAS_REAL or t in PALAVRAS_CENTAVO:
            continue
        m = re.fullmatch(r"(19\d{2}|20\d{2})([a-z]?)", t)
        if m:
            anos.add(int(m.group(1)))
            if m.group(2):
                variantes.add(m.group(2).upper())
            continue
        m = re.fullmatch(r"(\d{1,3})(c|ct|cts|cent|centavos?)?", t)
        if m and int(m.group(1)) in VALORES_VALIDOS:
            n = int(m.group(1))
            if n == 1 and not m.group(2):
                if tem_real and not tem_centavo:
                    valores.add(100)
                elif tem_centavo and not tem_real:
                    valores.add(1)
                else:
                    valores.update({1, 100})
            else:
                valores.add(n)
            continue
        if len(t) >= 2:
            textos.append(t)

    if tem_real and not valores:
        valores.add(100)
    return {"anos": anos, "variantes": variantes, "valores": valores, "textos": textos}


def buscar_moedas(user, q):
    f = interpretar_busca(q)
    if not any(f.values()):
        return None
    qs = Moeda.objects.all()
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
    series = series_com_progresso(request.user)
    return render(
        request,
        "colecao/inicio.html",
        {
            "progresso": progresso(request.user),
            "secoes": [
                (rotulo, [s for s in series if s.tipo == tipo])
                for tipo, rotulo in Serie.Tipo.choices
                if any(s.tipo == tipo for s in series)
            ],
        },
    )


@login_required
def serie_detalhe(request, pk):
    serie = get_object_or_404(Serie, pk=pk)
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
            "grupos": agrupar_por_denominacao(list(moedas)),
            "progresso_serie": progresso(request.user, serie),
        },
    )


@login_required
def faltando(request):
    moedas = moedas_com_colecao(request.user).filter(qtd=0)
    return render(
        request,
        "colecao/faltando.html",
        {"grupos": agrupar_por_serie(list(moedas)), "progresso": progresso(request.user)},
    )


@login_required
def buscar(request):
    q = request.GET.get("q", "").strip()[:100]
    moedas = buscar_moedas(request.user, q) if q else None
    return render(
        request,
        "colecao/_resultados.html",
        {"q": q, "grupos": agrupar_por_serie(list(moedas)) if moedas is not None else None},
    )


# ---------- compartilhar ----------

def texto_compartilhar(user, tipo, serie=None):
    """Mensagem pronta para WhatsApp: moedas que faltam ou repetidas para troca, por série."""
    moedas = moedas_com_colecao(user)
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
        linhas = [f"🪙 Moedas do Real repetidas{onde} (tenho para troca):"]
    else:
        total = Moeda.objects.filter(serie=serie).count() if serie else Moeda.objects.count()
        linhas = [f"🪙 Moedas do Real que me faltam{onde} ({len(moedas)} de {total}):"]

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
        serie = get_object_or_404(Serie, pk=int(request.GET["serie"]))
    return render(
        request,
        "colecao/compartilhar.html",
        {
            "tipo": tipo,
            "serie": serie,
            "texto": texto_compartilhar(request.user, tipo, serie),
            "series": Serie.objects.all(),
        },
    )


# ---------- ações (HTMX) ----------

def resposta_moeda(request, moeda_id, extra_headers=None):
    """Devolve o chip atualizado + contadores de progresso (out-of-band)."""
    moeda = moedas_com_colecao(request.user).get(pk=moeda_id)
    html = render_to_string("colecao/_chip.html", {"m": moeda, "oob": True}, request=request)
    # Atualiza só o contador que existe na tela atual (série ou total).
    na_serie = urlparse(request.headers.get("HX-Current-URL", "")).path.startswith("/serie/")
    html += render_to_string(
        "colecao/_barra.html",
        {
            "dados": progresso(request.user, moeda.serie) if na_serie else progresso(request.user),
            "serie": moeda.serie if na_serie else None,
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
    moeda = get_object_or_404(Moeda, pk=pk)
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
    moeda = get_object_or_404(Moeda.objects.select_related("serie", "denominacao"), pk=pk)
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

    return render(request, "colecao/_ficha.html", {"moeda": moeda, "item": item, "form": form})
