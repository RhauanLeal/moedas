"""Formulários do catálogo próprio: coleções criadas pelo usuário, valores, séries e moedas."""
from io import BytesIO

from django import forms
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

from .models import Colecao, Denominacao, Moeda, Serie

TAMANHO_MAX_FOTO = 10 * 1024 * 1024  # 10 MB (foto do celular); depois de reduzida fica com ~50 KB
LADO_MAX_FOTO = 800
MAX_FAIXA_ANOS = 300


def processar_foto(arquivo):
    """Gira conforme o EXIF do celular, reduz para no máximo 800 px e converte para WebP."""
    arquivo.seek(0)
    img = ImageOps.exif_transpose(Image.open(arquivo))
    img.thumbnail((LADO_MAX_FOTO, LADO_MAX_FOTO))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if img.mode in ("LA", "PA", "P") else "RGB")
    buf = BytesIO()
    img.save(buf, "WEBP", quality=80)
    return ContentFile(buf.getvalue(), name="foto.webp")


class CampoMixin:
    """Aplica o estilo .campo do app.css nos campos de texto e seleção."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if not isinstance(campo.widget, (forms.CheckboxInput, forms.FileInput)):
                campo.widget.attrs.setdefault("class", "campo")


class ColecaoForm(CampoMixin, forms.ModelForm):
    class Meta:
        model = Colecao
        fields = ["nome", "simbolo"]
        labels = {"nome": "Nome da coleção"}
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Dólar americano"}),
            "simbolo": forms.TextInput(attrs={"placeholder": "Ex.: US$"}),
        }

    def __init__(self, *args, dono, **kwargs):
        super().__init__(*args, **kwargs)
        self.dono = dono

    def clean_nome(self):
        nome = self.cleaned_data["nome"].strip()
        mesmas = Colecao.objects.filter(nome__iexact=nome).exclude(pk=self.instance.pk)
        if mesmas.filter(dono=self.dono).exists():
            raise forms.ValidationError("Você já tem uma coleção com esse nome.")
        if mesmas.filter(dono__isnull=True).exists():
            raise forms.ValidationError("Já existe uma coleção oficial com esse nome.")
        return nome


class DenominacaoForm(CampoMixin, forms.ModelForm):
    class Meta:
        model = Denominacao
        fields = ["nome", "valor_centavos"]
        labels = {"nome": "Nome do valor", "valor_centavos": "Valor em centavos"}
        help_texts = {"valor_centavos": "Ex.: 25 para 25 cents, 100 para 1 dólar. Ordena os valores e ajuda na busca."}
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: 25 Cents (Quarter)"}),
            "valor_centavos": forms.NumberInput(attrs={"min": 1, "inputmode": "numeric"}),
        }

    def __init__(self, *args, colecao, **kwargs):
        super().__init__(*args, **kwargs)
        self.colecao = colecao

    def clean(self):
        dados = super().clean()
        outras = Denominacao.objects.filter(colecao=self.colecao).exclude(pk=self.instance.pk)
        if dados.get("nome") and outras.filter(nome__iexact=dados["nome"].strip()).exists():
            self.add_error("nome", "Já existe um valor com esse nome nesta coleção.")
        if dados.get("valor_centavos") and outras.filter(valor_centavos=dados["valor_centavos"]).exists():
            self.add_error("valor_centavos", "Já existe um valor com esse número nesta coleção.")
        return dados


class SerieForm(CampoMixin, forms.ModelForm):
    TIPOS = [Serie.Tipo.CIRCULACAO, Serie.Tipo.COMEMORATIVA, Serie.Tipo.OUTRA]

    class Meta:
        model = Serie
        fields = ["nome", "tipo", "ordem"]
        labels = {"nome": "Nome da série", "tipo": "Tipo", "ordem": "Posição na tela inicial"}
        help_texts = {"ordem": "Números menores aparecem primeiro."}
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Moedas de circulação"}),
            "ordem": forms.NumberInput(attrs={"min": 0, "inputmode": "numeric"}),
        }

    def __init__(self, *args, colecao, **kwargs):
        super().__init__(*args, **kwargs)
        self.colecao = colecao
        self.fields["tipo"].choices = [(t.value, t.label) for t in self.TIPOS]

    def clean_nome(self):
        nome = self.cleaned_data["nome"].strip()
        outras = Serie.objects.filter(colecao=self.colecao).exclude(pk=self.instance.pk)
        if outras.filter(nome__iexact=nome).exists():
            raise forms.ValidationError("Já existe uma série com esse nome nesta coleção.")
        return nome


class MoedaForm(CampoMixin, forms.ModelForm):
    ano_ate = forms.IntegerField(
        label="Até o ano (opcional)", required=False, min_value=1500, max_value=2100,
        help_text="Preencha para cadastrar uma moeda para cada ano da faixa de uma vez (ex.: 1999 até 2024).",
        widget=forms.NumberInput(attrs={"inputmode": "numeric"}),
    )
    foto_cara = forms.ImageField(label="Foto da cara", required=False)
    foto_coroa = forms.ImageField(label="Foto da coroa", required=False)
    remover_cara = forms.BooleanField(label="Remover a foto da cara", required=False)
    remover_coroa = forms.BooleanField(label="Remover a foto da coroa", required=False)

    class Meta:
        model = Moeda
        fields = ["serie", "denominacao", "ano", "variante", "descricao", "cor_metal", "como_identificar"]
        labels = {
            "serie": "Série",
            "denominacao": "Valor",
            "ano": "Ano",
            "variante": "Variante (opcional)",
            "descricao": "Descrição / tema (opcional)",
            "cor_metal": "Cor do metal",
            "como_identificar": "Como identificar (opcional)",
        }
        help_texts = {
            "variante": "Marca que diferencia moedas do mesmo ano (ex.: letra da casa da moeda). Vazio na maioria.",
            "descricao": "Para comemorativas: o tema. Vazio nas moedas comuns.",
            "cor_metal": "Cor da bolinha quando você tiver a moeda.",
            "como_identificar": "Dica para diferenciar de outra moeda parecida.",
        }
        widgets = {
            "ano": forms.NumberInput(attrs={"min": 1500, "max": 2100, "inputmode": "numeric"}),
            "variante": forms.TextInput(attrs={"placeholder": 'Ex.: "D" (casa da moeda de Denver)'}),
            "descricao": forms.TextInput(attrs={"placeholder": "Ex.: Estado do Texas"}),
            "como_identificar": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, colecao, **kwargs):
        super().__init__(*args, **kwargs)
        self.colecao = colecao
        self.fields["serie"].queryset = colecao.series.all()
        self.fields["denominacao"].queryset = colecao.denominacoes.all()
        self.fields["serie"].empty_label = None
        self.fields["denominacao"].empty_label = None
        self.fields["ano"].widget.attrs.update(min=1500, max=2100)
        self.fields["cor_metal"].choices = [("", "Automática (prateada)")] + list(Moeda.Metal.choices)
        for lado in ("cara", "coroa"):
            self.fields[f"foto_{lado}"].widget.attrs["accept"] = "image/*"
        if self.instance.pk:
            del self.fields["ano_ate"]  # faixa de anos só ao cadastrar
        else:
            del self.fields["remover_cara"], self.fields["remover_coroa"]

    @property
    def campos_principais(self):
        nomes = ["serie", "denominacao", "ano", "ano_ate", "variante", "descricao", "cor_metal", "como_identificar"]
        return [self[n] for n in nomes if n in self.fields]

    @property
    def lados_foto(self):
        """[(lado, campo da foto, campo "remover" ou None, url da foto enviada atual)] para o template."""
        lados = []
        for lado in ("cara", "coroa"):
            atual = getattr(self.instance, f"imagem_{lado}")
            remover = self[f"remover_{lado}"] if f"remover_{lado}" in self.fields else None
            lados.append((lado, self[f"foto_{lado}"], remover, atual.url if atual else ""))
        return lados

    def _validar_foto(self, nome):
        foto = self.cleaned_data.get(nome)
        if foto and foto.size > TAMANHO_MAX_FOTO:
            raise forms.ValidationError("A foto passa de 10 MB. Tire outra com resolução menor.")
        return foto

    def clean_foto_cara(self):
        return self._validar_foto("foto_cara")

    def clean_foto_coroa(self):
        return self._validar_foto("foto_coroa")

    def clean_variante(self):
        return self.cleaned_data["variante"].strip().upper()

    def clean_descricao(self):
        return self.cleaned_data["descricao"].strip()

    def clean(self):
        dados = super().clean()
        ano, ate = dados.get("ano"), dados.get("ano_ate")
        if ano is not None and not 1500 <= ano <= 2100:
            self.add_error("ano", "Informe um ano entre 1500 e 2100.")
        if ano is not None and ate is not None:
            if ate < ano:
                self.add_error("ano_ate", "O ano final precisa ser igual ou maior que o inicial.")
            elif ate - ano > MAX_FAIXA_ANOS:
                self.add_error("ano_ate", f"No máximo {MAX_FAIXA_ANOS} anos de uma vez.")
        if self.instance.pk and not self.errors:
            repetida = Moeda.objects.filter(
                serie=dados["serie"], denominacao=dados["denominacao"], ano=dados["ano"],
                variante=dados["variante"], descricao=dados["descricao"],
            ).exclude(pk=self.instance.pk)
            if repetida.exists():
                raise forms.ValidationError("Já existe uma moeda igual nesta série (mesmo valor, ano, variante e descrição).")
        return dados

    def _get_validation_exclusions(self):
        # Sem "ano" o Django não confere a moeda_unica_no_catalogo: ao cadastrar, os anos que já
        # existem são pulados; ao editar, o clean() acima confere.
        return super()._get_validation_exclusions() | {"ano"}

    def anos(self):
        ano = self.cleaned_data["ano"]
        return list(range(ano, (self.cleaned_data.get("ano_ate") or ano) + 1))
