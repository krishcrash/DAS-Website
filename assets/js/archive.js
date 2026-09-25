// Archive sort + nominator filter. The server renders the default view
// (newest first, grouped by year); this re-lays the same cells in place.
// State is mirrored to the URL (?sort=score-desc&by=ZA) so views are shareable.

const SORTS = {
  "date-desc": (a, b) => b.date.localeCompare(a.date),
  "date-asc": (a, b) => a.date.localeCompare(b.date),
  "score-desc": (a, b) => b.total - a.total || a.rank - b.rank,
  "sd-desc": (a, b) => b.sd - a.sd,
};
const SORT_LABEL = {
  "date-desc": "newest first",
  "date-asc": "oldest first",
  "score-desc": "highest rated first",
  "sd-desc": "most divisive first",
};

// Wide "feature" slots at positions 0 and 6 of every 10 → alternating sides.
const isFeature = (i) => i % 10 === 0 || i % 10 === 6;

export function initArchive() {
  const root = document.querySelector("[data-archive]");
  if (!root) return;
  const grid = root.querySelector("[data-archive-grid]");
  const toolbar = root.querySelector("[data-archive-toolbar]");
  const status = root.querySelector("[data-archive-status]");

  const cells = [...grid.querySelectorAll("[data-archive-cell]")].map((el) => {
    const s = el.querySelector(".sleeve").dataset;
    return {
      el,
      date: s.date,
      year: s.date.slice(0, 4),
      nominator: s.nominator,
      total: parseFloat(s.total || "0"),
      rank: parseInt(s.rank || "999", 10),
      sd: parseFloat(s.sd || "0"),
    };
  });
  const names = Object.fromEntries(
    [...toolbar.querySelectorAll("[data-filter]")].map((b) => [b.dataset.filter, b.textContent.trim()])
  );

  const params = new URLSearchParams(location.search);
  let sort = SORTS[params.get("sort")] ? params.get("sort") : "date-desc";
  let by = params.get("by") && names[params.get("by")] ? params.get("by") : "";

  const yearHeader = (year, count) => {
    const h = document.createElement("h2");
    h.className = "archive__year";
    h.innerHTML = `<span>${year}</span><span class="mono">${count} film${count === 1 ? "" : "s"}</span>`;
    return h;
  };

  const render = (announce) => {
    const list = cells.filter((c) => !by || c.nominator === by).sort(SORTS[sort]);
    const frag = document.createDocumentFragment();

    if (sort.startsWith("date")) {
      const groups = new Map();
      list.forEach((c) => (groups.get(c.year) || groups.set(c.year, []).get(c.year)).push(c));
      groups.forEach((items, year) => {
        frag.appendChild(yearHeader(year, items.length));
        items.forEach((c, i) => {
          c.el.classList.toggle("is-feature", isFeature(i));
          frag.appendChild(c.el);
        });
      });
    } else {
      list.forEach((c, i) => {
        c.el.classList.toggle("is-feature", isFeature(i));
        frag.appendChild(c.el);
      });
    }
    grid.replaceChildren(frag);
    cells.forEach((c) => c.el.classList.add("is-in")); // no staggered re-reveal on re-sort

    toolbar.querySelectorAll("[data-sort]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.sort === sort)));
    toolbar.querySelectorAll("[data-filter]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.filter === by)));

    const who = by ? ` picked by ${names[by]}` : "";
    status.textContent = `${list.length} film${list.length === 1 ? "" : "s"}${who}, ${SORT_LABEL[sort]}`;

    if (announce) {
      const url = new URL(location.href);
      sort === "date-desc" ? url.searchParams.delete("sort") : url.searchParams.set("sort", sort);
      by ? url.searchParams.set("by", by) : url.searchParams.delete("by");
      history.replaceState(null, "", url);
    }
  };

  toolbar.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.sort) sort = b.dataset.sort;
    if ("filter" in b.dataset) by = b.dataset.filter;
    render(true);
  });

  toolbar.hidden = false;
  if (sort !== "date-desc" || by) render(false);
  else status.textContent = `${cells.length} films, ${SORT_LABEL[sort]}`;
}
