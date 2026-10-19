"""Gera _fotos_rascunho/conferencia.html (abre direto no navegador)."""
import html, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django; django.setup()
from django.core.management import call_command
from django.db import connection
from colecao.models import Moeda
from colecao.fotos import chave_do_desenho, carregar_mapa

AQUI = os.path.dirname(os.path.abspath(__file__))
manifest = json.load(open(os.path.join(AQUI, "manifest.json"), encoding="utf-8"))
pagina = {v["arquivo"]: v["pagina"] for v in manifest.values()}
mapa = carregar_mapa()
nome_db = connection.creation.create_test_db(verbosity=0)
try:
    call_command("carregar_catalogo", verbosity=0)
    uso = {}
    for m in Moeda.objects.select_related("serie", "denominacao"):
        uso.setdefault(chave_do_desenho(m), []).append(f"{m.denominacao} {m.ano_rotulo}" + (f" – {m.descricao}" if m.descricao else ""))
finally:
    connection.creation.destroy_test_db(nome_db, verbosity=0)

linhas = []
for chave, d in mapa.items():
    fontes = " · ".join(f'<a href="{html.escape(pagina[a])}">{html.escape(a)}</a>' for a in d["origem"])
    moedas = uso.get(chave, [])
    resumo = f"{len(moedas)} moeda(s): " + ", ".join(m.split(" ", 2)[-1] if False else m for m in moedas[:6]) + ("…" if len(moedas) > 6 else "")
    linhas.append(f"""<section><h3>{html.escape(chave)}</h3>
<div class="par"><figure><img src="../static/{d['cara']}"><figcaption>cara</figcaption></figure>
<figure><img src="../static/{d['coroa']}"><figcaption>coroa</figcaption></figure></div>
<p class="uso">{html.escape(resumo)}</p><p class="fonte">{fontes}<br>{html.escape(d['credito'])}</p></section>""")
open(os.path.join(AQUI, "conferencia.html"), "w", encoding="utf-8").write(f"""<!doctype html><html lang="pt-br"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conferência das fotos</title><style>
body{{font:15px system-ui;margin:16px;background:#faf7f2;color:#2b2620}}
.grade{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}}
section{{background:#fff;border-radius:14px;padding:12px;box-shadow:0 1px 3px #0002}}
h3{{margin:0 0 8px}} .par{{display:flex;gap:8px}} figure{{margin:0;flex:1;text-align:center}}
img{{width:100%;aspect-ratio:1;object-fit:contain;background:#ececec;border-radius:10px}}
figcaption{{font-size:12px;color:#6b6258}} .uso{{margin:8px 0 4px}} .fonte{{font-size:11px;color:#6b6258;margin:0}}
</style><h1>Conferência das fotos ({len(mapa)} desenhos → 193 moedas)</h1>
<p>Cara = lado do retrato/tema; coroa = lado do valor. Se algo estiver trocado ou errado, me diga a chave (ex.: <b>f2-25</b>).</p>
<div class="grade">{''.join(linhas)}</div></html>""")
print("ok", len(mapa))
