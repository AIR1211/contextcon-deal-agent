/* Motion for Avuno, using GSAP. Everything here is optional: without GSAP, or with reduced motion set, pages just appear.
   Animations only ever clear what they set, so content can never get stuck hidden. */
window.fx = (() => {
  const on = () => window.gsap && !matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ease = 'power3.out', clear = 'transform,opacity,visibility';
  const NUMBER = /^(₹?)([\d,]+(?:\.\d+)?)(%?)$/;

  function count(el, delay = 0.1) {
    const text = el.textContent.trim(), m = text.match(NUMBER);
    if (!on() || !m) return;
    const end = parseFloat(m[2].replace(/,/g, '')), decimals = (m[2].split('.')[1] || '').length, state = { v: 0 };
    if (!end) return;
    gsap.to(state, { v: end, duration: 0.9, delay, ease: 'power2.out',
      onUpdate() { el.textContent = m[1] + state.v.toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + m[3]; },
      onComplete() { el.textContent = text; } });
  }

  function meters(root) {
    root.querySelectorAll('.meter i').forEach((el, i) => {
      const width = el.style.width;
      gsap.fromTo(el, { width: '0%' }, { width, duration: 0.9, delay: 0.12 + Math.min(i, 12) * 0.025, ease: 'power2.out' });
    });
  }

  /* A page arriving: blocks rise in order, meters fill, headline numbers count up. */
  function page(root) {
    if (!on()) return;
    const items = root.querySelectorAll(':scope > .head, :scope > .card, :scope > .ask, :scope > form, :scope > details, :scope > .grid > *, :scope > .stack > *, :scope > .split > .stack > *, :scope > .onb > *, :scope > .selbar');
    gsap.from(items, { autoAlpha: 0, y: 14, duration: 0.5, ease, stagger: { amount: Math.min(0.45, items.length * 0.04) }, clearProps: clear });
    meters(root);
    root.querySelectorAll('.tile .v, .hero-num, .stats3 b').forEach(el => count(el, 0.15));
  }

  /* New lines in a running deal slide in, so the agent's work is visible as it happens. */
  function fresh(els) {
    if (!on() || !els.length) return;
    gsap.from(els, { autoAlpha: 0, x: -10, duration: 0.35, ease, stagger: 0.05, clearProps: clear });
  }

  function grow(els) {
    if (!on() || !els.length) return;
    gsap.from(els, { scaleX: 0, transformOrigin: 'left center', duration: 0.5, ease: 'power2.inOut', stagger: 0.04, clearProps: 'transform,transform-origin' });
  }

  /* Something that needs attention or just finished: a question, a block, the agreed price. */
  function arrive(el) {
    if (!on() || !el) return;
    gsap.from(el, { autoAlpha: 0, y: 10, scale: 0.985, duration: 0.45, ease: 'back.out(1.6)', clearProps: clear });
  }

  function drawer(el) {
    if (!on() || !el) return;
    gsap.from(el, { x: 56, autoAlpha: 0, duration: 0.42, ease, clearProps: clear });
    const bg = document.querySelector('.drawer-bg');
    if (bg) gsap.from(bg, { opacity: 0, duration: 0.3, clearProps: 'opacity' });
  }

  function list(root) {
    if (!on() || !root) return;
    gsap.from(root.children, { autoAlpha: 0, y: 8, duration: 0.35, ease, stagger: 0.04, clearProps: clear });
  }

  function toast(el) {
    if (!on()) return;
    gsap.from(el, { autoAlpha: 0, y: 16, duration: 0.3, ease, clearProps: 'opacity,visibility' });
  }

  function logo() {
    if (!on()) return;
    gsap.from('.logo svg', { y: 8, autoAlpha: 0, duration: 0.6, ease, clearProps: clear });
    gsap.from('.nav a', { x: -8, autoAlpha: 0, duration: 0.35, ease, stagger: 0.04, delay: 0.1, clearProps: clear });
  }

  return { page, fresh, grow, arrive, drawer, list, toast, logo, count };
})();
