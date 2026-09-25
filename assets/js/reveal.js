// Reveal [data-reveal] elements as they scroll into view. Siblings revealed
// together are staggered so grids "develop" in sequence like a contact sheet.
//
// IntersectionObserver does the work; a cheap position check on scroll/load
// backs it up so jumps (anchor links, restored scroll on back/forward) never
// leave content hidden — anything at or above the viewport is revealed.

export function initReveal(root = document) {
  let pending = [...root.querySelectorAll("[data-reveal]:not(.is-in)")];
  if (!pending.length) return;

  const show = (els) => {
    els.forEach((el, i) => {
      el.style.setProperty("--reveal-delay", `${Math.min(i, 6) * 70}ms`);
      el.classList.add("is-in");
    });
    pending = pending.filter((el) => !el.classList.contains("is-in"));
  };

  if (!("IntersectionObserver" in window)) {
    show(pending);
    return;
  }

  const io = new IntersectionObserver(
    (entries) => {
      const entering = entries.filter((e) => e.isIntersecting).map((e) => e.target);
      entering.forEach((el) => io.unobserve(el));
      show(entering);
    },
    { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
  );
  pending.forEach((el) => io.observe(el));

  let raf = 0;
  const sweep = () => {
    raf = 0;
    const limit = window.innerHeight * 0.95;
    const due = pending.filter((el) => el.getBoundingClientRect().top < limit);
    due.forEach((el) => io.unobserve(el));
    if (due.length) show(due);
    if (!pending.length) {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    }
  };
  const onScroll = () => { if (!raf) raf = requestAnimationFrame(sweep); };
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  window.addEventListener("load", onScroll);
  window.addEventListener("hashchange", onScroll);
  onScroll();
}
