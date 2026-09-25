// Record crate: horizontal browsing that feels like flipping through media.
//
// Geometry: the "front" of the crate is the snap position (the leftmost fully
// visible slot). That sleeve stands upright; sleeves behind it lean back into
// depth; sleeves already flipped past fall away to the left and fade.
//
// Input:
//   touch     native scroll + scroll-snap (momentum for free), no hijacking
//   mouse     click-and-drag with momentum, clicks suppressed after a drag
//   keyboard  ←/→ on the focused track move one sleeve; buttons move a page
//   wheel     trackpads scroll horizontally natively; vertical wheel is left
//             alone so the page never gets stuck

const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

function setupCrate(crate) {
  const track = crate.querySelector("[data-crate-track]");
  const slots = [...crate.querySelectorAll("[data-crate-item]")];
  const prev = crate.querySelector("[data-crate-prev]");
  const next = crate.querySelector("[data-crate-next]");
  const counter = crate.querySelector("[data-crate-index]");
  if (!track || !slots.length) return;

  let step = 0;  // slot width + gap, px
  let inset = 0; // track padding before the first slot = the "front" position
  let raf = 0;

  const measure = () => {
    inset = slots[0].offsetLeft;
    step = slots[1] ? slots[1].offsetLeft - inset : slots[0].offsetWidth;
  };

  const render = () => {
    raf = 0;
    let front = 0;
    let best = Infinity;

    slots.forEach((slot, i) => {
      // Distance from the front position, in sleeves (0 = front).
      const d = (slot.offsetLeft - track.scrollLeft - inset) / step;
      if (Math.abs(d) < best) { best = Math.abs(d); front = i; }
      if (reduced.matches) return;

      let ry = 0, tz = 0, ty = 0, o = 1;
      if (d >= 0) {
        const k = Math.min(d, 4);
        ry = -k * 5;            // lean back
        tz = -k * 26;
        ty = k * 4;
        ty -= Math.max(0, 1 - d * 2.5) * 10; // front sleeve lifts slightly
      } else {
        const k = Math.min(-d, 1.5);
        ry = k * 38;            // flipped past: falls away to the left
        tz = -k * 90;
        o = Math.max(0.25, 1 - k * 0.6);
      }
      slot.style.setProperty("--ry", `${ry.toFixed(2)}deg`);
      slot.style.setProperty("--tz", `${tz.toFixed(1)}px`);
      slot.style.setProperty("--ty", `${ty.toFixed(1)}px`);
      slot.style.setProperty("--o", o.toFixed(3));
    });

    if (counter) counter.textContent = String(front + 1).padStart(2, "0");
    const max = track.scrollWidth - track.clientWidth - 2;
    if (prev) prev.disabled = track.scrollLeft <= 2;
    if (next) next.disabled = track.scrollLeft >= max;
  };

  const schedule = () => { if (!raf) raf = requestAnimationFrame(render); };

  // ---- Buttons + keyboard ----------------------------------------------------
  const pageBy = (dir) => {
    const perPage = Math.max(1, Math.floor(track.clientWidth / step) - 1);
    track.scrollBy({ left: dir * perPage * step, behavior: reduced.matches ? "auto" : "smooth" });
  };
  prev?.addEventListener("click", () => pageBy(-1));
  next?.addEventListener("click", () => pageBy(1));
  track.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    track.scrollBy({ left: (e.key === "ArrowRight" ? 1 : -1) * step, behavior: reduced.matches ? "auto" : "smooth" });
  });

  // ---- Mouse drag with momentum ---------------------------------------------
  let down = false, dragged = false, startX = 0, startScroll = 0;
  let lastX = 0, lastT = 0, velocity = 0, glide = 0;

  track.addEventListener("pointerdown", (e) => {
    if (e.pointerType !== "mouse" || e.button !== 0) return;
    cancelAnimationFrame(glide);
    down = true;
    dragged = false;
    startX = lastX = e.clientX;
    startScroll = track.scrollLeft;
    lastT = performance.now();
    velocity = 0;
  });

  track.addEventListener("pointermove", (e) => {
    if (!down) return;
    const dx = e.clientX - startX;
    if (!dragged && Math.abs(dx) > 5) {
      dragged = true;
      track.classList.add("is-dragging");
      track.setPointerCapture(e.pointerId);
    }
    if (!dragged) return;
    const now = performance.now();
    velocity = (e.clientX - lastX) / Math.max(1, now - lastT) * 16; // px per frame
    lastX = e.clientX;
    lastT = now;
    track.scrollLeft = startScroll - dx;
  });

  const release = (e) => {
    if (!down) return;
    down = false;
    if (track.hasPointerCapture?.(e.pointerId)) track.releasePointerCapture(e.pointerId);
    if (!dragged) return;
    // Glide, then hand back to scroll-snap.
    const tick = () => {
      velocity *= 0.93;
      track.scrollLeft -= velocity;
      if (Math.abs(velocity) > 0.6 && !reduced.matches) {
        glide = requestAnimationFrame(tick);
      } else {
        track.classList.remove("is-dragging");
      }
    };
    glide = requestAnimationFrame(tick);
  };
  track.addEventListener("pointerup", release);
  track.addEventListener("pointercancel", release);

  // A drag must not also open the sleeve under the cursor.
  track.addEventListener("click", (e) => {
    if (dragged) { e.preventDefault(); e.stopPropagation(); dragged = false; }
  }, true);
  track.addEventListener("dragstart", (e) => e.preventDefault());

  // ---- Wire up ---------------------------------------------------------------
  track.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", () => { measure(); schedule(); });
  reduced.addEventListener?.("change", () => {
    slots.forEach((s) => ["--ry", "--tz", "--ty", "--o"].forEach((p) => s.style.removeProperty(p)));
    schedule();
  });
  measure();
  render();
}

export function initCrates(root = document) {
  root.querySelectorAll("[data-crate]").forEach(setupCrate);
}
