// Dead Auteur Society — site behaviour entry point (bundled by Hugo's js.Build).

import { initCrates } from "./crate.js";
import { initTilt } from "./tilt.js";
import { initReveal } from "./reveal.js";
import { initTooltips } from "./tooltip.js";
import { initArchive } from "./archive.js";
import { initAnalytics } from "./analytics.js";
import { initSubmit } from "./submit.js";

window.__das = true; // tells the inline failsafe in head.html that we booted

const root = document.documentElement;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

// ---- Masthead state + scroll-linked sprocket rails -------------------------

function initScroll() {
  const masthead = document.querySelector("[data-masthead]");
  const PERF_PITCH = 24; // px, must match --perf-v tile height
  let ticking = false;

  const update = () => {
    const y = window.scrollY;
    masthead?.classList.toggle("is-scrolled", y > 8);
    if (!reducedMotion.matches) {
      // Film runs *up* through the gate as you scroll down.
      root.style.setProperty("--perf-offset", `${-((y * 0.35) % PERF_PITCH)}px`);
    }
    ticking = false;
  };

  window.addEventListener(
    "scroll",
    () => {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(update);
      }
    },
    { passive: true }
  );
  update();
}

// ---- Mobile navigation overlay ---------------------------------------------

function initNav() {
  const toggle = document.querySelector("[data-nav-toggle]");
  const nav = document.querySelector("[data-nav]");
  if (!toggle || !nav) return;

  const label = toggle.querySelector(".masthead__toggle-label");
  const desktop = window.matchMedia("(min-width: 1180px)"); // keep in sync with chrome.css

  const setOpen = (open) => {
    toggle.setAttribute("aria-expanded", String(open));
    nav.classList.toggle("is-open", open);
    root.classList.toggle("nav-locked", open);
    if (label) label.textContent = open ? "Close" : "Menu";
    if (open) nav.querySelector("a")?.focus({ preventScroll: true });
  };

  toggle.addEventListener("click", () => setOpen(toggle.getAttribute("aria-expanded") !== "true"));

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && nav.classList.contains("is-open")) {
      setOpen(false);
      toggle.focus();
    }
  });

  // Keep focus inside the overlay while it is open.
  nav.addEventListener("keydown", (e) => {
    if (e.key !== "Tab" || !nav.classList.contains("is-open")) return;
    const links = [...nav.querySelectorAll("a")];
    const first = links[0];
    const last = links[links.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      toggle.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      toggle.focus();
    }
  });

  desktop.addEventListener("change", (e) => e.matches && setOpen(false));
}

// ---- Letterbox gate on internal navigation ---------------------------------

function initLetterbox() {
  const CLOSE_MS = 380;

  document.addEventListener("click", (e) => {
    if (reducedMotion.matches || e.defaultPrevented) return;
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

    const a = e.target.closest("a[href]");
    if (!a || a.target === "_blank" || a.hasAttribute("download")) return;

    const url = new URL(a.href, location.href);
    if (url.origin !== location.origin) return;
    // Same page or in-page anchor: no transition.
    if (url.pathname === location.pathname && url.search === location.search) return;
    // Non-HTML assets (feeds, images, chart files opened directly).
    if (/\.(xml|jpe?g|png|webp|gif|svg|pdf|json)$/i.test(url.pathname)) return;

    e.preventDefault();
    root.classList.add("is-leaving");
    window.setTimeout(() => {
      location.href = url.href;
    }, CLOSE_MS);
  });

  // Returning via back/forward cache: reopen the gate.
  window.addEventListener("pageshow", (e) => {
    if (e.persisted) root.classList.remove("is-leaving");
  });
}

initScroll();
initNav();
initLetterbox();
initArchive(); // before reveal/tilt: it may reorder cells
initCrates();
initTilt();
initTooltips();
initReveal();
initAnalytics();
initSubmit();
