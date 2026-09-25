// 3D tilt + pointer glare for [data-tilt] elements.
//
// Mouse / pen: the card follows the pointer while hovering.
// Touch: pressing tilts the card toward the finger and sinks it slightly
// (a tactile "press"); it springs back on release or when the finger
// starts scrolling. We never call preventDefault, so swiping still scrolls.

const MAX_DEG = 9;
const TOUCH_DEG = 6;

export function initTilt(root = document) {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const els = root.querySelectorAll("[data-tilt]");

  els.forEach((el) => {
    let frame = 0;
    let rect = null;

    const apply = (clientX, clientY, deg, press = 1) => {
      rect = rect || el.getBoundingClientRect();
      const px = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1);
      const py = Math.min(Math.max((clientY - rect.top) / rect.height, 0), 1);
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        el.style.setProperty("--ry", `${(px - 0.5) * 2 * deg}deg`);
        el.style.setProperty("--rx", `${(0.5 - py) * 2 * deg}deg`);
        el.style.setProperty("--gx", `${px * 100}%`);
        el.style.setProperty("--gy", `${py * 100}%`);
        el.style.setProperty("--glare", "1");
        el.style.setProperty("--press", String(press));
      });
    };

    const reset = () => {
      cancelAnimationFrame(frame);
      rect = null;
      el.classList.remove("is-tilting");
      ["--rx", "--ry", "--glare", "--press"].forEach((p) => el.style.removeProperty(p));
    };

    el.addEventListener("pointerenter", (e) => {
      if (reduced.matches || e.pointerType === "touch") return;
      rect = el.getBoundingClientRect();
      el.classList.add("is-tilting");
    });
    el.addEventListener("pointermove", (e) => {
      if (reduced.matches || e.pointerType === "touch") return;
      apply(e.clientX, e.clientY, MAX_DEG);
    });
    el.addEventListener("pointerleave", reset);

    // Touch press
    el.addEventListener(
      "pointerdown",
      (e) => {
        if (reduced.matches || e.pointerType !== "touch") return;
        rect = el.getBoundingClientRect();
        apply(e.clientX, e.clientY, TOUCH_DEG, 0.97);
      },
      { passive: true }
    );
    ["pointerup", "pointercancel"].forEach((type) =>
      el.addEventListener(type, (e) => e.pointerType === "touch" && reset(), { passive: true })
    );
  });
}
