"""Coleções e catálogo próprio: a pessoa cria coleções (ex.: Dólar americano), valores, séries e moedas.

Tudo aqui só mexe em coleções cujo dono é request.user; as oficiais (o Real) só pelo admin.
O usuário pode ocultar, zerar o que marcou e exportar qualquer coleção que ele vê, inclusive o Real.
"""
import re
from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Max
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from . import planilha
from .forms import ColecaoForm, DenominacaoForm, MoedaForm, SerieForm, processar_foto
from .models import Colecao, Denominacao, ItemColecao, Moeda, Serie, apagar_foto_se_orfa
from .views import CHAVE_COLECAO_ATUAL, _pct, colecao_atual, colecoes_visiveis, definir_colecao_atual

MAX_COLECOES = planilha.MAX_COLECOES
MAX_MOEDAS_POR_COLECAO = planilha.MAX_MOEDAS_POR_COLECAO
MAX_VALORES_POR_COLECAO = 50


def _minha_colecao(request, pk):
    return get_object_or_404(Colecao, pk=pk, dono=request.user)


# ---------- coleções ----------

@login_required
def colecoes(request):
    lista = list(colecoes_visiveis(request.user).annotate(total=Count("series__moedas")))
    tenho = dict(
        ItemColecao.objects.filter(user=request.user, quantidade__gt=0)
        .values_list("moeda__serie__colecao")
        .annotate(n=Count("id"))
    )
    ocultas = set(request.user.colecoes_ocultas.values_list("pk", flat=True))
    for c in lista:
        c.tenho = tenho.get(c.pk, 0)
        c.pct = _pct(c.tenho, c.total)
        c.oculta = c.pk in ocultas
    atual = colecao_atual(request)
    return render(
        request,
        "colecao/colecoes.html",
        {
            "lista": lista,
            "atual": atual,
            "pode_criar": request.user.colecoes.count() < MAX_COLECOES,
        },
    )


@login_required
def nova_colecao(request):
    if request.user.colecoes.count() >= MAX_COLECOES:
        messages.error(request, f"Limite de {MAX_COLECOES} coleções atingido.")
        return redirect("colecoes")
    form = ColecaoForm(request.POST or None, dono=request.user)
    if request.method == "POST" and form.is_valid():
        colecao = form.save(commit=False)
        colecao.dono = request.user
        colecao.ordem = (request.user.colecoes.aggregate(m=Max("ordem"))["m"] or 0) + 10  # depois das que já tem
        colecao.save()
        definir_colecao_atual(request, colecao)
        messages.success(request, "Coleção criada. Comece cadastrando os valores das moedas.")
        return redirect("valores_colecao", colecao.pk)
    return render(request, "colecao/colecao_form.html", {"form": form, "colecao": None})


