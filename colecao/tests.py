from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

import json
from unittest import mock

from django.test import override_settings

from .models import Aviso, InscricaoPush, ItemColecao, Moeda, PerfilPublico, Serie
from .views import interpretar_busca


class CatalogoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("carregar_catalogo", verbosity=0)

    def test_total_igual_ao_pdf(self):
        self.assertEqual(Moeda.objects.count(), 193)
        por_tipo = {
            Serie.Tipo.FAMILIA: 167,
            Serie.Tipo.COMEMORATIVA: 9,
            Serie.Tipo.OLIMPIADA: 17,
        }
        for tipo, total in por_tipo.items():
            self.assertEqual(Moeda.objects.filter(serie__tipo=tipo).count(), total, tipo)

    def test_idempotente(self):
        call_command("carregar_catalogo", verbosity=0)
        self.assertEqual(Moeda.objects.count(), 193)

    def test_furos_e_variantes(self):
        f2 = Serie.objects.get(nome="2ª Família")
        cinquenta = Moeda.objects.filter(serie=f2, denominacao__valor_centavos=50)
        self.assertFalse(cinquenta.filter(ano=1999).exists())
        self.assertFalse(cinquenta.filter(ano=2004).exists())
        self.assertTrue(cinquenta.filter(ano=2019, variante="A").exists())
        um_real = Moeda.objects.filter(serie=f2, denominacao__valor_centavos=100)
        self.assertFalse(um_real.filter(ano__in=[2000, 2001]).exists())
        self.assertEqual(um_real.count(), 27)


class BuscaTests(TestCase):
    def test_interpretacao(self):
        self.assertEqual(interpretar_busca("50 2008")["valores"], {50})
        self.assertEqual(interpretar_busca("1 real 2019")["valores"], {100})
        self.assertEqual(interpretar_busca("1 centavo")["valores"], {1})
        self.assertEqual(interpretar_busca("1 2003")["valores"], {1, 100})
        f = interpretar_busca("5c 2019a")
        self.assertEqual((f["valores"], f["anos"], f["variantes"]), ({5}, {2019}, {"A"}))
        self.assertEqual(interpretar_busca("Natação")["textos"], ["natacao"])


class TelasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("carregar_catalogo", verbosity=0)
        cls.user = User.objects.create_user("rhauan", password="senha-de-teste-123")

    def setUp(self):
        self.client.force_login(self.user)

    def test_exige_login(self):
        self.client.logout()
        r = self.client.get(reverse("inicio"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("account_login"), r["Location"])

    def test_paginas_abrem(self):
        self.assertContains(self.client.get(reverse("inicio")), "193")
        serie = Serie.objects.get(nome="2ª Família")
        self.assertContains(self.client.get(reverse("serie", args=[serie.pk])), "2019A")
        self.assertEqual(self.client.get(reverse("faltando")).status_code, 200)

    def test_ordem_series_inicio(self):
        r = self.client.get(reverse("inicio"))
        secoes = dict(r.context["secoes"])
        nomes_familia = [s.nome for s in secoes["Família"]]
        self.assertEqual(nomes_familia, ["1ª Família", "2ª Família"])
        nomes_olimpiadas = [s.nome for s in secoes["Olimpíadas"]]
        self.assertEqual(nomes_olimpiadas[0], "Olimpíadas 2012 – Entrega da Bandeira")
        self.assertEqual(nomes_olimpiadas[1], "Olimpíadas 2014 – 1ª Série")

    def test_busca(self):
        r = self.client.get(reverse("buscar"), {"q": "50 2008"})
        self.assertContains(r, "2008")
        r = self.client.get(reverse("buscar"), {"q": "natacao"})
        self.assertContains(r, "Natação Paralímpica")
        r = self.client.get(reverse("buscar"), {"q": "xyz 1950"})
        self.assertContains(r, "Nenhuma moeda")

    def test_marcar_e_editar(self):
        m = Moeda.objects.get(serie__nome="2ª Família", denominacao__valor_centavos=50, ano=2008)
        r = self.client.post(reverse("marcar", args=[m.pk]))
        self.assertContains(r, 'hx-swap-oob="true"')
        self.assertContains(r, "chip tenho")
        self.assertEqual(ItemColecao.objects.get(user=self.user, moeda=m).quantidade, 1)

        # segundo toque não zera
        self.client.post(reverse("marcar", args=[m.pk]))
        self.assertEqual(ItemColecao.objects.get(user=self.user, moeda=m).quantidade, 1)

        r = self.client.post(
            reverse("ficha", args=[m.pk]),
            {"quantidade": 3, "estado": "MBC", "observacao": "troco", "adquirida_em": "2026-10-19"},
        )
        self.assertEqual(r["HX-Trigger"], "fechar-ficha")
        item = ItemColecao.objects.get(user=self.user, moeda=m)
        self.assertEqual((item.quantidade, item.estado), (3, "MBC"))

        r = self.client.post(reverse("ficha", args=[m.pk]), {"acao": "remover"})
        self.assertEqual(ItemColecao.objects.get(user=self.user, moeda=m).quantidade, 0)

    def test_ficha_invalida_volta_com_erro(self):
        m = Moeda.objects.first()
        r = self.client.post(reverse("ficha", args=[m.pk]), {"quantidade": -2})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="erro"')


class MultiusuarioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("carregar_catalogo", verbosity=0)
        cls.ana = User.objects.create_user("ana", "ana@ex.com", "senha-de-teste-123")
        cls.beto = User.objects.create_user("beto", "beto@ex.com", "senha-de-teste-123")
        cls.moeda = Moeda.objects.get(serie__nome="2ª Família", denominacao__valor_centavos=10, ano=2010)

    def test_colecoes_separadas(self):
        self.client.force_login(self.ana)
        self.client.post(reverse("marcar", args=[self.moeda.pk]))
        self.assertContains(self.client.get(reverse("inicio")), '<span class="grande">1</span>', html=False)

        self.client.force_login(self.beto)
        self.assertContains(self.client.get(reverse("inicio")), '<span class="grande">0</span>', html=False)
        r = self.client.get(reverse("serie", args=[self.moeda.serie_id]))
        self.assertContains(r, f'id="moeda-{self.moeda.pk}" class="chip"')

    def test_excluir_conta_apaga_colecao(self):
        self.client.force_login(self.ana)
        self.client.post(reverse("marcar", args=[self.moeda.pk]))
        # Confirmação errada
        r = self.client.post(reverse("excluir_conta"), {"confirmacao": "errado", "senha": "senha-de-teste-123"})
        self.assertTrue(User.objects.filter(pk=self.ana.pk).exists())
        # Senha errada
        r = self.client.post(reverse("excluir_conta"), {"confirmacao": "EXCLUIR", "senha": "senha-errada"})
        self.assertTrue(User.objects.filter(pk=self.ana.pk).exists())
        # Correto: apaga
        r = self.client.post(reverse("excluir_conta"), {"confirmacao": "excluir", "senha": "senha-de-teste-123"})
        self.assertRedirects(r, reverse("account_login"), fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(pk=self.ana.pk).exists())
        self.assertFalse(ItemColecao.objects.filter(user_id=self.ana.pk).exists())


class ContasTests(TestCase):
    def test_cadastro_por_email_e_login(self):
        r = self.client.post(
            reverse("account_signup"),
            {"email": "nova@ex.com", "password1": "Moeda-forte-2026", "password2": "Moeda-forte-2026"},
        )
        self.assertEqual(r.status_code, 302)
        self.client.logout()
        r = self.client.post(reverse("account_login"), {"login": "nova@ex.com", "password": "Moeda-forte-2026"})
        self.assertRedirects(r, reverse("inicio"), fetch_redirect_response=False)

    def test_trocar_email_substitui_em_vez_de_acumular(self):
        from allauth.account.models import EmailAddress

        u = User.objects.create_user("ana", "ana@ex.com", "senha-de-teste-123")
        EmailAddress.objects.create(user=u, email="ana@ex.com", primary=True, verified=True)
        self.client.force_login(u)
        for novo in ("novo1@ex.com", "novo2@ex.com"):
            self.client.post(reverse("account_email"), {"action_add": "", "email": novo})
        pendentes = EmailAddress.objects.filter(user=u, verified=False)
        self.assertEqual(pendentes.count(), 1)
        self.assertEqual(pendentes.get().email, "novo2@ex.com")
        self.assertEqual(EmailAddress.objects.filter(user=u).count(), 2)  # atual + 1 pendente

    def test_login_por_usuario_antigo(self):
        User.objects.create_user("rhauan", "", "senha-de-teste-123")
        r = self.client.post(reverse("account_login"), {"login": "rhauan", "password": "senha-de-teste-123"})
        self.assertRedirects(r, reverse("inicio"), fetch_redirect_response=False)

    @override_settings(CADASTRO_ABERTO=False)
    def test_cadastro_fechado(self):
        r = self.client.post(
            reverse("account_signup"),
            {"email": "x@ex.com", "password1": "Moeda-forte-2026", "password2": "Moeda-forte-2026"},
        )
        self.assertFalse(User.objects.filter(email="x@ex.com").exists())

    def test_login_sem_provedores_nao_mostra_botoes(self):
        html = self.client.get(reverse("account_login")).content.decode()
        self.assertNotIn("btn-social", html)

    def test_login_mostra_botoes_dos_provedores_configurados(self):
        apps = [{"client_id": "x", "secret": "y", "key": ""}]
        provedores = {
            "google": {"APPS": apps},
            "microsoft": {"APPS": apps},
            "apple": {"APPS": [{"client_id": "x", "secret": "kid", "key": "team",
                                "settings": {"certificate_key": "k"}}]},
        }
        with override_settings(SOCIALACCOUNT_PROVIDERS=provedores):
            for nome in ["account_login", "account_signup"]:
                html = self.client.get(reverse(nome)).content.decode()
                for rotulo in ["Google", "Apple", "Microsoft"]:
                    self.assertIn(f"Continuar com {rotulo}", html, nome)
                self.assertIn("/contas/microsoft/login/", html)
                self.assertIn("/contas/apple/login/", html)

    def test_telas_publicas(self):
        for nome in ["account_login", "account_signup", "privacidade", "offline", "manifest", "service_worker"]:
            self.assertEqual(self.client.get(reverse(nome)).status_code, 200, nome)
        sw = self.client.get(reverse("service_worker"))
        self.assertEqual(sw["Content-Type"], "application/javascript")
        self.assertIn("showNotification", sw.content.decode())
        man = json.loads(self.client.get(reverse("manifest")).content)
        self.assertEqual(man["display"], "standalone")


class PushTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ana", "ana@ex.com", "senha-de-teste-123")

    def setUp(self):
        self.client.force_login(self.user)

    def test_inscrever_e_cancelar(self):
        dados = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "AAA", "auth": "BBB"}}
        r = self.client.post(reverse("push_inscrever"), json.dumps(dados), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(InscricaoPush.objects.filter(user=self.user).count(), 1)
        r = self.client.post(reverse("push_cancelar"), json.dumps({"endpoint": dados["endpoint"]}), content_type="application/json")
        self.assertEqual(InscricaoPush.objects.count(), 0)

    def test_inscricao_invalida_ou_ssrf(self):
        # JSON vazio
        r = self.client.post(reverse("push_inscrever"), "{}", content_type="application/json")
        self.assertEqual(r.status_code, 400)
        # Endpoint interno / SSRF bloqueado
        dados_ssrf = {"endpoint": "https://192.168.30.6/push", "keys": {"p256dh": "AAA", "auth": "BBB"}}
        r = self.client.post(reverse("push_inscrever"), json.dumps(dados_ssrf), content_type="application/json")
        self.assertEqual(r.status_code, 400)

    @override_settings(VAPID_PUBLIC_KEY="pub", VAPID_PRIVATE_KEY="priv", VAPID_EMAIL="mailto:a@b.c")
    def test_envio_remove_inscricao_expirada(self):
        from pywebpush import WebPushException

        from .push import enviar_aviso

        InscricaoPush.objects.create(user=self.user, endpoint="https://fcm.googleapis.com/ok", p256dh="a", auth="b")
        InscricaoPush.objects.create(user=self.user, endpoint="https://fcm.googleapis.com/velha", p256dh="a", auth="b")
        aviso = Aviso.objects.create(titulo="Moeda nova", texto="1 Real 2026")

        def falso_webpush(subscription_info, **kw):
            if subscription_info["endpoint"].endswith("velha"):
                resp = mock.Mock(status_code=410)
                raise WebPushException("gone", response=resp)
            self.assertEqual(json.loads(kw["data"])["title"], "Moeda nova")
            self.assertEqual(kw["vapid_claims"]["sub"], "mailto:a@b.c")

        with mock.patch("pywebpush.webpush", side_effect=falso_webpush):
            n = enviar_aviso(aviso)
        self.assertEqual(n, 1)
        self.assertEqual(list(InscricaoPush.objects.values_list("endpoint", flat=True)), ["https://fcm.googleapis.com/ok"])

    def test_chaves_vapid_funcionam_com_pywebpush(self):
        from io import StringIO

        from py_vapid import Vapid

        out = StringIO()
        call_command("gerar_chaves_push", stdout=out)
        linhas = dict(l.split("=", 1) for l in out.getvalue().splitlines() if l.startswith("VAPID_"))
        v = Vapid.from_string(linhas["VAPID_PRIVATE_KEY"])
        self.assertIsNotNone(v.private_key)

    def test_novidades_e_conta(self):
        Aviso.objects.create(titulo="Teste de aviso", texto="texto")
        self.assertContains(self.client.get(reverse("novidades")), "Teste de aviso")
        self.assertContains(self.client.get(reverse("conta")), "ana@ex.com")

    def test_aviso_link_validacao(self):
        from django.core.exceptions import ValidationError

        a = Aviso(titulo="Teste", texto="Texto", link="https://site-externo.com")
        with self.assertRaises(ValidationError):
            a.full_clean()
        a_ok = Aviso(titulo="Teste", texto="Texto", link="/serie/1/")
        a_ok.full_clean()

    def test_apoie_pix(self):
        self.assertNotContains(self.client.get(reverse("conta")), "Apoie o projeto")
        self.assertEqual(self.client.get(reverse("apoie")).status_code, 404)
        with override_settings(PIX_CHAVE="chave-pix-teste", PIX_NOME="Fulano", PIX_CIDADE="Sao Paulo"):
            self.assertContains(self.client.get(reverse("conta")), "Apoie o projeto")
            self.assertContains(self.client.get(reverse("inicio")), "Apoie com um Pix")
            resp = self.client.get(reverse("apoie"))
        self.assertContains(resp, "<svg")
        self.assertContains(resp, "br.gov.bcb.pix0115chave-pix-teste")
        self.assertContains(resp, "FULANO")

    def test_crc_do_pix(self):
        from .pix import _crc16, payload_pix

        self.assertEqual(_crc16("123456789"), "29B1")
        codigo = payload_pix("a@b.com", "Fulano", "Sao Paulo")
        self.assertEqual(codigo[-4:], _crc16(codigo[:-4]))


class FotosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("carregar_catalogo", verbosity=0)
        call_command("carregar_fotos", verbosity=0)
        cls.user = User.objects.create_user("rhauan", password="senha-de-teste-123")

    def test_todas_as_moedas_tem_foto_e_arquivo(self):
        from pathlib import Path

        from django.conf import settings

        self.assertFalse(Moeda.objects.filter(foto_cara="").exists())
        self.assertFalse(Moeda.objects.filter(foto_coroa="").exists())
        for caminho in set(Moeda.objects.values_list("foto_cara", flat=True)) | set(
            Moeda.objects.values_list("foto_coroa", flat=True)
        ):
            self.assertTrue((Path(settings.BASE_DIR) / "static" / caminho).exists(), caminho)

    def test_2019a_tem_dica(self):
        m = Moeda.objects.get(serie__nome="2ª Família", denominacao__valor_centavos=5, ano=2019, variante="A")
        self.assertIn("“A”", m.como_identificar)
        comum = Moeda.objects.get(serie__nome="2ª Família", denominacao__valor_centavos=5, ano=2019, variante="")
        self.assertEqual(comum.como_identificar, "")
        self.assertNotEqual(m.foto_coroa, comum.foto_coroa)

    def test_idempotente_e_nao_mexe_na_colecao(self):
        m = Moeda.objects.get(serie__nome="2ª Família", denominacao__valor_centavos=50, ano=2008)
        ItemColecao.objects.create(user=self.user, moeda=m, quantidade=2, estado="SOB", observacao="minha")
        Moeda.objects.filter(pk=m.pk).update(foto_cara="moedas/ajustada.webp")
        call_command("carregar_fotos", verbosity=0)
        m.refresh_from_db()
        self.assertEqual(m.foto_cara, "moedas/ajustada.webp")  # ajuste manual preservado
        call_command("carregar_fotos", "--forcar", verbosity=0)
        m.refresh_from_db()
        self.assertEqual(m.foto_cara, "moedas/f2-50-cara.webp")
        item = ItemColecao.objects.get(user=self.user, moeda=m)
        self.assertEqual((item.quantidade, item.estado, item.observacao), (2, "SOB", "minha"))

    def test_ficha_mostra_fotos(self):
        self.client.force_login(self.user)
        m = Moeda.objects.get(serie__nome="2ª Família", denominacao__valor_centavos=5, ano=2019, variante="A")
        r = self.client.get(reverse("ficha", args=[m.pk]))
        self.assertContains(r, "f2-5A-coroa.webp")
        self.assertContains(r, "Como identificar")


class CompartilharTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("carregar_catalogo", verbosity=0)
        cls.user = User.objects.create_user("rhauan", password="senha-de-teste-123")

    def setUp(self):
        self.client.force_login(self.user)

    def test_faltam_ignora_as_que_tenho(self):
        ItemColecao.objects.create(user=self.user, moeda=Moeda.objects.first(), quantidade=1)
        r = self.client.get(reverse("compartilhar"))
        self.assertContains(r, "(192 de 193)")
        self.assertContains(r, "data-whatsapp")

    def test_por_serie(self):
        serie = Serie.objects.get(nome="2ª Família")
        r = self.client.get(reverse("compartilhar"), {"serie": serie.pk})
        self.assertContains(r, "da série 2ª Família")
        self.assertNotContains(r, "*Olimp")

    def test_repetidas(self):
        moeda = Moeda.objects.first()
        r = self.client.get(reverse("compartilhar"), {"tipo": "repetidas"})
        self.assertContains(r, "Nenhuma moeda repetida")
        ItemColecao.objects.create(user=self.user, moeda=moeda, quantidade=3)
        r = self.client.get(reverse("compartilhar"), {"tipo": "repetidas"})
        self.assertContains(r, f"{moeda.ano_rotulo} +2")

    def test_exige_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("compartilhar")).status_code, 302)


class ColecaoPublicaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("carregar_catalogo", verbosity=0)
        cls.user = User.objects.create_user("rhauan", "segredo@ex.com", "senha-de-teste-123", first_name="Rhauan")

    def ativar(self):
        self.client.force_login(self.user)
        self.client.get(reverse("conta"))  # cria o perfil
        self.client.post(reverse("compartilhar_colecao"), {"acao": "ativar", "nome": "Rhauan"})
        self.client.logout()
        return PerfilPublico.objects.get(user=self.user)

    def test_desligado_por_padrao(self):
        self.client.force_login(self.user)
        self.client.get(reverse("conta"))
        perfil = PerfilPublico.objects.get(user=self.user)
        self.assertFalse(perfil.ativo)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("colecao_publica", args=[perfil.token])).status_code, 404)

    def test_pagina_publica_sem_login_e_sem_dados_pessoais(self):
        ItemColecao.objects.create(
            user=self.user, moeda=Moeda.objects.first(), quantidade=2, estado="FC", observacao="achei na padaria"
        )
        perfil = self.ativar()
        r = self.client.get(reverse("colecao_publica", args=[perfil.token]))
        self.assertContains(r, "Coleção de Rhauan")
        self.assertContains(r, "1</span>")
        for proibido in ("segredo@ex.com", "achei na padaria", "FC"):
            self.assertNotContains(r, proibido)
        self.assertIn("noindex", r["X-Robots-Tag"])
        self.assertEqual(self.client.get(reverse("colecao_publica", args=[perfil.token]), {"ver": "repetidas"}).status_code, 200)

    def test_novo_link_invalida_o_anterior_e_desativar_fecha(self):
        perfil = self.ativar()
        antigo = perfil.token
        self.client.force_login(self.user)
        self.client.post(reverse("compartilhar_colecao"), {"acao": "novo_link"})
        self.client.logout()
        self.assertEqual(self.client.get(reverse("colecao_publica", args=[antigo])).status_code, 404)
        perfil.refresh_from_db()
        self.assertEqual(self.client.get(reverse("colecao_publica", args=[perfil.token])).status_code, 200)
        self.client.force_login(self.user)
        self.client.post(reverse("compartilhar_colecao"), {"acao": "desativar"})
        self.client.logout()
        self.assertEqual(self.client.get(reverse("colecao_publica", args=[perfil.token])).status_code, 404)

    def test_exige_login_para_configurar(self):
        r = self.client.post(reverse("compartilhar_colecao"), {"acao": "ativar"})
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("account_login"), r["Location"])

    def test_compartilhar_estado_opcional(self):
        m = Moeda.objects.first()
        ItemColecao.objects.create(user=self.user, moeda=m, quantidade=1, estado="SOB")
        perfil = self.ativar()
        self.assertFalse(perfil.compartilhar_estado)
        r = self.client.get(reverse("colecao_publica", args=[perfil.token]))
        self.assertNotContains(r, '<span class="est">SOB</span>')

        # Ativa compartilhamento do estado
        self.client.force_login(self.user)
        self.client.post(
            reverse("compartilhar_colecao"),
            {"acao": "salvar", "nome": "Rhauan", "compartilhar_estado": "1"},
        )
        self.client.logout()
        perfil.refresh_from_db()
        self.assertTrue(perfil.compartilhar_estado)

        r = self.client.get(reverse("colecao_publica", args=[perfil.token]))
        self.assertContains(r, '<span class="est">SOB</span>')

        # Desativa compartilhamento do estado
        self.client.force_login(self.user)
        self.client.post(
            reverse("compartilhar_colecao"),
            {"acao": "salvar", "nome": "Rhauan"},
        )
        self.client.logout()
        perfil.refresh_from_db()
        self.assertFalse(perfil.compartilhar_estado)

        r = self.client.get(reverse("colecao_publica", args=[perfil.token]))
        self.assertNotContains(r, '<span class="est">SOB</span>')



class SaudeTests(TestCase):
    @override_settings(ALLOWED_HOSTS=["moedas.exemplo.com"])
    def test_responde_ok_mesmo_com_host_fora_do_allowed_hosts(self):
        resp = self.client.get("/saude/", HTTP_HOST="localhost")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"ok")

    def test_banco_fora_do_ar_retorna_503(self):
        with mock.patch("colecao.middleware.connection.cursor", side_effect=Exception("sem banco")):
            resp = self.client.get("/saude/")
        self.assertEqual(resp.status_code, 503)
