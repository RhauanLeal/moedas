{% load static %}/* Service worker — Moedas do Real ({{ versao }}) */
const VERSAO = "{{ versao }}";
const ESTATICOS = "estaticos-" + VERSAO;
const PAGINAS = "paginas";
const OFFLINE = "{{ precache.0 }}";
const PRECACHE = [{% for url in precache %}"{{ url }}"{% if not forloop.last %}, {% endif %}{% endfor %}];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(ESTATICOS).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((nomes) => Promise.all(
        nomes.filter((n) => n.startsWith("estaticos-") && n !== ESTATICOS).map((n) => caches.delete(n))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/admin/") || url.pathname.startsWith("/contas/")) return;

  // Arquivos estáticos (têm hash no nome): cache primeiro
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((resp) => {
        if (resp.ok) { const copia = resp.clone(); caches.open(ESTATICOS).then((c) => c.put(req, copia)); }
        return resp;
      }))
    );
    return;
  }

  // Páginas: rede primeiro; sem internet, mostra a última versão guardada
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((resp) => {
          if (resp.ok && !resp.redirected) {
            const copia = resp.clone();
            caches.open(PAGINAS).then((c) => c.put(req, copia));
          }
          return resp;
        })
        .catch(() => caches.match(req).then((hit) => hit || caches.match(OFFLINE)))
    );
  }
});

// ---------- notificações ----------
self.addEventListener("push", (event) => {
  let dados = {};
  try { dados = event.data ? event.data.json() : {}; } catch (e) { dados = { body: event.data && event.data.text() }; }
  event.waitUntil(
    self.registration.showNotification(dados.title || "Moedas do Real", {
      body: dados.body || "",
      icon: "{% static 'icones/icone-192.png' %}",
      badge: "{% static 'icones/badge-96.png' %}",
      data: { url: dados.url || "/novidades/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const destino = new URL(event.notification.data.url, location.origin).href;
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((janelas) => {
      for (const j of janelas) {
        if ("focus" in j) { j.navigate(destino); return j.focus(); }
      }
      return clients.openWindow(destino);
    })
  );
});
