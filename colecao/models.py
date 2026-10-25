"""Modelo de dados.

Catálogo (o que existe):          Colecao -> Serie -> Moeda <- Denominacao
Coleção (o que cada pessoa tem):  ItemColecao (1 por usuário + moeda)

Uma Colecao sem dono é oficial e igual para todos (o Real, mantido pelo admin e pelo carregar_catalogo):
o usuário só marca e pode ocultar. Com dono é privada: só aquele usuário vê e edita o catálogo dela.
Cada "bolinha" do PDF é uma Moeda: série + denominação + ano (+ variante/descrição).
"""
import secrets
import unicodedata
import uuid

from django.conf import settings
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.templatetags.static import static


def normalizar(texto: str) -> str:
    """Minúsculas e sem acento, para a busca funcionar com 'natacao' ou 'Natação'."""
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


class ColecaoQuerySet(models.QuerySet):
    def visiveis_para(self, user):
        """Oficiais + as criadas por este usuário (inclusive as que ele ocultou)."""
        return self.filter(Q(dono__isnull=True) | Q(dono=user))

    def ativas_para(self, user):
        """Visíveis e não ocultas: as que aparecem no seletor da tela inicial."""
        return self.visiveis_para(user).exclude(ocultada_por=user)


class Colecao(models.Model):
    SLUG_REAL = "real"

    nome = models.CharField(max_length=60)
    simbolo = models.CharField("símbolo", max_length=8, blank=True, help_text='Ex.: "R$", "US$", "€".')
    slug = models.SlugField(
        max_length=30, unique=True, null=True, blank=True,
        help_text='Só nas coleções oficiais carregadas por comando (o Real é "real").',
    )
    dono = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
        related_name="colecoes", help_text="Vazio = coleção oficial, igual para todos.",
    )
    ordem = models.PositiveIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)
    ocultada_por = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="colecoes_ocultas"
    )

    objects = ColecaoQuerySet.as_manager()

    class Meta:
        ordering = [F("dono").asc(nulls_first=True), "ordem", "nome"]  # oficiais primeiro
        verbose_name = "coleção"
        verbose_name_plural = "coleções"
        constraints = [
            models.UniqueConstraint(fields=["dono", "nome"], name="colecao_nome_unico_por_dono")
        ]

    def __str__(self):
        return self.nome

    @property
    def oficial(self):
        return self.dono_id is None

    @property
    def e_real(self):
        return self.slug == self.SLUG_REAL

    @property
    def titulo(self):
        """Usado nos textos de compartilhar e na página pública."""
        return "Moedas do Real" if self.e_real else f"Moedas – {self.nome}"

    @transaction.atomic
    def apagar(self):
        """Exclui a coleção com todo o catálogo dela (e as fotos, pelo sinal de Moeda).

        As moedas protegem séries e valores (PROTECT), então a ordem importa.
        """
        Moeda.objects.filter(serie__colecao=self).delete()
        self.series.all().delete()
        self.denominacoes.all().delete()
        self.delete()


