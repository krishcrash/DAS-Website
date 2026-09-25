// One shared tooltip for any [data-tip] element (hover, keyboard focus, tap).

export function initTooltips() {
  const tip = document.createElement("div");
  tip.className = "tip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = false;
  document.body.appendChild(tip);

  let current = null;

  const show = (el) => {
    current = el;
    tip.textContent = el.dataset.tip;
    const r = el.getBoundingClientRect();
    const x = Math.min(Math.max(r.left + r.width / 2, 90), window.innerWidth - 90);
    tip.style.left = `${x}px`;
    tip.style.top = `${r.top}px`;
    tip.classList.add("is-on");
  };
  const hide = () => {
    current = null;
    tip.classList.remove("is-on");
  };

  document.addEventListener("pointerover", (e) => {
    const el = e.target.closest("[data-tip]");
    if (el && e.pointerType !== "touch") show(el);
  });
  document.addEventListener("pointerout", (e) => {
    const el = e.target.closest("[data-tip]");
    if (el && !el.contains(e.relatedTarget)) hide();
  });
  // Tap to toggle on touch screens.
  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-tip]");
    if (el) (current === el ? hide() : show(el));
    else if (current) hide();
  });
  document.addEventListener("focusin", (e) => {
    const el = e.target.closest("[data-tip]");
    if (el) show(el);
  });
  document.addEventListener("focusout", hide);
  window.addEventListener("scroll", () => current && hide(), { passive: true });
}
