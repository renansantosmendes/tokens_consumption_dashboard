(function () {
  "use strict";

  var listBox = document.getElementById("list");
  var detailBox = document.getElementById("detail");
  var userSelect = document.getElementById("user");
  var daysSelect = document.getElementById("days");
  var limitSelect = document.getElementById("limit");
  var requestId = 0;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function formatTime(iso) {
    if (!iso) return "—";
    return new Date(iso).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" });
  }

  function fillUsers() {
    var option = el("option", "", "Todos os alunos");
    option.value = "";
    userSelect.appendChild(option);
    var users = (window.DASHBOARD_DATA && window.DASHBOARD_DATA.users) || [];
    users.forEach(function (user) {
      var item = el("option", "", (user.name || "Sem nome") + " · " + user.user_id);
      item.value = user.user_id;
      userSelect.appendChild(item);
    });
  }

  function request(path) {
    return fetch(path, { headers: { Accept: "application/json" } }).then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) throw new Error(body.error || "Erro ao consultar o servidor.");
        return body;
      });
    });
  }

  function renderList(rows) {
    listBox.replaceChildren();
    if (!rows.length) {
      listBox.appendChild(el("p", "status", "Nenhuma conversa encontrada neste filtro."));
      return;
    }
    rows.forEach(function (row) {
      var button = el("button", "item");
      button.type = "button";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", "false");
      button.dataset.id = row.id;
      var who = row.name ? row.name + " · " + row.user_id : (row.user_id || "sem usuário");
      button.appendChild(el("div", "meta", formatTime(row.time) + " · " + who + " · " + (row.model || "modelo não informado")));
      button.appendChild(el("div", "q", row.question || "(sem texto de pergunta)"));
      button.appendChild(el("div", "a", row.answer ? "→ " + row.answer : "(sem resposta)"));
      button.addEventListener("click", function () { openConversation(row.id, button); });
      listBox.appendChild(button);
    });
  }

  function renderDetail(conversation) {
    detailBox.replaceChildren();
    if (!conversation.messages.length) {
      detailBox.appendChild(el("p", "status", "Esta chamada não tem mensagens registradas."));
    }
    conversation.messages.forEach(function (message) {
      var box = el("div", "msg " + (message.role || "system"));
      box.appendChild(el("div", "role", message.role || "mensagem"));
      box.appendChild(document.createTextNode(message.content));
      detailBox.appendChild(box);
    });
    var answer = el("div", "msg assistant");
    answer.appendChild(el("div", "role", "resposta do modelo"));
    answer.appendChild(document.createTextNode(conversation.answer || "(vazia)"));
    detailBox.appendChild(answer);
  }

  function loadList() {
    var current = ++requestId;
    listBox.replaceChildren(el("p", "status", "Consultando o Langfuse…"));
    var params = new URLSearchParams({
      days: daysSelect.value,
      limit: limitSelect.value,
    });
    if (userSelect.value) params.set("user", userSelect.value);
    request("/api/conversations?" + params.toString()).then(function (rows) {
      if (current === requestId) renderList(rows);
    }, function (error) {
      if (current === requestId) listBox.replaceChildren(el("p", "error", error.message));
    });
  }

  function openConversation(id, button) {
    Array.prototype.forEach.call(listBox.querySelectorAll(".item"), function (item) {
      item.setAttribute("aria-selected", item === button ? "true" : "false");
    });
    detailBox.replaceChildren(el("p", "status", "Carregando a conversa…"));
    request("/api/conversation?id=" + encodeURIComponent(id)).then(renderDetail, function (error) {
      detailBox.replaceChildren(el("p", "error", error.message));
    });
  }

  fillUsers();
  document.getElementById("reload").addEventListener("click", loadList);
  userSelect.addEventListener("change", loadList);
  daysSelect.addEventListener("change", loadList);
  limitSelect.addEventListener("change", loadList);
  loadList();
})();
