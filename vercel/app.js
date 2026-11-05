(function () {
  "use strict";

  var data = window.VERCEL_DATA;
  var money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD" });
  var integer = new Intl.NumberFormat("pt-BR");

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function formatDate(iso) {
    if (!iso) return "—";
    return new Date(iso).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" });
  }

  function formatShortDate(day) {
    var parts = day.split("-");
    return parts[2] + "/" + parts[1];
  }

  function formatSeconds(value) {
    if (value === null || value === undefined) return "—";
    return value.toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " s";
  }

  function stateBadge(state) {
    var kind = state === "READY" ? "ok" : (state === "ERROR" || state === "CANCELED") ? "fail" : state ? "run" : "";
    return el("span", { class: "badge " + kind }, state || "sem deploy");
  }

  function table(headers, rows, numericColumns) {
    var node = el("table");
    var head = el("tr");
    headers.forEach(function (title, index) {
      head.appendChild(el("th", numericColumns.indexOf(index) >= 0 ? { class: "num" } : {}, title));
    });
    node.appendChild(head);
    rows.forEach(function (cells) {
      var row = el("tr");
      cells.forEach(function (cell, index) {
        var td = el("td", numericColumns.indexOf(index) >= 0 ? { class: "num" } : {});
        if (cell instanceof Node) td.appendChild(cell);
        else td.textContent = cell === null || cell === undefined ? "—" : String(cell);
        row.appendChild(td);
      });
      node.appendChild(row);
    });
    return node;
  }

  function renderHeader() {
    document.getElementById("window").textContent =
      "Período: " + formatShortDate(data.window.start) + " a " + formatShortDate(data.window.end);
    document.getElementById("generated").textContent =
      "Dados gerados em " + data.generated_at.replace("T", " ").replace("Z", " UTC");
  }

  function renderKpis() {
    var summary = data.summary;
    var billing = data.billing;
    var cards = [
      ["Aplicações", integer.format(summary.applications), "projetos na conta ou no time"],
      ["Deploys no período", integer.format(summary.deploys), summary.errors + " com erro"],
      ["Taxa de sucesso", summary.success_rate === null ? "—" : summary.success_rate + "%", "deploys prontos entre os finalizados"],
      ["Custo no período", billing.available ? money.format(billing.total) : "indisponível", billing.available ? "cobrança da Vercel" : "veja a seção de cobrança"],
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

  function renderProjects() {
    var rows = data.projects.map(function (project) {
      var link = project.last_url ? el("a", { href: project.last_url, target: "_blank", rel: "noopener" }, "abrir") : "—";
      return [
        project.name,
        project.framework,
        stateBadge(project.last_state),
        project.last_target,
        formatDate(project.last_at),
        project.deploys,
        project.errors,
        link,
      ];
    });
    var box = document.getElementById("projects");
    box.replaceChildren();
    if (!rows.length) {
      box.appendChild(el("p", "muted", "Nenhum projeto encontrado com este token."));
      return;
    }
    box.appendChild(table(
      ["Aplicação", "Framework", "Último deploy", "Ambiente", "Quando", "Deploys", "Erros", "Link"],
      rows,
      [5, 6]
    ));
  }

  function renderDaily() {
    if (!window.Chart) return;
    new Chart(document.getElementById("deploysChart"), {
      type: "bar",
      data: {
        labels: data.daily.map(function (day) { return formatShortDate(day.date); }),
        datasets: [
          { label: "Prontos", data: data.daily.map(function (day) { return day.ready; }), backgroundColor: "rgba(52,211,153,0.75)", stack: "deploys" },
          { label: "Com erro", data: data.daily.map(function (day) { return day.error; }), backgroundColor: "rgba(248,113,113,0.8)", stack: "deploys" },
        ],
      },
      options: {
        maintainAspectRatio: false,
        scales: {
          x: { stacked: true },
          y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } },
        },
      },
    });
  }

  function renderBilling() {
    var billing = data.billing;
    var box = document.getElementById("billing");
    box.replaceChildren();
    if (!billing.available) {
      box.appendChild(el("p", "notice", billing.message));
      return;
    }
    box.appendChild(el("p", "muted", "Total no período: " + money.format(billing.total) + " (" + billing.currency + ")"));
    if (!billing.by_service.length) {
      box.appendChild(el("p", "muted", "Nenhuma cobrança registrada no período."));
      return;
    }
    var rows = billing.by_service.map(function (item) {
      return [
        item.service,
        money.format(item.cost),
        item.quantity.toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + " " + item.unit,
      ];
    });
    box.appendChild(table(["Serviço", "Custo", "Consumo"], rows, [1]));
  }

  function renderStates() {
    var box = document.getElementById("states");
    var entries = Object.keys(data.states || {}).map(function (state) {
      return [stateBadge(state), integer.format(data.states[state])];
    });
    box.replaceChildren();
    if (!entries.length) {
      box.appendChild(el("p", "muted", "Nenhum deploy no período."));
      return;
    }
    box.appendChild(table(["Estado", "Deploys"], entries, [1]));
  }

  function renderRecent() {
    var rows = data.recent.map(function (item) {
      var link = item.url ? el("a", { href: item.url, target: "_blank", rel: "noopener" }, "abrir") : "—";
      return [
        formatDate(item.time),
        item.project,
        stateBadge(item.state),
        item.target,
        item.branch,
        formatSeconds(item.duration_s),
        link,
      ];
    });
    var box = document.getElementById("recent");
    box.replaceChildren();
    if (!rows.length) {
      box.appendChild(el("p", "muted", "Nenhum deploy no período."));
      return;
    }
    box.appendChild(table(["Quando", "Aplicação", "Estado", "Ambiente", "Branch", "Duração", "Link"], rows, [5]));
  }

  renderHeader();
  renderKpis();
  renderProjects();
  renderDaily();
  renderBilling();
  renderStates();
  renderRecent();
})();
