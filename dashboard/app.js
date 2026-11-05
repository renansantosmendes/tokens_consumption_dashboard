(function () {
  "use strict";

  var data = window.DASHBOARD_DATA;
  var brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  var integer = new Intl.NumberFormat("pt-BR");
  var PALETTE = ["#6ea8ff", "#34d399", "#fbbf24", "#f472b6", "#a78bfa", "#f87171", "#22d3ee", "#94a3b8"];

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function formatMs(ms) {
    if (ms === null || ms === undefined) return "—";
    if (ms < 1000) return Math.round(ms) + " ms";
    return (ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " s";
  }

  function formatDate(iso) {
    var parts = iso.split("-");
    return parts[2] + "/" + parts[1] + "/" + parts[0];
  }

  function renderHeader() {
    document.getElementById("window").textContent =
      "Janela: " + formatDate(data.window.start) + " a " + formatDate(data.window.end) +
      " · Fontes: " + (data.sources || []).join(", ") +
      " · Dólar PTAX de venda: R$ " + data.exchange.usd_brl.toLocaleString("pt-BR", { minimumFractionDigits: 4 });
    document.getElementById("generated").textContent = "Dados gerados em " + data.generated_at.replace("T", " ").replace("Z", " UTC");
  }

  function renderKpis() {
    var totals = data.totals;
    var cards = [
      ["Custo no período", brl.format(totals.cost_brl), "US$ " + totals.cost_usd.toFixed(4)],
      ["Tokens consumidos", integer.format(totals.tokens), "entrada e saída"],
      ["Chamadas ao modelo", integer.format(totals.calls), "generations registradas"],
      ["Latência mediana", formatMs(totals.p50_ms), "por operação do agente"],
    ];
    var box = document.getElementById("kpis");
    cards.forEach(function (card) {
      var item = el("div", { class: "kpi" });
      item.appendChild(el("div", { class: "label" }, card[0]));
      item.appendChild(el("div", { class: "value" }, card[1]));
      item.appendChild(el("div", { class: "hint" }, card[2]));
      box.appendChild(item);
    });
  }

  function renderDaily() {
    if (!window.Chart) return;
    var labels = data.daily.map(function (day) { return formatDate(day.date); });
    new Chart(document.getElementById("dailyChart"), {
      data: {
        labels: labels,
        datasets: [
          { type: "bar", label: "Custo (R$)", data: data.daily.map(function (d) { return d.cost_brl; }),
            backgroundColor: "rgba(110,168,255,0.7)", yAxisID: "cost", order: 2 },
          { type: "line", label: "Tokens", data: data.daily.map(function (d) { return d.tokens; }),
            borderColor: "#34d399", backgroundColor: "#34d399", tension: 0.3, yAxisID: "tokens", order: 1 },
        ],
      },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          cost: { position: "left", ticks: { callback: function (v) { return brl.format(v); } } },
          tokens: { position: "right", grid: { drawOnChartArea: false }, ticks: { callback: function (v) { return integer.format(v); } } },
        },
        plugins: { legend: { labels: { color: "#e6eaf5" } } },
      },
    });
  }

  function renderModels() {
    var models = data.models;
    if (window.Chart) new Chart(document.getElementById("modelChart"), {
      type: "doughnut",
      data: {
        labels: models.map(function (m) { return m.model; }),
        datasets: [{ data: models.map(function (m) { return m.cost_brl; }),
          backgroundColor: models.map(function (_m, i) { return PALETTE[i % PALETTE.length]; }) }],
      },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { position: "bottom", labels: { color: "#e6eaf5" } } },
      },
    });
    var table = document.getElementById("modelTable");
    var head = el("tr");
    ["Modelo", "Custo", "Tokens", "Chamadas"].forEach(function (title, index) {
      head.appendChild(el("th", index ? { class: "num" } : {}, title));
    });
    table.appendChild(el("thead")).appendChild(head);
    var body = el("tbody");
    models.forEach(function (m) {
      var row = el("tr");
      row.appendChild(el("td", {}, m.model));
      row.appendChild(el("td", { class: "num" }, brl.format(m.cost_brl)));
      row.appendChild(el("td", { class: "num" }, integer.format(m.tokens)));
      row.appendChild(el("td", { class: "num" }, integer.format(m.calls)));
      body.appendChild(row);
    });
    table.appendChild(body);
  }

  function renderUsers() {
    var box = document.getElementById("users");
    if (!data.user_tracking) {
      box.appendChild(el("div", { class: "notice" },
        "Ainda não há dados de usuário. Os traces do agente não trazem o usuário, então o Langfuse " +
        "não consegue agrupar o gasto por pessoa. Para ativar esta seção, o agente precisa enviar o " +
        "id do usuário autenticado ao Langfuse em cada chamada (metadata langfuse_user_id)."));
      return;
    }
    var max = Math.max.apply(null, data.users.map(function (u) { return u.tokens; })) || 1;
    var table = el("table");
    var head = el("tr");
    ["Aluno", "Tokens", "", "Custo"].forEach(function (title, index) {
      head.appendChild(el("th", index ? { class: "num" } : {}, title));
    });
    table.appendChild(el("thead")).appendChild(head);
    var body = el("tbody");
    data.users.forEach(function (u) {
      var row = el("tr");
      var who = u.name ? u.name + " · " + u.user_id : u.user_id;
      row.appendChild(el("td", {}, who));
      row.appendChild(el("td", { class: "num" }, integer.format(u.tokens)));
      var barCell = el("td");
      var bar = el("div", { class: "bar" });
      bar.appendChild(el("span", { style: "width:" + (u.tokens / max * 100).toFixed(1) + "%" }));
      barCell.appendChild(bar);
      row.appendChild(barCell);
      row.appendChild(el("td", { class: "num" }, brl.format(u.cost_brl)));
      body.appendChild(row);
    });
    table.appendChild(body);
    box.appendChild(table);
  }

  function renderOperations() {
    var ops = data.operations;
    var box = document.getElementById("operations");
    var max = Math.max.apply(null, ops.map(function (o) { return o.p95_ms || 0; })) || 1;
    var table = el("table");
    var head = el("tr");
    ["Operação", "Chamadas", "Mediana", "p95", ""].forEach(function (title, index) {
      head.appendChild(el("th", index ? { class: "num" } : {}, title));
    });
    table.appendChild(el("thead")).appendChild(head);
    var body = el("tbody");
    ops.forEach(function (o) {
      var row = el("tr");
      row.appendChild(el("td", {}, o.name));
      row.appendChild(el("td", { class: "num" }, integer.format(o.calls)));
      row.appendChild(el("td", { class: "num" }, formatMs(o.p50_ms)));
      row.appendChild(el("td", { class: "num" }, formatMs(o.p95_ms)));
      var barCell = el("td");
      var bar = el("div", { class: "bar" });
      bar.appendChild(el("span", { style: "width:" + (((o.p95_ms || 0) / max) * 100).toFixed(1) + "%;background:#fbbf24" }));
      barCell.appendChild(bar);
      row.appendChild(barCell);
      body.appendChild(row);
    });
    table.appendChild(body);
    box.appendChild(table);
  }

  if (!data) {
    document.querySelector("main").insertBefore(
      el("div", { class: "notice" }, "Arquivo data.js não encontrado. Rode o coletor: python -m dashboard.build"),
      document.querySelector("main").firstChild
    );
    return;
  }
  renderHeader();
  renderKpis();
  renderDaily();
  renderModels();
  renderUsers();
  renderOperations();
})();
