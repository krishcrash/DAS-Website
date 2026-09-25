// Analytics plates: render the Plotly specs produced by scripts/build_charts.py.
//
// Plotly (~1.4 MB gz) is only fetched on pages that have charts, and only once
// the first chart is about to scroll into view. Each spec carries a base
// figure plus "views" (what the old Plotly dropdowns switched between); we
// render our own chip/select controls and apply views with Plotly.update.

const PLOTLY_SRC = "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js";
const CONFIG = { displayModeBar: false, responsive: true, scrollZoom: false, doubleClick: false };
const CHIP_LIMIT = 10; // more views than this → a <select>

let plotlyPromise = null;
function loadPlotly() {
  if (window.Plotly) return Promise.resolve(window.Plotly);
  plotlyPromise ||= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = PLOTLY_SRC;
    s.async = true;
    s.onload = () => resolve(window.Plotly);
    s.onerror = () => reject(new Error("Plotly failed to load"));
    document.head.appendChild(s);
  });
  return plotlyPromise;
}

const fmt = (v) => (v === null || v === undefined || v === "" ? "—" : typeof v === "number" ? String(Math.round(v * 100) / 100) : String(v));
const monthLabel = (iso) => {
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleDateString("en-GB", { month: "short", year: "numeric" });
};

function renderTable(host, head, rows) {
  const t = document.createElement("table");
  t.innerHTML =
    `<thead><tr>${head.map((h) => `<th scope="col">${h}</th>`).join("")}</tr></thead>` +
    `<tbody>${rows
      .map((r) => `<tr>${r.map((c, i) => (i === 0 ? `<th scope="row">${c}</th>` : `<td>${fmt(c)}</td>`)).join("")}</tr>`)
      .join("")}</tbody>`;
  host.replaceChildren(t);
}

// Build chips (few views) or a select (many) and call onChange(index).
function buildControls(host, views, onChange) {
  if (!host || !views.length) return;
  const label = host.dataset.label || "View";
  if (views.length > CHIP_LIMIT) {
    const id = `sel-${Math.random().toString(36).slice(2, 8)}`;
    host.innerHTML = `<label class="plate__label mono" for="${id}">${label}</label>`;
    const sel = document.createElement("select");
    sel.id = id;
    sel.className = "plate__select";
    views.forEach((v, i) => sel.add(new Option(v.label, String(i))));
    sel.addEventListener("change", () => onChange(Number(sel.value)));
    host.appendChild(sel);
    return;
  }
  host.innerHTML = `<span class="plate__label mono">${label}</span>`;
  const group = document.createElement("div");
  group.className = "plate__chips";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", label);
  views.forEach((v, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = v.label;
    b.setAttribute("aria-pressed", String(i === 0));
    b.addEventListener("click", () => {
      group.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c === b)));
      onChange(i);
    });
    group.appendChild(b);
  });
  host.appendChild(group);
}

// ---- Standard Plotly figures ---------------------------------------------------

function tableFromFigure(spec, gd) {
  const tr = gd.data[0];
  if (tr.type === "heatmap") {
    return tr.y.map((name, r) => [name, ...tr.z[r]]);
  }
  if (tr.orientation === "h") {
    const labels = tr.customdata || tr.y;
    return labels.map((l, i) => [l, tr.x[i]]);
  }
  return tr.x.map((x, i) => [monthLabel(x), tr.y[i]]);
}

async function renderStandard(plate, spec) {
  const Plotly = await loadPlotly();
  const canvas = plate.querySelector("[data-chart-canvas]");
  const tableHost = plate.querySelector("[data-chart-table]");
  canvas.replaceChildren();
  await Plotly.newPlot(canvas, spec.figure.data, spec.figure.layout, CONFIG);
  const sync = () => renderTable(tableHost, spec.table || ["", ""], tableFromFigure(spec, canvas));
  sync();
  buildControls(plate.querySelector("[data-chart-controls]"), spec.views || [], async (i) => {
    const v = spec.views[i];
    await Plotly.update(canvas, v.restyle || {}, v.relayout || {});
    sync();
  });
}

// ---- Radar small multiples ------------------------------------------------------

