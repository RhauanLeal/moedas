"""Pix "copia e cola" (BR Code estático) e QR Code em SVG."""
import io
import unicodedata

import segno


def _campo(id_, valor):
    return f"{id_}{len(valor):02d}{valor}"


def _crc16(texto):
    crc = 0xFFFF
    for byte in texto.encode("ascii"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def _ascii(texto, limite):
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.upper()[:limite]


def payload_pix(chave, nome, cidade):
    """Monta o código Pix estático (sem valor: quem paga digita o quanto quiser)."""
    conta = _campo("00", "br.gov.bcb.pix") + _campo("01", chave)
    corpo = (
        _campo("00", "01")
        + _campo("26", conta)
        + _campo("52", "0000")
        + _campo("53", "986")
        + _campo("58", "BR")
        + _campo("59", _ascii(nome, 25) or "NAO INFORMADO")
        + _campo("60", _ascii(cidade, 15) or "BRASIL")
        + _campo("62", _campo("05", "***"))
        + "6304"
    )
    return corpo + _crc16(corpo)


def qr_svg(texto):
    saida = io.BytesIO()
    segno.make(texto, error="m").save(saida, kind="svg", scale=1, border=2, omitsize=True, xmldecl=False, svgns=True, nl=False, dark="#000", light="#fff")
    return saida.getvalue().decode()
