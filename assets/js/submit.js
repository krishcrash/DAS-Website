// Members-only score submission (/submit.html).
//
// 1. Gate: the entered password is SHA-256 hashed and compared with the hash
//    from hugo.toml (params.submit.passwordHash). This keeps casual visitors
//    out; it is not real security (a static site can't keep secrets), so the
//    Formspree endpoint should also have spam filtering / allowed domains set.
// 2. Scorecard: sliders + number boxes per category, running total, and on
//    submit a POST to Formspree, which emails the submission to the owner —
//    including rows already formatted for master-data/ratings_by_metric.csv.

const UNLOCK_KEY = "das-booth-unlocked";

async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const store = {
  get: () => { try { return sessionStorage.getItem(UNLOCK_KEY); } catch { return null; } },
  set: (v) => { try { sessionStorage.setItem(UNLOCK_KEY, v); } catch { /* private mode */ } },
};

const round2 = (n) => Math.round(n * 100) / 100;

// A dial is either a slider + number box, or (Enjoyable) a 0/max radio pair.
const valueOf = (dial) => {
  const choices = dial.querySelectorAll("[data-dial-choice]");
  if (choices.length) return dial.querySelector("[data-dial-choice]:checked")?.value ?? "";
  return dial.querySelector("[data-dial-input]").value;
};
const ddmmyyyy = (iso) => { const [y, m, d] = iso.split("-"); return `${d}/${m}/${y}`; };

function openForm(root) {
  const gate = root.querySelector("[data-gate]");
  const host = root.querySelector("[data-form-host]");
  const tpl = root.querySelector("[data-form-template]");
  if (!tpl || host.childElementCount) return;
  host.appendChild(tpl.content.cloneNode(true));
  gate.hidden = true;
  wireForm(root, host.querySelector("[data-score-form]"));
  host.querySelector("select, input")?.focus();
}

function wireForm(root, form) {
  const endpoint = root.dataset.endpoint;
  const dev = "dev" in root.dataset;
  const totalEl = form.querySelector("[data-total]");
  const status = form.querySelector("[data-status]");
  const btn = form.querySelector("[data-submit-btn]");
  const dials = [...form.querySelectorAll("[data-dial]")];

  const today = new Date();
  form.querySelector("[data-today]").value =
    `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

  const recompute = () => {
    const total = dials.reduce((sum, d) => sum + (parseFloat(valueOf(d)) || 0), 0);
    totalEl.textContent = String(round2(total));
  };

  // Keep slider and number box in step; the number box is the real field.
  dials.forEach((d) => {
    d.querySelectorAll("[data-dial-choice]").forEach((r) =>
      r.addEventListener("change", () => {
        d.classList.add("is-set");
        d.classList.remove("is-invalid");
        recompute();
      })
    );
    const slider = d.querySelector("[data-dial-slider]");
    const input = d.querySelector("[data-dial-input]");
    if (!slider || !input) return;
    const paint = () => {
      const min = parseFloat(slider.min), max = parseFloat(slider.max);
      d.style.setProperty("--fill", String((parseFloat(slider.value) - min) / (max - min)));
    };
    slider.addEventListener("input", () => {
      input.value = String(round2(parseFloat(slider.value)));
      d.classList.add("is-set");
      d.classList.remove("is-invalid");
      paint();
      recompute();
    });
    input.addEventListener("input", () => {
      const v = parseFloat(input.value);
      if (!Number.isNaN(v)) slider.value = String(v);
      d.classList.toggle("is-set", input.value !== "");
      d.classList.toggle("is-invalid", input.value !== "" && !input.checkValidity());
      paint();
      recompute();
    });
    paint();
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    status.textContent = "";
    status.className = "scorecard__status";

    // Validate (show every problem at once, focus the first).
    let firstBad = null;
    form.querySelectorAll("input[required], select[required]").forEach((el) => {
      const bad = !el.checkValidity();
      el.closest("[data-dial], .field")?.classList.toggle("is-invalid", bad);
      if (bad && !firstBad) firstBad = el;
    });
    if (firstBad) {
      status.textContent = "Some fields need attention — every category needs a score within its range.";
      status.classList.add("is-error");
      firstBad.focus();
      return;
    }

    const fd = new FormData(form);
    const code = fd.get("initials");
    const name = form.querySelector(`option[value="${code}"]`)?.dataset.name || code;
    const film = String(fd.get("film")).trim();
    const date = ddmmyyyy(String(fd.get("date")));
    const total = round2(dials.reduce((s, d) => s + parseFloat(valueOf(d)), 0));

    // Rows in ratings_by_metric.csv column order:
    // date,user,movie,list_user,Metric,metric_order,Score  (list_user = the film's nominator; fill in on import)
    const csvFilm = /[",]/.test(film) ? `"${film.replace(/"/g, '""')}"` : film;
    const rows = dials.map((d) =>
      [date, code, csvFilm, "", d.dataset.key, d.dataset.order, valueOf(d)].join(",")
    );
    fd.set("member", name);
    fd.set("total", String(total));
    fd.set("csv_rows", rows.join("\n"));
    fd.set("_subject", `DAS scores: ${code} — ${film} (${total})`);

    if (!endpoint) {
      status.classList.add("is-warn");
      status.innerHTML = dev
        ? `<strong>Preview only</strong> — no Formspree endpoint is set, so nothing was sent. This is what would be emailed:<pre>${[...fd.entries()]
            .filter(([k]) => k !== "_gotcha")
            .map(([k, v]) => `${k}: ${v}`)
            .join("\n")
            .replace(/</g, "&lt;")}</pre>`
        : "Submissions aren't switched on yet — please send your scores to the ledger keeper directly.";
      return;
    }

    btn.disabled = true;
    btn.textContent = "Sending…";
    try {
      const res = await fetch(endpoint, { method: "POST", body: fd, headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(String(res.status));
      form.innerHTML = `
        <div class="sent">
          <p class="eyebrow eyebrow--red">In the can</p>
          <h2 class="sent__title">Thanks, ${name.replace(/</g, "&lt;")}.</h2>
          <p class="sent__copy">Your ${total} for <em>${film.replace(/</g, "&lt;")}</em> is on its way to the ledger keeper.</p>
          <a class="btn btn--ghost" href="${location.pathname}">Score another film</a>
        </div>`;
      form.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch {
      btn.disabled = false;
      btn.textContent = "Submit scores";
      status.classList.add("is-error");
      status.textContent = "That didn't send — check your connection and try again.";
    }
  });
}

export function initSubmit() {
  const root = document.querySelector("[data-submit]");
  if (!root) return;
  const hash = root.dataset.hash;

  if (hash && store.get() === hash) {
    openForm(root);
    return;
  }

  root.querySelector("[data-gate-dev]")?.addEventListener("click", () => openForm(root));

  const gateForm = root.querySelector("[data-gate-form]");
  const err = root.querySelector("[data-gate-error]");
  gateForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = gateForm.querySelector("input");
    if (!window.crypto?.subtle) {
      err.textContent = "This browser can't check the password here (needs HTTPS).";
      err.hidden = false;
      return;
    }
    const attempt = await sha256Hex(input.value);
    if (attempt === hash) {
      store.set(hash);
      openForm(root);
    } else {
      err.hidden = false;
      gateForm.classList.remove("is-wrong");
      void gateForm.offsetWidth; // restart the shake
      gateForm.classList.add("is-wrong");
      input.select();
    }
  });
}