async function renderRadars(plate, spec) {
  const Plotly = await loadPlotly();
  const canvas = plate.querySelector("[data-chart-canvas]");
  const tableHost = plate.querySelector("[data-chart-table]");
  const cats = spec.categories;
  const theta = [...cats, cats[0]];
  const close = (r) => (r ? [...r, r[0]] : cats.map(() => null).concat(null));
  const c = spec.colors;

  canvas.replaceChildren();
  canvas.classList.add("plate__canvas--grid");
  const minis = spec.members.map((m) => {
    const cell = document.createElement("div");
    cell.className = "radar";
    cell.innerHTML = `<p class="radar__name">${m.name}</p><div class="radar__plot"></div><p class="radar__empty mono">Didn't score</p>`;
    canvas.appendChild(cell);
    return { m, cell, plot: cell.querySelector(".radar__plot") };
  });

  const layout = {
    height: 270,
    margin: { l: 58, r: 58, t: 24, b: 24 },
    paper_bgcolor: "rgba(0,0,0,0)",
    showlegend: false,
    dragmode: false,
    font: { family: "Archivo, Arial, sans-serif", size: 10, color: c.text },
    hoverlabel: { bgcolor: "#ede5d6", bordercolor: "#ede5d6", font: { color: "#0b0a09", size: 12 } },
    polar: {
      bgcolor: "rgba(0,0,0,0)",
      radialaxis: { range: [0, 100], showticklabels: false, ticks: "", gridcolor: c.grid, linecolor: c.grid, showline: false },
      angularaxis: { gridcolor: c.grid, linecolor: c.grid, tickfont: { size: 10, color: c.text } },
    },
  };

  const draw = async (view, first) => {
    await Promise.all(
      minis.map(({ m, cell, plot }) => {
        const mine = view.members[m.code];
        cell.classList.toggle("is-empty", !mine);
        const traces = [
          { type: "scatterpolar", r: close(view.society), theta, mode: "lines", line: { color: c.society, width: 1.5 },
            name: "Society", hovertemplate: "%{theta}: %{r:.0f}%<extra>Society</extra>" },
          { type: "scatterpolar", r: close(mine), theta, mode: "lines+markers", fill: "toself",
            fillcolor: "rgba(200,127,30,0.14)", line: { color: c.member, width: 2 },
            marker: { size: 6, color: c.member, line: { width: 1.5, color: "#0b0a09" } },
            name: m.name, hovertemplate: `%{theta}: %{r:.0f}%<extra>${m.name}</extra>` },
        ];
        return first ? Plotly.newPlot(plot, traces, layout, CONFIG) : Plotly.react(plot, traces, layout, CONFIG);
      })
    );
    renderTable(
      tableHost,
      ["Category", "Society", ...minis.map(({ m }) => m.name)],
      cats.map((cat, i) => [cat, view.society[i], ...minis.map(({ m }) => (view.members[m.code] ? view.members[m.code][i] : null))])
    );
  };

  await draw(spec.views[0], true);
  buildControls(plate.querySelector("[data-chart-controls]"), spec.views, (i) => draw(spec.views[i], false));
}

// ---- Boot -------------------------------------------------------------------------

export function initAnalytics() {
  const plates = [...document.querySelectorAll("[data-chart]")];
  if (!plates.length) return;

  const render = (plate) => {
    if (plate.dataset.rendered) return;
    plate.dataset.rendered = "1";
    let spec;
    try {
      spec = JSON.parse(plate.querySelector("[data-chart-spec]").textContent);
    } catch {
      return;
    }
    const job = spec.kind === "radar-multiples" ? renderRadars(plate, spec) : renderStandard(plate, spec);
    job.catch(() => {
      const canvas = plate.querySelector("[data-chart-canvas]");
      canvas.innerHTML = `<p class="plate__loading mono">The chart couldn't load — the numbers are in the table below.</p>`;
      plate.querySelector("details")?.setAttribute("open", "");
    });
  };

  if (!("IntersectionObserver" in window)) {
    plates.forEach(render);
    return;
  }
  const io = new IntersectionObserver(
    (entries) => entries.forEach((e) => { if (e.isIntersecting) { io.unobserve(e.target); render(e.target); } }),
    { rootMargin: "600px 0px" }
  );
  plates.forEach((p) => io.observe(p));
}
