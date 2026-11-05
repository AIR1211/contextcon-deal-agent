/* Motion for Avuno, using GSAP. Everything here is optional: without GSAP, or with motion off, pages just appear.
   Level comes from Settings: auto follows the device, full always animates, off never does.
   Animations only ever clear what they set, so content can never get stuck hidden. */
window.fx = (() => {
  let level = 'auto';
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  const on = () => window.gsap && level !== 'off' && (level === 'full' || !reduced());
  const ease = 'power3.out', clear = 'transform,opacity,visibility';
  const NUMBER = /^(₹?)([\d,]+(?:\.\d+)?)(%?)$/;

  function setLevel(next) {
    level = next;
    document.documentElement.dataset.motion = on() ? 'on' : 'off';
  }

  function count(el, delay = 0.1) {
    const text = el.textContent.trim(), m = text.match(NUMBER);
    if (!on() || !m) return;
    const end = parseFloat(m[2].replace(/,/g, '')), decimals = (m[2].split('.')[1] || '').length, state = { v: 0 };
    if (!end) return;
    el.textContent = m[1] + '0' + m[3];
    gsap.to(state, { v: end, duration: 1.1, delay, ease: 'power2.out',
      onUpdate() { el.textContent = m[1] + state.v.toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + m[3]; },
      onComplete() { el.textContent = text; } });
  }

  function meters(root) {
    root.querySelectorAll('.meter i').forEach((el, i) => {
      const width = el.style.width;
      gsap.fromTo(el, { width: '0%' }, { width, duration: 1.1, delay: 0.25 + Math.min(i, 14) * 0.04, ease: 'power3.out' });
    });
  }

  /* Headlines rise word by word. The words are restored afterwards, so text stays selectable and readable. */
  function headline(root) {
    const el = root.querySelector('.hero-title, .head h1');
    if (!el || el.children.length) return;
    const text = el.textContent;
    el.innerHTML = text.split(' ').map(w => `<span style="display:inline-block">${w.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</span>`).join(' ');
    gsap.from(el.children, { y: 26, autoAlpha: 0, rotate: 1.5, duration: 0.7, ease, stagger: 0.05, onComplete() { el.textContent = text; } });
  }

  /* A page arriving: the headline rises, blocks follow in order, meters fill, numbers count up. */
  function page(root) {
    if (!on()) return;
    headline(root);
    const items = root.querySelectorAll(':scope > .head > :not(div:first-child), :scope > .head > div:first-child > p, :scope > .card, :scope > .ask, :scope > form, :scope > details, :scope > .grid > *, :scope > .stack > *, :scope > .split > .stack > *, :scope > .onb > .card, :scope > .selbar');
    if (items.length) gsap.from(items, { autoAlpha: 0, y: 30, scale: 0.975, duration: 0.7, ease, delay: 0.1, stagger: { amount: Math.min(0.7, items.length * 0.07) }, clearProps: clear });
    root.querySelectorAll('.avatar').forEach((el, i) => gsap.from(el, { scale: 0.5, autoAlpha: 0, duration: 0.6, delay: 0.25 + Math.min(i, 10) * 0.05, ease: 'back.out(2)', clearProps: clear }));
    meters(root);
    root.querySelectorAll('.tile .v, .hero-num, .stats3 b').forEach(el => count(el, 0.25));
  }

  /* New lines in a running deal slide in, so the agent's work is visible as it happens. */
  function fresh(els) {
    if (!on() || !els.length) return;
    gsap.from(els, { autoAlpha: 0, x: -18, duration: 0.45, ease, stagger: 0.06, clearProps: clear });
    gsap.fromTo(els, { backgroundColor: 'rgba(201,162,78,.22)' }, { backgroundColor: 'rgba(201,162,78,0)', duration: 1.2, clearProps: 'backgroundColor' });
  }

  function grow(els) {
    if (!on() || !els.length) return;
    gsap.from(els, { scaleX: 0, transformOrigin: 'left center', duration: 0.6, ease: 'power2.inOut', stagger: 0.05, clearProps: 'transform,transform-origin' });
  }

  /* Something that needs attention or just finished: a question, a block, the agreed price. */
  function arrive(el) {
    if (!on() || !el) return;
    gsap.from(el, { autoAlpha: 0, y: 18, scale: 0.96, duration: 0.6, ease: 'back.out(1.8)', clearProps: clear });
  }

  function drawer(el) {
    if (!on() || !el) return;
    gsap.from(el, { x: 120, autoAlpha: 0, duration: 0.55, ease, clearProps: clear });
    const bg = document.querySelector('.drawer-bg');
    if (bg) gsap.from(bg, { opacity: 0, duration: 0.35, clearProps: 'opacity' });
  }

  function list(root) {
    if (!on() || !root) return;
    gsap.from(root.children, { autoAlpha: 0, y: 16, duration: 0.45, ease, stagger: 0.06, clearProps: clear });
  }

  function toast(el) {
    if (!on()) return;
    gsap.from(el, { autoAlpha: 0, y: 28, duration: 0.45, ease: 'back.out(1.8)', clearProps: 'opacity,visibility' });
  }

  function logo() {
    if (!on()) return;
    gsap.from('.logo svg', { y: 12, scale: 0.7, autoAlpha: 0, duration: 0.8, ease: 'back.out(2)', clearProps: clear });
    gsap.from('.seg', { autoAlpha: 0, y: 8, duration: 0.45, delay: 0.1, ease, clearProps: clear });
    if (document.querySelector('.nav a')) gsap.from('.nav a', { x: -20, autoAlpha: 0, duration: 0.5, ease, stagger: 0.06, delay: 0.15, clearProps: clear });
  }

  document.documentElement.dataset.motion = on() ? 'on' : 'off';
  return { page, fresh, grow, arrive, drawer, list, toast, logo, count, setLevel, reduced };
})();
