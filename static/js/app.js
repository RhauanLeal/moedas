/* Moedas do Real — comportamento da interface (painel da ficha, PWA e notificações). */
(function () {
  "use strict";

  function csrf() {
    try { return JSON.parse(document.body.getAttribute("hx-headers"))["X-CSRFToken"]; }
    catch (e) { return ""; }
  }

  function postJSON(url, dados) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      credentials: "same-origin",
      body: JSON.stringify(dados),
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var body = document.body;

    // ---------- painel da ficha ----------
    var dlg = document.getElementById("ficha");
    var conteudo = document.getElementById("ficha-conteudo");
    if (dlg && conteudo) {
      body.addEventListener("htmx:afterSwap", function (e) {
        if (e.detail.target === conteudo && conteudo.innerHTML.trim() && !dlg.open) dlg.showModal();
      });
      body.addEventListener("fechar-ficha", function () { dlg.close(); });
      dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
      dlg.addEventListener("close", function () { conteudo.innerHTML = ""; });
    }

    // ---------- modo edição ----------
    // Ao abrir, a coleção é só para visualizar; toques nas moedas só valem com a edição ligada.
    var btnEditar = document.querySelector("[data-editar]");
    function definirEdicao(ligada) {
      body.classList.toggle("editando", ligada);
      if (btnEditar) {
        btnEditar.textContent = ligada ? "Concluir" : "Editar";
        btnEditar.setAttribute("aria-pressed", ligada ? "true" : "false");
      }
    }
    if (btnEditar) btnEditar.addEventListener("click", function () {
      definirEdicao(!body.classList.contains("editando"));
    });
    // Fase de captura: barra o clique antes de o HTMX marcar a moeda ou abrir a ficha
    document.addEventListener("click", function (e) {
      if (body.classList.contains("editando")) return;
      var chip = e.target.closest(".chip");
      if (chip) { e.preventDefault(); e.stopImmediatePropagation(); }
    }, true);

    // Botões − / + da quantidade
    body.addEventListener("click", function (e) {
      var b = e.target.closest("[data-delta]");
      if (!b) return;
      var input = document.getElementById(b.dataset.alvo);
      input.value = Math.max(0, (parseInt(input.value, 10) || 0) + parseInt(b.dataset.delta, 10));
    });

    // Mensagens (ex.: "Você entrou como…") somem sozinhas
    document.querySelectorAll(".aviso-flash").forEach(function (el) {
      setTimeout(function () { el.classList.add("sumindo"); }, 3500);
      setTimeout(function () { el.remove(); }, 4200);
    });

    // ---------- PWA ----------
    var logado = body.dataset.logado === "1";
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
      // Ao sair da conta, apaga as páginas guardadas para uso offline
      if (!logado && window.caches) caches.delete("paginas");
    }

    // Botão "Instalar app" (Android/Chrome)
    var pedidoInstalacao = null;
    var botoesInstalar = document.querySelectorAll("[data-instalar]");
    window.addEventListener("beforeinstallprompt", function (e) {
      e.preventDefault();
      pedidoInstalacao = e;
      botoesInstalar.forEach(function (b) { b.hidden = false; });
    });
    botoesInstalar.forEach(function (b) {
      b.addEventListener("click", function () {
        if (!pedidoInstalacao) return;
        pedidoInstalacao.prompt();
        pedidoInstalacao.userChoice.finally(function () {
          pedidoInstalacao = null;
          botoesInstalar.forEach(function (x) { x.hidden = true; });
        });
      });
    });
    var ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
    var instalado = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;
    document.querySelectorAll("[data-dica-ios]").forEach(function (el) { el.hidden = !(ios && !instalado); });

    // ---------- notificações ----------
    var caixa = document.getElementById("notificacoes");
    if (caixa) iniciarNotificacoes(caixa, ios, instalado);
  });

  function base64ParaBytes(b64) {
    var pad = "=".repeat((4 - (b64.length % 4)) % 4);
    var raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
    var arr = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
    return arr;
  }

  function iniciarNotificacoes(caixa, ios, instalado) {
    var chave = caixa.dataset.vapid;
    var estado = caixa.querySelector("[data-estado]");
    var botao = caixa.querySelector("button");

    function mostrar(texto, rotuloBotao) {
      estado.textContent = texto;
      if (rotuloBotao) { botao.textContent = rotuloBotao; botao.hidden = false; }
      else { botao.hidden = true; }
    }

    if (!chave) return mostrar("As notificações ainda não foram configuradas no servidor.");
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
      if (ios && !instalado) return mostrar("No iPhone, primeiro adicione o app à tela de início (Compartilhar › Adicionar à Tela de Início) e abra por lá.");
      return mostrar("Este navegador não suporta notificações.");
    }
    if (Notification.permission === "denied") {
      return mostrar("As notificações estão bloqueadas. Libere nas configurações do navegador para este site.");
    }

    navigator.serviceWorker.ready.then(function (reg) {
      function atualizar() {
        return reg.pushManager.getSubscription().then(function (sub) {
          if (sub) mostrar("Ativadas neste aparelho. Você será avisado quando sair moeda nova.", "Desativar");
          else mostrar("Receba um aviso quando sair moeda nova ou houver novidade.", "Ativar notificações");
          return sub;
        });
      }

      botao.addEventListener("click", function () {
        botao.disabled = true;
        reg.pushManager.getSubscription().then(function (sub) {
          if (sub) {
            return postJSON(caixa.dataset.cancelar, { endpoint: sub.endpoint }).then(function () {
              return sub.unsubscribe();
            });
          }
          return Notification.requestPermission().then(function (perm) {
            if (perm !== "granted") return;
            return reg.pushManager
              .subscribe({ userVisibleOnly: true, applicationServerKey: base64ParaBytes(chave) })
              .then(function (nova) { return postJSON(caixa.dataset.inscrever, nova.toJSON()); });
          });
        })
          .catch(function () { mostrar("Não foi possível alterar as notificações. Tente de novo."); })
          .finally(function () { botao.disabled = false; atualizar(); });
      });

      atualizar();
    });
  }
})();