class Serie(models.Model):
    class Tipo(models.TextChoices):
        CIRCULACAO = "CIRCULACAO", "Circulação"
        COMEMORATIVA = "COMEMORATIVA", "Comemorativa"
        OUTRA = "OUTRA", "Outra"

    colecao = models.ForeignKey(
        Colecao, on_delete=models.PROTECT, related_name="series", verbose_name="coleção"
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    nome = models.CharField(max_length=120)
    ordem = models.PositiveIntegerField(default=0, help_text="Posição na tela inicial")

    class Meta:
        ordering = ["ordem", "nome"]
        verbose_name = "série"
        verbose_name_plural = "séries"
        constraints = [
            models.UniqueConstraint(fields=["colecao", "nome"], name="serie_nome_unico_na_colecao")
        ]

    def __str__(self):
        return self.nome


class Denominacao(models.Model):
    colecao = models.ForeignKey(
        Colecao, on_delete=models.PROTECT, related_name="denominacoes", verbose_name="coleção"
    )
    nome = models.CharField(max_length=40)
    valor_centavos = models.PositiveIntegerField(
        help_text="Valor na menor unidade da moeda (centavos, cents…): ordena e ajuda na busca."
    )

    class Meta:
        ordering = ["valor_centavos"]
        verbose_name = "denominação"
        verbose_name_plural = "denominações"
        constraints = [
            models.UniqueConstraint(fields=["colecao", "nome"], name="denominacao_nome_unico_na_colecao"),
            models.UniqueConstraint(
                fields=["colecao", "valor_centavos"], name="denominacao_valor_unico_na_colecao"
            ),
        ]

    def __str__(self):
        return self.nome


def caminho_foto(instance, filename):
    """Fotos enviadas pelos usuários: nome aleatório, separado por dono da coleção."""
    return f"fotos/{instance.serie.colecao.dono_id or 0}/{uuid.uuid4().hex}.webp"


class Moeda(models.Model):
    class Metal(models.TextChoices):
        PRATA = "prata", "Prateada"
        COBRE = "cobre", "Cobre"
        LATAO = "latao", "Dourada (latão)"
        BIMETAL = "bimetal", "Bimetálica"

    serie = models.ForeignKey(Serie, on_delete=models.PROTECT, related_name="moedas")
    denominacao = models.ForeignKey(Denominacao, on_delete=models.PROTECT, related_name="moedas")
    ano = models.PositiveSmallIntegerField()
    variante = models.CharField(
        max_length=10, blank=True, help_text='Ex.: "A" para 2019A. Vazio na maioria.'
    )
    descricao = models.CharField(
        max_length=150, blank=True, help_text='Tema da comemorativa/olímpica. Ex.: "Basquete".'
    )
    ordem = models.PositiveIntegerField(default=0, help_text="Ordem dentro da série (opcional)")
    foto_cara = models.CharField(
        "foto da cara", max_length=200, blank=True,
        help_text='Caminho dentro de static/, ex.: "moedas/f2-5-cara.webp" (lado do retrato/tema).',
    )
    foto_coroa = models.CharField(
        "foto da coroa", max_length=200, blank=True,
        help_text='Caminho dentro de static/, ex.: "moedas/f2-5-coroa.webp" (lado do valor).',
    )
    foto_credito = models.CharField("crédito das fotos", max_length=400, blank=True)
    imagem_cara = models.ImageField(
        "foto enviada (cara)", upload_to=caminho_foto, blank=True,
        help_text="Foto enviada pelo usuário; tem prioridade sobre a foto da cara em static/.",
    )
    imagem_coroa = models.ImageField("foto enviada (coroa)", upload_to=caminho_foto, blank=True)
    cor_metal = models.CharField(
        "cor do metal", max_length=10, choices=Metal.choices, blank=True,
        help_text="Cor do chip quando a moeda está marcada. Vazio = automático.",
    )
    como_identificar = models.TextField(
        "como identificar", blank=True,
        help_text='Dica para distinguir esta moeda de outra parecida. Ex.: "Letra A no canto inferior esquerdo".',
    )
    busca =models.CharField(max_length=300, editable=False, db_index=True, default="")

    class Meta:
        ordering = ["serie__ordem", "denominacao__valor_centavos", "ordem", "ano", "variante"]
        constraints = [
            models.UniqueConstraint(
                fields=["serie", "denominacao", "ano", "variante", "descricao"],
                name="moeda_unica_no_catalogo",
            )
        ]

    @property
    def ano_rotulo(self):
        return f"{self.ano}{self.variante}"

    @property
    def url_cara(self):
        if self.imagem_cara:
            return self.imagem_cara.url
        return static(self.foto_cara) if self.foto_cara else ""

    @property
    def url_coroa(self):
        if self.imagem_coroa:
            return self.imagem_coroa.url
        return static(self.foto_coroa) if self.foto_coroa else ""

    @property
    def tem_foto(self):
        return bool(self.foto_cara or self.foto_coroa or self.imagem_cara or self.imagem_coroa)

    @property
    def metal(self):
        """Cor aproximada do metal, só para a tela ficar parecida com a moeda real."""
        if self.cor_metal:
            return self.cor_metal
        if not self.serie.colecao.e_real:
            return "prata"
        if self.ano < 1998:  # 1ª família (aço inox), inclusive as FAO de 1995
            return "prata"
        return {1: "cobre", 5: "cobre", 10: "latao", 25: "latao", 50: "prata"}.get(
            self.denominacao.valor_centavos, "bimetal"
        )

    def __str__(self):
        base = f"{self.denominacao} {self.ano_rotulo}"
        return f"{base} – {self.descricao}" if self.descricao else f"{base} ({self.serie})"

    def save(self, *args, **kwargs):
        partes = [
            self.denominacao.nome,
            self.serie.nome,
            self.serie.get_tipo_display(),
            str(self.ano),
            self.ano_rotulo,
            self.descricao,
        ]
        self.busca = normalizar(" ".join(partes))[:300]
        super().save(*args, **kwargs)


def apagar_foto_se_orfa(nome, storage):
    """Apaga o arquivo depois do commit, se nenhuma moeda usa mais (uma faixa de anos divide a mesma foto)."""
    if not nome:
        return

    def apagar():
        if not Moeda.objects.filter(Q(imagem_cara=nome) | Q(imagem_coroa=nome)).exists():
            storage.delete(nome)

    transaction.on_commit(apagar)


@receiver(post_delete, sender=Moeda)
def apagar_fotos_enviadas(sender, instance, **kwargs):
    """Moeda excluída (sozinha, com a coleção ou com a conta): apaga os arquivos das fotos."""
    for campo in (instance.imagem_cara, instance.imagem_coroa):
        if campo:
            apagar_foto_se_orfa(campo.name, campo.storage)


class ItemColecao(models.Model):
    class Estado(models.TextChoices):
        # Escala usual da numismática brasileira, da pior para a melhor.
        UTGC = "UTGC", "UTGC – Um tanto gasta"
        BC = "BC", "BC – Bem conservada"
        MBC = "MBC", "MBC – Muito bem conservada"
        SOB = "SOB", "SOB – Soberba"
        FC = "FC", "FC – Flor de cunho"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="itens_colecao"
    )
    moeda = models.ForeignKey(Moeda, on_delete=models.CASCADE, related_name="itens")
    quantidade = models.PositiveIntegerField(default=0)
    estado = models.CharField(max_length=5, choices=Estado.choices, blank=True)
    observacao = models.TextField(blank=True)
    adquirida_em = models.DateField(null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "item da coleção"
        verbose_name_plural = "itens da coleção"
        constraints = [
            models.UniqueConstraint(fields=["user", "moeda"], name="item_unico_por_usuario")
        ]

    @property
    def tenho(self):
        return self.quantidade > 0

    def __str__(self):
        return f"{self.moeda} × {self.quantidade} ({self.user})"


# ---------- notificações ----------

class Aviso(models.Model):
    """Novidade enviada a todos (moeda nova, lançamento etc.).

    Ao salvar um aviso novo no admin ele aparece em "Novidades" e,
    se as notificações estiverem configuradas, vai por push para quem ativou.
    """

    titulo = models.CharField(max_length=80)
    texto = models.CharField(max_length=240)
    link = models.CharField(
        max_length=200, blank=True, help_text='Caminho dentro do app, ex.: "/serie/2/". Vazio = Novidades.'
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    enviados = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "aviso"
        verbose_name_plural = "avisos (notificações)"

    def __str__(self):
        return self.titulo

    def clean(self):
        super().clean()
        if self.link:
            self.link = self.link.strip()
            if not self.link.startswith("/"):
                from django.core.exceptions import ValidationError
                raise ValidationError({"link": "O link deve ser um caminho interno do app começando com '/' (ex.: /serie/2/)."})


class InscricaoPush(models.Model):
    """Um navegador/celular que aceitou receber notificações."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inscricoes_push"
    )
    endpoint = models.URLField(max_length=600, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "inscrição de notificação"
        verbose_name_plural = "inscrições de notificação"

    def __str__(self):
        return f"{self.user} – {self.endpoint[:40]}…"


# ---------- compartilhamento por link ----------

def novo_token():
    return secrets.token_urlsafe(16)


class PerfilPublico(models.Model):
    """Link de leitura da coleção de um usuário (desligado até ele ativar)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil_publico"
    )
    ativo = models.BooleanField(default=False)
    token = models.CharField(max_length=40, unique=True, default=novo_token, editable=False)
    nome = models.CharField("nome na página pública", max_length=40, blank=True)
    compartilhar_estado = models.BooleanField(
        "compartilhar estado das moedas",
        default=False,
        help_text="Exibe o estado de conservação (ex.: MBC, SOB, FC) na página pública.",
    )

    class Meta:
        verbose_name = "perfil público"
        verbose_name_plural = "perfis públicos"

    @property
    def nome_exibido(self):
        return self.nome or "Colecionador"

    def __str__(self):
        return f"{self.user} ({'ativo' if self.ativo else 'desligado'})"
