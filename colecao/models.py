"""Modelo de dados.

Catálogo (o que existe, igual para todos):  Serie -> Moeda <- Denominacao
Coleção (o que cada pessoa tem):           ItemColecao (1 por usuário + moeda)

Cada "bolinha" do PDF é uma Moeda: série + denominação + ano (+ variante/descrição).
"""
import secrets
import unicodedata

from django.conf import settings
from django.db import models


def normalizar(texto: str) -> str:
    """Minúsculas e sem acento, para a busca funcionar com 'natacao' ou 'Natação'."""
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


class Serie(models.Model):
    class Tipo(models.TextChoices):
        FAMILIA = "FAMILIA", "Família"
        COMEMORATIVA = "COMEMORATIVA", "Comemorativa"
        OLIMPIADA = "OLIMPIADA", "Olimpíadas"
        OUTRA = "OUTRA", "Outra"

    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    nome = models.CharField(max_length=120, unique=True)
    ordem = models.PositiveIntegerField(default=0, help_text="Posição na tela inicial")

    class Meta:
        ordering = ["ordem", "nome"]
        verbose_name = "série"
        verbose_name_plural = "séries"

    def __str__(self):
        return self.nome


class Denominacao(models.Model):
    nome = models.CharField(max_length=40, unique=True)
    valor_centavos = models.PositiveIntegerField(unique=True)

    class Meta:
        ordering = ["valor_centavos"]
        verbose_name = "denominação"
        verbose_name_plural = "denominações"

    def __str__(self):
        return self.nome


class Moeda(models.Model):
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
    def tem_foto(self):
        return bool(self.foto_cara or self.foto_coroa)

    @property
    def metal(self):
        """Cor aproximada do metal, só para a tela ficar parecida com a moeda real."""
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
