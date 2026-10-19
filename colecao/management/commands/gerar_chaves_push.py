"""Gera o par de chaves VAPID usado nas notificações.

    python manage.py gerar_chaves_push

Copie as duas linhas para o .env. Gere UMA vez só: se trocar as chaves,
quem já ativou as notificações precisa ativar de novo.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def b64url(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


class Command(BaseCommand):
    help = "Gera VAPID_PUBLIC_KEY e VAPID_PRIVATE_KEY para as notificações."

    def handle(self, *args, **opts):
        chave = ec.generate_private_key(ec.SECP256R1())
        privada = chave.private_numbers().private_value.to_bytes(32, "big")
        publica = chave.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.stdout.write("Copie para o .env:\n")
        self.stdout.write(f"VAPID_PUBLIC_KEY={b64url(publica)}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={b64url(privada)}")