@login_required
def editar_colecao(request, pk):
    colecao = _minha_colecao(request, pk)
    if request.method == "POST" and request.POST.get("acao") == "excluir":
        nome = colecao.nome
        if request.session.get(CHAVE_COLECAO_ATUAL) == colecao.pk:
            del request.session[CHAVE_COLECAO_ATUAL]
        colecao.apagar()
        messages.success(request, f"Coleção “{nome}” excluída.")
        return redirect("colecoes")
    form = ColecaoForm(request.POST or None, instance=colecao, dono=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Coleção atualizada.")
        return redirect("inicio")
    total = Moeda.objects.filter(serie__colecao=colecao).count()
    return render(request, "colecao/colecao_form.html", {"form": form, "colecao": colecao, "total": total})


@login_required
@require_POST
def ocultar_colecao(request, pk):
    """Esconde/mostra uma coleção no seletor da tela inicial (o que foi marcado não é apagado)."""
    colecao = get_object_or_404(colecoes_visiveis(request.user), pk=pk)
    if colecao.ocultada_por.filter(pk=request.user.pk).exists():
        colecao.ocultada_por.remove(request.user)
        messages.success(request, f"“{colecao.nome}” voltou para a tela inicial.")
    else:
        colecao.ocultada_por.add(request.user)
        if request.session.get(CHAVE_COLECAO_ATUAL) == colecao.pk:
            del request.session[CHAVE_COLECAO_ATUAL]
        messages.success(request, f"“{colecao.nome}” ocultada. O que você marcou continua guardado.")
    return redirect("colecoes")


@login_required
@require_POST
def zerar_colecao(request, pk):
    """Apaga só o que a pessoa marcou nesta coleção (quantidade, estado, data, observação); o catálogo fica."""
    colecao = get_object_or_404(colecoes_visiveis(request.user), pk=pk)
    apagados, _ = ItemColecao.objects.filter(user=request.user, moeda__serie__colecao=colecao).delete()
    messages.success(request, f"Marcações de “{colecao.nome}” apagadas ({apagados} moeda(s)). Ela começa do zero.")
    return redirect("colecoes")


def _planilha(request, colecoes, nome):
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{nome}-{date.today():%Y-%m-%d}.csv"'
    planilha.escrever(resp, request.user, colecoes)
    return resp


@login_required
def exportar_colecao(request, pk):
    """Planilha (CSV que abre no Excel) da coleção, com todas as moedas e o que a pessoa marcou."""
    colecao = get_object_or_404(colecoes_visiveis(request.user), pk=pk)
    return _planilha(request, [colecao], f"moedas-{slugify(colecao.nome) or 'colecao'}")


@login_required
def exportar_tudo(request):
    """Backup de todas as coleções (inclusive as ocultas), para guardar ou importar em outra conta."""
    return _planilha(request, list(colecoes_visiveis(request.user)), "moedas-backup")


@login_required
@require_POST
def importar_backup(request):
    arquivo = request.FILES.get("arquivo")
    if not arquivo:
        messages.error(request, "Escolha o arquivo do backup.")
        return redirect(reverse("colecoes") + "#backup")
    try:
        resultado = planilha.importar(request.user, planilha.ler(arquivo))
    except planilha.ErroPlanilha as erro:
        messages.error(request, str(erro))
        return redirect(reverse("colecoes") + "#backup")
    partes = [f"{resultado.marcacoes} moeda(s) com marcações restauradas"]
    if resultado.colecoes_criadas:
        partes.append(f"{resultado.colecoes_criadas} coleção(ões) criada(s)")
    if resultado.moedas_criadas:
        partes.append(f"{resultado.moedas_criadas} moeda(s) cadastrada(s)")
    messages.success(request, "Backup importado: " + ", ".join(partes) + ".")
    if resultado.ignoradas:
        messages.warning(
            request,
            f"{resultado.ignoradas} linha(s) ignorada(s) — " + "; ".join(resultado.avisos)
            + ("…" if resultado.ignoradas > len(resultado.avisos) else ""),
        )
    return redirect("colecoes")


# ---------- valores (denominações) ----------

@login_required
def valores_colecao(request, pk):
    colecao = _minha_colecao(request, pk)
    form = DenominacaoForm(colecao=colecao)
    if request.method == "POST":
        acao = request.POST.get("acao")
        if acao == "adicionar":
            if colecao.denominacoes.count() >= MAX_VALORES_POR_COLECAO:
                messages.error(request, f"Limite de {MAX_VALORES_POR_COLECAO} valores por coleção.")
                return redirect("valores_colecao", pk)
            form = DenominacaoForm(request.POST, colecao=colecao)
            if form.is_valid():
                valor = form.save(commit=False)
                valor.colecao = colecao
                valor.save()
                messages.success(request, f"Valor “{valor.nome}” adicionado.")
                return redirect("valores_colecao", pk)
        elif acao in ("salvar", "excluir"):
            valor = get_object_or_404(Denominacao, pk=request.POST.get("id"), colecao=colecao)
            if acao == "excluir":
                if valor.moedas.exists():
                    messages.error(request, f"“{valor.nome}” tem moedas cadastradas; exclua ou mude as moedas antes.")
                else:
                    valor.delete()
                    messages.success(request, "Valor excluído.")
                return redirect("valores_colecao", pk)
            edicao = DenominacaoForm(request.POST, instance=valor, colecao=colecao, prefix=f"d{valor.pk}")
            if edicao.is_valid():
                edicao.save()
                messages.success(request, "Valor atualizado.")
            else:
                messages.error(request, "Não foi possível salvar: " + " ".join(e for es in edicao.errors.values() for e in es))
            return redirect("valores_colecao", pk)
    valores = [
        (v, DenominacaoForm(instance=v, colecao=colecao, prefix=f"d{v.pk}"))
        for v in colecao.denominacoes.annotate(n=Count("moedas"))
    ]
    return render(
        request,
        "colecao/valores.html",
        {"colecao": colecao, "form": form, "valores": valores, "tem_serie": colecao.series.exists()},
    )


# ---------- séries ----------

@login_required
def nova_serie(request, pk):
    colecao = _minha_colecao(request, pk)
    proxima = (colecao.series.aggregate(m=Max("ordem"))["m"] or 0) + 10
    form = SerieForm(request.POST or None, colecao=colecao, initial={"ordem": proxima, "tipo": Serie.Tipo.CIRCULACAO})
    if request.method == "POST" and form.is_valid():
        serie = form.save(commit=False)
        serie.colecao = colecao
        serie.save()
        messages.success(request, "Série criada. Agora adicione as moedas dela.")
        return redirect("serie", serie.pk)
    return render(request, "colecao/serie_form.html", {"form": form, "colecao": colecao, "serie": None})


@login_required
def editar_serie(request, pk):
    serie = get_object_or_404(Serie.objects.select_related("colecao"), pk=pk, colecao__dono=request.user)
    if request.method == "POST" and request.POST.get("acao") == "excluir":
        with transaction.atomic():
            serie.moedas.all().delete()
            serie.delete()
        messages.success(request, f"Série “{serie.nome}” excluída.")
        return redirect("inicio")
    form = SerieForm(request.POST or None, instance=serie, colecao=serie.colecao)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Série atualizada.")
        return redirect("serie", serie.pk)
    return render(
        request,
        "colecao/serie_form.html",
        {"form": form, "colecao": serie.colecao, "serie": serie, "total": serie.moedas.count()},
    )


# ---------- moedas ----------

def _salvar_fotos(moeda, form):
    """Troca/remove as fotos enviadas; os arquivos antigos só saem se nenhuma outra moeda usar."""
    antigos = []
    for lado in ("cara", "coroa"):
        campo = getattr(moeda, f"imagem_{lado}")
        nova = form.cleaned_data.get(f"foto_{lado}")
        if (nova or form.cleaned_data.get(f"remover_{lado}")) and campo:
            antigos.append((campo.name, campo.storage))
            setattr(moeda, f"imagem_{lado}", "")
        if nova:
            getattr(moeda, f"imagem_{lado}").save("foto.webp", processar_foto(nova), save=False)
    moeda.save()
    for nome, storage in antigos:
        apagar_foto_se_orfa(nome, storage)


@login_required
def nova_moeda(request, pk):
    serie = get_object_or_404(Serie.objects.select_related("colecao"), pk=pk, colecao__dono=request.user)
    colecao = serie.colecao
    if not colecao.denominacoes.exists():
        messages.info(request, "Cadastre primeiro os valores das moedas (ex.: 1 Cent, 25 Cents).")
        return redirect("valores_colecao", colecao.pk)
    initial = {"serie": serie}
    if request.GET.get("valor", "").isdigit():
        initial["denominacao"] = request.GET["valor"]
    form = MoedaForm(request.POST or None, request.FILES or None, colecao=colecao, initial=initial)
    if request.method == "POST" and form.is_valid():
        anos = form.anos()
        ja_tem = Moeda.objects.filter(serie__colecao=colecao).count()
        if ja_tem + len(anos) > MAX_MOEDAS_POR_COLECAO:
            form.add_error(None, f"Limite de {MAX_MOEDAS_POR_COLECAO} moedas por coleção.")
        else:
            criadas, repetidas = _criar_moedas(form, anos)
            if criadas:
                txt = f"{criadas} moeda(s) cadastrada(s)."
                if repetidas:
                    txt += f" {repetidas} já existia(m) e ficou(aram) como estava(m)."
                messages.success(request, txt)
            else:
                messages.error(request, "Essa moeda já estava cadastrada.")
            destino = form.cleaned_data["serie"]
            if request.POST.get("continuar"):
                url = reverse("nova_moeda", args=[destino.pk])
                return redirect(f"{url}?valor={form.cleaned_data['denominacao'].pk}")
            return redirect("serie", destino.pk)
    return render(request, "colecao/moeda_form.html", {"form": form, "colecao": colecao, "serie": serie, "moeda": None})


@transaction.atomic
def _criar_moedas(form, anos):
    """Uma moeda por ano da faixa; as fotos (iguais para a faixa) são processadas uma vez só."""
    dados = form.cleaned_data
    campos = {k: dados[k] for k in ("variante", "descricao", "cor_metal", "como_identificar")}
    criadas = repetidas = 0
    primeira = None
    for ano in anos:
        moeda, nova = Moeda.objects.get_or_create(
            serie=dados["serie"], denominacao=dados["denominacao"], ano=ano,
            variante=campos["variante"], descricao=campos["descricao"], defaults=campos,
        )
        if not nova:
            repetidas += 1
            continue
        criadas += 1
        if primeira is None:
            primeira = moeda
            _salvar_fotos(moeda, form)
        elif primeira.imagem_cara or primeira.imagem_coroa:
            moeda.imagem_cara, moeda.imagem_coroa = primeira.imagem_cara.name, primeira.imagem_coroa.name
            moeda.save()
    return criadas, repetidas


@login_required
def editar_moeda(request, pk):
    moeda = get_object_or_404(
        Moeda.objects.select_related("serie__colecao", "denominacao"), pk=pk, serie__colecao__dono=request.user
    )
    colecao = moeda.serie.colecao
    if request.method == "POST" and request.POST.get("acao") == "excluir":
        serie_id = moeda.serie_id
        moeda.delete()
        messages.success(request, "Moeda excluída do catálogo.")
        return redirect("serie", serie_id)
    form = MoedaForm(request.POST or None, request.FILES or None, instance=moeda, colecao=colecao)
    if request.method == "POST" and form.is_valid():
        moeda = form.save(commit=False)
        _salvar_fotos(moeda, form)
        messages.success(request, "Moeda atualizada.")
        return redirect("serie", moeda.serie_id)
    return render(
        request,
        "colecao/moeda_form.html",
        {"form": form, "colecao": colecao, "serie": moeda.serie, "moeda": moeda},
    )


# ---------- fotos enviadas ----------

NOME_FOTO = re.compile(r"[0-9a-f]{32}\.webp")


@login_required
def foto(request, dono_id, nome):
    """Serve as fotos enviadas só para o dono da coleção (e para a equipe, no admin)."""
    if not NOME_FOTO.fullmatch(nome) or (dono_id != request.user.pk and not request.user.is_staff):
        raise Http404
    caminho = Path(settings.MEDIA_ROOT) / "fotos" / str(dono_id) / nome
    if not caminho.is_file():
        raise Http404
    resp = FileResponse(open(caminho, "rb"), content_type="image/webp")
    resp["Cache-Control"] = "private, max-age=31536000, immutable"
    return resp
