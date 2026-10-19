"""Escolhe, recorta e converte as fotos (rascunho; não faz parte do app).

Uso (na pasta do projeto):  python _fotos_rascunho/montar_fotos.py
Lê _fotos_rascunho/manifest.json + ordem.json e gera static/moedas/*.webp + colecao/fotos.json.
"""
import json, os, re, time, urllib.parse, urllib.request
from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SAIDA = os.path.join(RAIZ, "static", "moedas")
UA = {"User-Agent": "MoedasRealApp/1.0 (rhauan@gmail.com)"}
manifest = json.load(open(os.path.join(AQUI, "manifest.json"), encoding="utf-8"))
ordem = json.load(open(os.path.join(AQUI, "ordem.json")))
por_arquivo = {v["arquivo"]: (t, v) for t, v in manifest.items()}

# spec: indice (foto inteira) ou (indice, "esq"/"dir") para fotos com duas moedas.
# Convenção: cara = lado do retrato/tema; coroa = lado do valor.
E = "esq"
DESENHOS = {
    "f1-1": (36, 37), "f1-5": (100, 101), "f1-10": (18, 19), "f1-25": (82, 83), "f1-50": (95, 96), "f1-100": (131, 126),
    "f2-1": (129, 128), "f2-5": (102, 103), "f2-10": (20, 21), "f2-25": (84, 85), "f2-50": (97, 98), "f2-100": (38, 39),
    "f2-5A": (102, 93), "f2-50A": (97, 94),
    "com-fao10": (32, (31, E)), "com-fao25": (92, (91, E)), "com-dh1998": (3, 5), "com-jk2002": (125, (81, E)),
    "com-bc2005": (124, (116, E)), "com-bc2015": (42, (41, E)), "com-25anos": (9, 10), "com-30anos": (12, 13),
    "com-60anos": (15, 16),
    "oli-entrega-da-bandeira": (80, (79, E)), "oli-atletismo": (34, (33, E)), "oli-paratriatlo": (64, (63, E)),
    "oli-golf": (50, (49, E)), "oli-natacao": (72, (71, E)), "oli-basquete": (46, (45, E)),
    "oli-paracanoagem": (56, (55, E)), "oli-vela": (68, (67, E)), "oli-rugby": (66, (65, E)),
    "oli-futebol": (70, (69, E)), "oli-volei": (74, (73, E)), "oli-atletismo-paralimpico": (58, (57, E)),
    "oli-judo": (52, (51, E)), "oli-natacao-paralimpica": (62, (61, E)), "oli-boxe": (48, (47, E)),
    "oli-mascote-olimpico": (54, (53, E)), "oli-mascote-paralimpico": (60, (59, E)),
}


def baixar_hd(arquivo):
    """Baixa a versão grande (até 1000 px) do arquivo da Commons."""
    pasta = os.path.join(AQUI, "originais_hd"); os.makedirs(pasta, exist_ok=True)
    dest = os.path.join(pasta, arquivo)
    if os.path.exists(dest):
        return dest
    titulo, _ = por_arquivo[arquivo]
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "titles": titulo, "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 1000, "format": "json"})
    d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))
    ii = next(iter(d["query"]["pages"].values()))["imageinfo"][0]
    fonte = ii.get("thumburl") or ii["url"]
    for _ in range(3):
        try:
            open(dest, "wb").write(urllib.request.urlopen(urllib.request.Request(fonte, headers=UA), timeout=60).read()); break
        except Exception:
            time.sleep(3)
    time.sleep(0.4)
    return dest


def mascara(im):
    """Retorna (imagem RGBA, função fundo(x,y)->bool) separando moeda do fundo."""
    im = im.convert("RGBA")
    a = im.getchannel("A")
    if a.getextrema()[0] < 250:  # fundo transparente
        return im, a.point(lambda v: 255 if v > 16 else 0)
    w, h = im.size
    cantos = [im.getpixel(p)[:3] for p in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3))]
    bg = tuple(sum(c[i] for c in cantos) // 4 for i in range(3))
    rgb = im.convert("RGB")
    dif = Image.new("L", im.size)
    dif.putdata([255 if max(abs(p[i] - bg[i]) for i in range(3)) > 40 else 0 for p in rgb.getdata()])
    return im, dif


def quadrado(im, margem=0.04, lado=480):
    w, h = im.size; m = max(w, h); pad = int(m * margem)
    fundo = Image.new("RGBA", (m + 2 * pad, m + 2 * pad), (0, 0, 0, 0))
    fundo.alpha_composite(im, ((m + 2 * pad - w) // 2, (m + 2 * pad - h) // 2))
    return fundo.resize((lado, lado), Image.LANCZOS)


def recortar(im, mask, caixa=None):
    bbox = mask.crop(caixa).getbbox() if caixa else mask.getbbox()
    if caixa:
        bbox = (bbox[0] + caixa[0], bbox[1] + caixa[1], bbox[2] + caixa[0], bbox[3] + caixa[1])
    return im.crop(bbox), mask.crop(bbox)


def processar(spec, saida):
    idx, lado = (spec, None) if isinstance(spec, int) else spec
    arquivo = ordem[idx]
    im = Image.open(baixar_hd(arquivo))
    im, mask = mascara(im)
    transparente = im.getchannel("A").getextrema()[0] < 250
    if lado:  # duas moedas: acha a maior faixa vazia entre elas
        w, h = im.size
        cols = [mask.crop((x, 0, x + 1, h)).getbbox() is not None for x in range(w)]
        melhor, atual, ini = (0, 0), 0, 0
        ocup = [x for x, c in enumerate(cols) if c]
        for x, ocupado in enumerate(cols):
            if x < ocup[0] or x > ocup[-1]:  # ignora as margens
                continue
            if not ocupado:
                if atual == 0: ini = x
                atual += 1
                if atual > melhor[0]: melhor = (atual, ini)
            else:
                atual = 0
        corte = melhor[1] + melhor[0] // 2 if melhor[0] > 3 else w // 2  # moedas coladas: corta no meio
        caixa = (0, 0, corte, h) if lado == "esq" else (corte, 0, w, h)
        im2, m2 = recortar(im, mask, caixa)
        im = im2
    elif transparente:
        im, _ = recortar(im, mask)
    else:  # foto retangular com fundo: recorte central quadrado
        w, h = im.size; m = min(w, h)
        im = im.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m)).resize((480, 480), Image.LANCZOS)
        im.save(saida, "WEBP", quality=84, method=6); return arquivo
    quadrado(im).save(saida, "WEBP", quality=84, method=6)
    return arquivo


def credito(arquivos):
    partes = []
    for a in dict.fromkeys(arquivos):
        _, v = por_arquivo[a]
        autor = re.sub(r"\s+", " ", v["autor"]).strip()[:50] or "autor desconhecido"
        item = f"{autor} ({v['licenca']})"
        if item not in partes: partes.append(item)
    return "Wikimedia Commons — " + "; ".join(partes)


if __name__ == "__main__":
    os.makedirs(SAIDA, exist_ok=True)
    fotos = {}
    for chave, (cara, coroa) in DESENHOS.items():
        usados = []
        for lado_nome, spec in (("cara", cara), ("coroa", coroa)):
            usados.append(processar(spec, os.path.join(SAIDA, f"{chave}-{lado_nome}.webp")))
        fotos[chave] = {"cara": f"moedas/{chave}-cara.webp", "coroa": f"moedas/{chave}-coroa.webp", "credito": credito(usados),
                        "origem": usados}
        print("ok", chave)
    json.dump(fotos, open(os.path.join(RAIZ, "colecao", "fotos.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
