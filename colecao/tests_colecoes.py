"""Testes da versão 2.0: coleções (o Real oficial + coleções próprias de cada usuário) e fotos enviadas."""
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from . import planilha
from .models import Colecao, Denominacao, ItemColecao, Moeda, PerfilPublico, Serie
from .views import interpretar_busca


class ColecoesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("carregar_catalogo", verbosity=0)
        cls.real = Colecao.objects.get(slug=Colecao.SLUG_REAL)
        cls.ana = User.objects.create_user("ana", "ana@ex.com", "senha-de-teste-123")
        cls.beto = User.objects.create_user("beto", "beto@ex.com", "senha-de-teste-123")
        cls.dolar = Colecao.objects.create(nome="Dólar americano", simbolo="US$", dono=cls.ana, ordem=10)
        cls.cent = Denominacao.objects.create(colecao=cls.dolar, nome="1 Cent", valor_centavos=1)
        cls.quarter = Denominacao.objects.create(colecao=cls.dolar, nome="25 Cents (Quarter)", valor_centavos=25)
        cls.serie = Serie.objects.create(colecao=cls.dolar, nome="Circulação", tipo=Serie.Tipo.CIRCULACAO)
        cls.moedas = [
            Moeda.objects.create(serie=cls.serie, denominacao=cls.quarter, ano=ano) for ano in (1999, 2000, 2001)
        ]

    def entrar(self, user, colecao=None):
        self.client.force_login(user)
        if colecao:
            self.client.get(reverse("abrir_colecao", args=[colecao.pk]))

    def test_real_e_a_unica_oficial(self):
        self.assertEqual(list(Colecao.objects.filter(dono__isnull=True)), [self.real])
        self.assertEqual(Moeda.objects.filter(serie__colecao=self.real).count(), 193)
        call_command("carregar_catalogo", verbosity=0)  # idempotente também com outras coleções
        self.assertEqual(Colecao.objects.count(), 2)
        self.assertEqual(Moeda.objects.count(), 196)

    def test_real_continua_padrao(self):
        self.entrar(self.ana)
        r = self.client.get(reverse("inicio"))
        self.assertEqual(r.context["colecao"], self.real)
        self.assertContains(r, "de 193 moedas")
        self.assertContains(r, "Dólar americano")  # no seletor

    def test_trocar_de_colecao_e_progresso(self):
        self.entrar(self.ana, self.dolar)
        r = self.client.get(reverse("inicio"))
        self.assertContains(r, "de 3 moedas")
        self.assertContains(r, "Circulação")
        r = self.client.post(reverse("marcar", args=[self.moedas[0].pk]), headers={"HX-Current-URL": "http://testserver/"})
        self.assertContains(r, '<span class="grande">1</span>')
        self.assertContains(r, "de 3 moedas")
        self.assertContains(self.client.get(reverse("faltando")), "de 3 moedas faltando")
        self.client.get(reverse("abrir_colecao", args=[self.real.pk]))
        self.assertContains(self.client.get(reverse("inicio")), '<span class="grande">0</span>')

    def test_abrir_serie_muda_a_colecao_atual(self):
        self.entrar(self.ana)
        self.client.get(reverse("serie", args=[self.serie.pk]))
        self.assertEqual(self.client.get(reverse("inicio")).context["colecao"], self.dolar)

    def test_outro_usuario_nao_ve_nem_mexe(self):
        self.entrar(self.beto)
        m = self.moedas[0]
        for nome, args in [
            ("abrir_colecao", [self.dolar.pk]),
            ("serie", [self.serie.pk]),
            ("ficha", [m.pk]),
            ("editar_colecao", [self.dolar.pk]),
            ("valores_colecao", [self.dolar.pk]),
            ("nova_serie", [self.dolar.pk]),
            ("editar_serie", [self.serie.pk]),
            ("nova_moeda", [self.serie.pk]),
            ("editar_moeda", [m.pk]),
        ]:
            self.assertEqual(self.client.get(reverse(nome, args=args)).status_code, 404, nome)
        self.assertEqual(self.client.post(reverse("marcar", args=[m.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("ocultar_colecao", args=[self.dolar.pk])).status_code, 404)
        self.client.post(reverse("editar_moeda", args=[m.pk]), {"acao": "excluir"})
        self.assertTrue(Moeda.objects.filter(pk=m.pk).exists())
        # as moedas privadas da Ana não aparecem para o Beto
        self.assertContains(self.client.get(reverse("faltando")), "de 193 moedas faltando")
        self.assertNotContains(self.client.get(reverse("inicio")), "Dólar americano")
        self.assertNotContains(self.client.get(reverse("buscar"), {"q": "quarter"}), 'class="chip')
        self.assertNotIn(self.dolar, self.client.get(reverse("colecoes")).context["lista"])

    def test_usuario_nao_edita_nem_exclui_o_real(self):
        self.entrar(self.ana)
        for nome in ("editar_colecao", "valores_colecao", "nova_serie"):
            self.assertEqual(self.client.get(reverse(nome, args=[self.real.pk])).status_code, 404, nome)
        serie_real = Serie.objects.filter(colecao=self.real).first()
        moeda_real = serie_real.moedas.first()
        self.assertEqual(self.client.get(reverse("nova_moeda", args=[serie_real.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("editar_serie", args=[serie_real.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("editar_moeda", args=[moeda_real.pk])).status_code, 404)
        self.client.post(reverse("editar_colecao", args=[self.real.pk]), {"acao": "excluir"})
        self.assertTrue(Colecao.objects.filter(pk=self.real.pk).exists())
        self.assertNotContains(self.client.get(reverse("colecoes")), reverse("editar_colecao", args=[self.real.pk]))

    def test_busca_usa_os_valores_da_colecao(self):
        self.assertEqual(interpretar_busca("1 2003", {1, 25})["valores"], {1})
        self.assertEqual(interpretar_busca("25 1899", {25})["anos"], {1899})
        self.entrar(self.ana, self.dolar)
        r = self.client.get(reverse("buscar"), {"q": "25 2000"})
        self.assertContains(r, "2000")
        self.assertNotContains(r, "1999")
        self.assertContains(self.client.get(reverse("buscar"), {"q": "quarter"}), "2001")
        self.assertNotContains(self.client.get(reverse("buscar"), {"q": "50 2008"}), 'class="chip')

    def test_criar_catalogo_pelo_app(self):
        self.entrar(self.beto)
        r = self.client.post(reverse("nova_colecao"), {"nome": "Euro", "simbolo": "€"})
        euro = Colecao.objects.get(nome="Euro")
        self.assertEqual(euro.dono, self.beto)
        self.assertRedirects(r, reverse("valores_colecao", args=[euro.pk]))
        # nome repetido (dele ou de uma oficial) não pode
        self.assertContains(self.client.post(reverse("nova_colecao"), {"nome": "euro"}), "Você já tem")
        self.assertContains(self.client.post(reverse("nova_colecao"), {"nome": "Real"}), "coleção oficial")

        r = self.client.post(reverse("nova_serie", args=[euro.pk]), {"nome": "Circulação", "tipo": "CIRCULACAO", "ordem": 10})
        serie = Serie.objects.get(colecao=euro)
        self.assertRedirects(r, reverse("serie", args=[serie.pk]))
        # sem valores, "adicionar moedas" manda cadastrar os valores primeiro
        r = self.client.get(reverse("nova_moeda", args=[serie.pk]))
        self.assertRedirects(r, reverse("valores_colecao", args=[euro.pk]))

        url_valores = reverse("valores_colecao", args=[euro.pk])
        self.client.post(url_valores, {"acao": "adicionar", "nome": "2 Euros", "valor_centavos": 200})
        r = self.client.post(url_valores, {"acao": "adicionar", "nome": "Dois", "valor_centavos": 200})
        self.assertContains(r, "Já existe um valor com esse número")
        valor = Denominacao.objects.get(colecao=euro)

        dados = {"serie": serie.pk, "denominacao": valor.pk, "ano": 2002, "ano_ate": 2005, "variante": "",
                 "descricao": "", "cor_metal": "bimetal", "como_identificar": ""}
        self.client.post(reverse("nova_moeda", args=[serie.pk]), dados)
        self.assertEqual(list(serie.moedas.values_list("ano", flat=True)), [2002, 2003, 2004, 2005])
        dados.update(ano=2004, ano_ate=2006)
        r = self.client.post(reverse("nova_moeda", args=[serie.pk]), dados, follow=True)
        self.assertContains(r, "1 moeda(s) cadastrada(s). 2 já existia(m)")
        self.assertEqual(serie.moedas.count(), 5)
        self.assertEqual(serie.moedas.first().metal, "bimetal")
        self.assertContains(self.client.get(reverse("inicio")), "de 5 moedas")

        dados.update(ano=2010, ano_ate=2009)
        self.assertContains(self.client.post(reverse("nova_moeda", args=[serie.pk]), dados), "ano final")

        # editar não pode virar uma moeda que já existe
        m = serie.moedas.get(ano=2006)
        dados.update(ano=2005)
        del dados["ano_ate"]
        self.assertContains(self.client.post(reverse("editar_moeda", args=[m.pk]), dados), "Já existe uma moeda igual")

        # valor com moedas não pode ser excluído
        self.client.post(url_valores, {"acao": "excluir", "id": valor.pk})
        self.assertTrue(Denominacao.objects.filter(pk=valor.pk).exists())

    def test_metal(self):
        self.assertEqual(self.moedas[0].metal, "prata")
        self.moedas[0].cor_metal = "cobre"
        self.assertEqual(self.moedas[0].metal, "cobre")
        um_centavo_2004 = Moeda.objects.get(serie__colecao=self.real, denominacao__valor_centavos=1, ano=2004)
        self.assertEqual(um_centavo_2004.metal, "cobre")
        um_real_1994 = Moeda.objects.get(serie__colecao=self.real, denominacao__valor_centavos=100, ano=1994)
        self.assertEqual(um_real_1994.metal, "prata")

    def test_ocultar_real_nao_apaga_o_que_foi_marcado(self):
        moeda_real = Moeda.objects.filter(serie__colecao=self.real).first()
        ItemColecao.objects.create(user=self.ana, moeda=moeda_real, quantidade=2)
        self.entrar(self.ana)
        self.client.post(reverse("ocultar_colecao", args=[self.real.pk]))
        r = self.client.get(reverse("inicio"))
        self.assertEqual(r.context["colecao"], self.dolar)
        self.assertNotIn(self.real, r.context["colecoes"])
        self.assertTrue(ItemColecao.objects.filter(user=self.ana, moeda=moeda_real, quantidade=2).exists())
        # ainda dá para abrir de propósito pela lista de coleções
        self.client.get(reverse("abrir_colecao", args=[self.real.pk]))
        self.assertEqual(self.client.get(reverse("inicio")).context["colecao"], self.real)
        self.client.post(reverse("ocultar_colecao", args=[self.real.pk]))  # mostra de novo
        self.assertIn(self.real, self.client.get(reverse("inicio")).context["colecoes"])

    def test_tudo_oculto_vai_para_colecoes(self):
        self.entrar(self.beto)
        self.client.post(reverse("ocultar_colecao", args=[self.real.pk]))
        self.assertRedirects(self.client.get(reverse("inicio")), reverse("colecoes"))
        self.assertRedirects(self.client.get(reverse("faltando")), reverse("colecoes"))

    def test_compartilhar_e_pagina_publica(self):
        self.entrar(self.ana, self.dolar)
        r = self.client.get(reverse("compartilhar"))
        self.assertContains(r, "Moedas – Dólar americano que me faltam (3 de 3)")
        self.assertNotContains(r, "Família")
        self.client.get(reverse("conta"))
        self.client.post(reverse("compartilhar_colecao"), {"acao": "ativar", "nome": "Ana"})
        token = PerfilPublico.objects.get(user=self.ana).token
        self.client.logout()
        url = reverse("colecao_publica", args=[token])
        r = self.client.get(url)
        self.assertEqual(r.context["colecao"], self.real)
        self.assertContains(r, "Dólar americano")  # no seletor
        r = self.client.get(url, {"colecao": self.dolar.pk})
        self.assertContains(r, "de 3 moedas")
        self.assertContains(r, "Moedas – Dólar americano · somente leitura")
        # coleção de outra pessoa pelo parâmetro: ignora e mostra a padrão
        euro = Colecao.objects.create(nome="Euro", dono=self.beto)
        self.assertEqual(self.client.get(url, {"colecao": euro.pk}).context["colecao"], self.real)

    def test_excluir_serie_e_colecao(self):
        ItemColecao.objects.create(user=self.ana, moeda=self.moedas[0], quantidade=1)
        self.entrar(self.ana, self.dolar)
        self.client.post(reverse("editar_serie", args=[self.serie.pk]), {"acao": "excluir"})
        self.assertFalse(Serie.objects.filter(pk=self.serie.pk).exists())
        self.assertFalse(ItemColecao.objects.filter(user=self.ana).exists())
        r = self.client.post(reverse("editar_colecao", args=[self.dolar.pk]), {"acao": "excluir"})
        self.assertRedirects(r, reverse("colecoes"))
        self.assertFalse(Colecao.objects.filter(pk=self.dolar.pk).exists())
        self.assertFalse(Denominacao.objects.filter(colecao_id=self.dolar.pk).exists())
        self.assertEqual(self.client.get(reverse("inicio")).context["colecao"], self.real)

    def test_excluir_conta_apaga_colecoes_proprias(self):
        self.entrar(self.ana)
        self.client.post(reverse("excluir_conta"), {"confirmacao": "EXCLUIR", "senha": "senha-de-teste-123"})
        self.assertFalse(User.objects.filter(pk=self.ana.pk).exists())
        self.assertFalse(Colecao.objects.filter(pk=self.dolar.pk).exists())
        self.assertEqual(Moeda.objects.count(), 193)  # o Real continua

    def test_zerar_apaga_so_as_marcacoes_da_pessoa(self):
        moeda_real = Moeda.objects.filter(serie__colecao=self.real).first()
        ItemColecao.objects.create(user=self.ana, moeda=moeda_real, quantidade=2, observacao="minha")
        ItemColecao.objects.create(user=self.ana, moeda=self.moedas[0], quantidade=1)
        ItemColecao.objects.create(user=self.beto, moeda=moeda_real, quantidade=5)
        self.entrar(self.ana)
        r = self.client.post(reverse("zerar_colecao", args=[self.real.pk]))
        self.assertRedirects(r, reverse("colecoes"))
        self.assertFalse(ItemColecao.objects.filter(user=self.ana, moeda__serie__colecao=self.real).exists())
        self.assertTrue(ItemColecao.objects.filter(user=self.ana, moeda=self.moedas[0]).exists())  # outra coleção
        self.assertTrue(ItemColecao.objects.filter(user=self.beto, moeda=moeda_real, quantidade=5).exists())
        self.assertEqual(Moeda.objects.filter(serie__colecao=self.real).count(), 193)  # catálogo intacto
        self.assertEqual(self.client.get(reverse("zerar_colecao", args=[self.real.pk])).status_code, 405)  # só POST
        self.entrar(self.beto)
        self.assertEqual(self.client.post(reverse("zerar_colecao", args=[self.dolar.pk])).status_code, 404)

    def test_exportar_planilha(self):
        from datetime import date

        ItemColecao.objects.create(
            user=self.ana, moeda=self.moedas[1], quantidade=2, estado="MBC",
            adquirida_em=date(2026, 10, 19), observacao="=troco da padaria",
        )
        self.entrar(self.ana)
        r = self.client.get(reverse("exportar_colecao", args=[self.dolar.pk]))
        self.assertEqual(r["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('filename="moedas-dolar-americano-', r["Content-Disposition"])
        linhas = r.content.decode("utf-8-sig").splitlines()
        self.assertEqual(linhas[0], ";".join(planilha.COLUNAS))
        self.assertEqual(len(linhas), 4)  # cabeçalho + 3 moedas, inclusive as que faltam
        self.assertIn("Dólar americano;US$;Circulação;Circulação;25 Cents (Quarter);25;1999;;;;;0;;;", linhas)
        self.assertIn(
            "Dólar americano;US$;Circulação;Circulação;25 Cents (Quarter);25;2000;;;;;2;MBC;19/10/2026;'=troco da padaria",
            linhas,
        )
        real = self.client.get(reverse("exportar_colecao", args=[self.real.pk])).content.decode("utf-8-sig")
        self.assertEqual(len(real.splitlines()), 194)
        self.entrar(self.beto)
        self.assertEqual(self.client.get(reverse("exportar_colecao", args=[self.dolar.pk])).status_code, 404)



class BackupTests(TestCase):
    """Baixar o backup numa conta e importar em outra (é o jeito de “trocar de e-mail”)."""

    @classmethod
    def setUpTestData(cls):
        from datetime import date

        call_command("carregar_catalogo", verbosity=0)
        cls.real = Colecao.objects.get(slug=Colecao.SLUG_REAL)
        cls.ana = User.objects.create_user("ana", "ana@ex.com", "senha-de-teste-123")
        cls.carla = User.objects.create_user("carla", "carla@ex.com", "senha-de-teste-123")
        dolar = Colecao.objects.create(nome="Dólar americano", simbolo="US$", dono=cls.ana, ordem=10)
        quarter = Denominacao.objects.create(colecao=dolar, nome="25 Cents", valor_centavos=25)
        estados = Serie.objects.create(colecao=dolar, nome="50 Estados", tipo=Serie.Tipo.COMEMORATIVA, ordem=20)
        texas = Moeda.objects.create(serie=estados, denominacao=quarter, ano=2004, descricao="Texas", cor_metal="prata",
                                     como_identificar="Estrela solitária")
        Moeda.objects.create(serie=estados, denominacao=quarter, ano=2004, descricao="Iowa")
        m2019a = Moeda.objects.get(serie__colecao=cls.real, denominacao__valor_centavos=5, ano=2019, variante="A")
        ItemColecao.objects.create(user=cls.ana, moeda=m2019a, quantidade=2, estado="SOB",
                                   adquirida_em=date(2026, 10, 19), observacao="troco; padaria")
        ItemColecao.objects.create(user=cls.ana, moeda=texas, quantidade=1, estado="FC")

    def baixar(self, user):
        self.client.force_login(user)
        r = self.client.get(reverse("exportar_tudo"))
        self.assertIn('filename="moedas-backup-', r["Content-Disposition"])
        return r.content

    def importar(self, conteudo, nome="backup.csv"):
        return self.client.post(
            reverse("importar_backup"), {"arquivo": SimpleUploadedFile(nome, conteudo, content_type="text/csv")}, follow=True
        )

    def marcacoes(self, user):
        return sorted(
            (i.moeda.serie.colecao.nome, i.moeda.serie.nome, i.moeda.denominacao.valor_centavos, i.moeda.ano,
             i.moeda.variante, i.moeda.descricao, i.quantidade, i.estado, i.adquirida_em, i.observacao)
            for i in ItemColecao.objects.filter(user=user).select_related("moeda__serie__colecao", "moeda__denominacao")
        )

    def test_levar_tudo_para_outra_conta(self):
        conteudo = self.baixar(self.ana)
        self.client.force_login(self.carla)
        r = self.importar(conteudo)
        self.assertContains(r, "2 moeda(s) com marcações restauradas, 1 coleção(ões) criada(s), 2 moeda(s) cadastrada(s)")
        self.assertEqual(self.marcacoes(self.carla), self.marcacoes(self.ana))
        dolar = self.carla.colecoes.get()
        self.assertEqual((dolar.nome, dolar.simbolo), ("Dólar americano", "US$"))
        texas = Moeda.objects.get(serie__colecao=dolar, descricao="Texas")
        self.assertEqual((texas.serie.tipo, texas.cor_metal, texas.como_identificar), ("COMEMORATIVA", "prata", "Estrela solitária"))
        self.assertEqual(texas.denominacao.valor_centavos, 25)
        self.assertEqual(Moeda.objects.filter(serie__colecao=self.real).count(), 193)  # o Real não ganha nada

        # importar de novo não duplica nada
        r = self.importar(conteudo)
        self.assertContains(r, "2 moeda(s) com marcações restauradas.")
        self.assertEqual(self.carla.colecoes.count(), 1)
        self.assertEqual(Moeda.objects.filter(serie__colecao=dolar).count(), 2)

    def test_planilha_salva_de_novo_pelo_excel(self):
        import csv
        import io

        linhas = list(csv.reader(io.StringIO(self.baixar(self.ana).decode("utf-8-sig")), delimiter=";"))
        # o Excel salva com outro separador, acentos em Windows-1252 e às vezes números como "25.0"
        saida = io.StringIO()
        csv.writer(saida, delimiter="\t").writerows([[c + ".0" if c == "25" else c for c in li] for li in linhas])
        excel = saida.getvalue().encode("cp1252")
        self.client.force_login(self.carla)
        self.importar(excel)
        self.assertEqual(self.marcacoes(self.carla), self.marcacoes(self.ana))

    def test_linhas_com_erro_sao_puladas(self):
        cab = ";".join(planilha.COLUNAS)
        linhas = [
            cab,
            "Real;R$;2ª Família;Circulação;5 Centavos;5;2008;;;;;3;MBC;;",          # ok
            "Real;R$;2ª Família;Circulação;50 Centavos;50;1999;;;;;1;;;",           # 1999 não existe no Real
            "Real;R$;2ª Família;Circulação;5 Centavos;5;2009;;;;;1;XYZ;;",          # estado inválido
            "Euro;€;Circulação;Circulação;2 Euros;;2002;;;;;1;;;",                  # valor novo sem centavos
            "Euro;€;Circulação;Circulação;2 Euros;200;2003;;;;;1;;31/02/2020;",     # data inválida
            "Euro;€;Circulação;Circulação;2 Euros;200;2004;;;;;1;;;",               # ok
        ]
        self.client.force_login(self.carla)
        r = self.importar("\n".join(linhas).encode("utf-8"))
        self.assertContains(r, "4 linha(s) ignorada(s)")
        self.assertContains(r, "linha 3: a moeda 50 Centavos 1999 não existe em Real")
        self.assertEqual(ItemColecao.objects.filter(user=self.carla).count(), 2)
        euro = self.carla.colecoes.get(nome="Euro")
        # as linhas desfeitas não deixaram restos (a série/valor da linha 5 só existe por causa da linha 7)
        self.assertEqual(list(Moeda.objects.filter(serie__colecao=euro).values_list("ano", flat=True)), [2004])
        self.assertEqual(euro.denominacoes.count(), 1)

    def test_arquivo_errado(self):
        self.client.force_login(self.carla)
        self.assertContains(self.importar(b"nome;idade\nfulano;3"), "não tem as colunas")
        self.assertContains(self.importar(b""), "vazio")
        r = self.client.post(reverse("importar_backup"))
        self.assertRedirects(r, reverse("colecoes") + "#backup", fetch_redirect_response=False)
        self.assertFalse(ItemColecao.objects.filter(user=self.carla).exists())


class FotosEnviadasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = User.objects.create_user("ana", "ana@ex.com", "senha-de-teste-123")
        cls.beto = User.objects.create_user("beto", "beto@ex.com", "senha-de-teste-123")
        cls.dolar = Colecao.objects.create(nome="Dólar americano", dono=cls.ana)
        cls.quarter = Denominacao.objects.create(colecao=cls.dolar, nome="25 Cents", valor_centavos=25)
        cls.serie = Serie.objects.create(colecao=cls.dolar, nome="Circulação", tipo=Serie.Tipo.CIRCULACAO)

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        ajuste = override_settings(MEDIA_ROOT=self.media)
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        self.client.force_login(self.ana)

    def foto(self, tamanho=(2000, 1500)):
        buf = BytesIO()
        Image.new("RGB", tamanho, (200, 150, 60)).save(buf, "JPEG")
        return SimpleUploadedFile("IMG_0001.jpg", buf.getvalue(), content_type="image/jpeg")

    def arquivos(self):
        return sorted(p for p in Path(self.media).rglob("*") if p.is_file())

    def dados(self, **extra):
        return {"serie": self.serie.pk, "denominacao": self.quarter.pk, "ano": 1999, "variante": "",
                "descricao": "", "cor_metal": "", "como_identificar": "", **extra}

    def cadastrar(self, **extra):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("nova_moeda", args=[self.serie.pk]), self.dados(**extra))

    def test_foto_reduzida_em_webp_e_dividida_na_faixa(self):
        self.cadastrar(ano_ate=2001, foto_cara=self.foto())
        arquivos = self.arquivos()
        self.assertEqual(len(arquivos), 1)
        self.assertEqual(arquivos[0].parent.name, str(self.ana.pk))
        self.assertEqual(arquivos[0].suffix, ".webp")
        with Image.open(arquivos[0]) as img:
            self.assertEqual(img.format, "WEBP")
            self.assertEqual(max(img.size), 800)
        self.assertEqual(self.serie.moedas.count(), 3)
        self.assertEqual(len(set(self.serie.moedas.values_list("imagem_cara", flat=True))), 1)

        m = self.serie.moedas.first()
        self.assertContains(self.client.get(reverse("ficha", args=[m.pk])), m.imagem_cara.url)
        self.assertEqual(self.client.get(m.imagem_cara.url).status_code, 200)
        self.client.force_login(self.beto)
        self.assertEqual(self.client.get(m.imagem_cara.url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(m.imagem_cara.url).status_code, 302)

    def test_arquivo_so_sai_quando_ninguem_usa(self):
        self.cadastrar(ano_ate=2000, foto_cara=self.foto())
        m1999, m2000 = self.serie.moedas.order_by("ano")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("editar_moeda", args=[m1999.pk]), {"acao": "excluir"})
        self.assertEqual(len(self.arquivos()), 1)  # a de 2000 ainda usa
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("editar_moeda", args=[m2000.pk]), {"acao": "excluir"})
        self.assertEqual(self.arquivos(), [])

    def test_trocar_e_remover_foto(self):
        self.cadastrar(foto_cara=self.foto())
        m = self.serie.moedas.get()
        antiga = m.imagem_cara.name
        url = reverse("editar_moeda", args=[m.pk])
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, self.dados(foto_cara=self.foto((300, 300))))
        m.refresh_from_db()
        self.assertNotEqual(m.imagem_cara.name, antiga)
        self.assertEqual(len(self.arquivos()), 1)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, self.dados(remover_cara="on"))
        m.refresh_from_db()
        self.assertFalse(m.imagem_cara)
        self.assertEqual(self.arquivos(), [])

    def test_arquivo_que_nao_e_imagem(self):
        r = self.cadastrar(foto_cara=SimpleUploadedFile("x.jpg", b"nao sou imagem", content_type="image/jpeg"))
        self.assertContains(r, 'class="erro"')
        self.assertFalse(self.serie.moedas.exists())

    def test_excluir_conta_apaga_as_fotos(self):
        self.cadastrar(foto_cara=self.foto(), foto_coroa=self.foto())
        self.assertEqual(len(self.arquivos()), 2)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("excluir_conta"), {"confirmacao": "EXCLUIR", "senha": "senha-de-teste-123"})
        self.assertEqual(self.arquivos(), [])

