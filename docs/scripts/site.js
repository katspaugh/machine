/* machine — site interactions
 * - nav-stuck on scroll
 * - reveal-on-scroll
 * - copy buttons (one-liner + hero CTA)
 */
(function () {
  'use strict';

  // ---------- Nav: thin border fades in after hero ----------
  const nav = document.getElementById('nav');
  const sentinel = document.getElementById('hero');
  if (nav && sentinel && 'IntersectionObserver' in window) {
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          // when hero leaves the top → stuck
          nav.classList.toggle('is-stuck', e.intersectionRatio < 0.15);
        }
      },
      { threshold: [0, 0.15, 1] }
    );
    io.observe(sentinel);
  }

  // ---------- Reveal on scroll, first entry only ----------
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add('is-in');
            io.unobserve(e.target);
          }
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );
    document.querySelectorAll('.reveal').forEach((el) => io.observe(el));
  } else {
    document.querySelectorAll('.reveal').forEach((el) => el.classList.add('is-in'));
  }

  // ---------- Copy buttons ----------
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(() => fallbackCopy(text));
    }
    return Promise.resolve(fallbackCopy(text));
  }
  function fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (_) {}
    document.body.removeChild(ta);
  }

  // hero primary CTA: copies install one-liner, swaps label briefly
  document.querySelectorAll('[data-copy]').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      const text = btn.getAttribute('data-copy');
      if (!text) return;
      copyText(text);
      const label = btn.querySelector('.btn-text, .label');
      if (label) {
        const original = btn.getAttribute('data-label') || label.textContent;
        if (!btn.hasAttribute('data-label')) btn.setAttribute('data-label', original);
        label.textContent = 'copied ✓';
        btn.classList.add('copied');
        setTimeout(() => {
          label.textContent = btn.getAttribute('data-label') || original;
          btn.classList.remove('copied');
        }, 1200);
      }
    });
  });

})();
