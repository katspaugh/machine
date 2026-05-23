/* machine — site interactions
 * - nav-stuck on scroll
 * - reveal-on-scroll
 * - copy buttons (one-liner + hero CTA)
 * - asciinema-style demo player (typewriter)
 */
(function () {
  'use strict';

  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

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

  // ---------- Demo player ----------
  // A sequence of frames. Each frame: { d: delay-ms-before, t: text or html, c: optional CSS class }
  // We render plain spans into the demo body. The cursor sits at the end.
  const demoBody = document.getElementById('demo-body');
  const demoClock = document.getElementById('demo-clock');
  const demoRestart = document.getElementById('demo-restart');

  if (demoBody) {
    const TOTAL = 38; // seconds, shown in clock
    const script = [
      // [type, payload, delay-ms-after]
      { type: 'prompt' },
      { type: 'type', text: 'machine up blog', cls: 'cmd', speed: 28 },
      { type: 'wait', ms: 220 },
      { type: 'nl' },
      { type: 'line', html: '<span class="dim">→</span> <span class="muted">project</span>   blog' },
      { type: 'line', html: '<span class="dim">→</span> <span class="muted">profile</span>   python · cypress' },
      { type: 'line', html: '<span class="dim">→</span> <span class="muted">image</span>     ubuntu-24.04-arm64' },
      { type: 'line', html: '<span class="dim">→</span> <span class="muted">disk</span>      20G  <span class="dim">·</span>  <span class="muted">cpu</span> 4  <span class="dim">·</span>  <span class="muted">mem</span> 8G' },
      { type: 'wait', ms: 320 },
      { type: 'line', html: '' },
      { type: 'line', html: '<span class="muted">[1/4]</span> boot ………………………… <span class="ok">ok</span>  <span class="dim">4.1s</span>' },
      { type: 'wait', ms: 320 },
      { type: 'line', html: '<span class="muted">[2/4]</span> base image …………… <span class="ok">ok</span>  <span class="dim">12.0s</span>' },
      { type: 'wait', ms: 240 },
      { type: 'line', html: '<span class="muted">[3/4]</span> provision ……………… <span class="ok">ok</span>  <span class="dim">18.6s</span>' },
      { type: 'wait', ms: 180 },
      { type: 'line', html: '<span class="muted">[4/4]</span> ssh handshake …… <span class="ok">ok</span>  <span class="dim">0.4s</span>' },
      { type: 'wait', ms: 280 },
      { type: 'line', html: '' },
      { type: 'line', html: '<span class="ok">✓</span> <span class="cmd">vm</span> running  <span class="dim">·</span>  <span class="muted">host</span> <span class="user">machine-blog</span>  <span class="dim">·</span>  <span class="muted">port</span> 60010' },
      { type: 'line', html: '<span class="ok">✓</span> <span class="cmd">agent</span> forwarded   <span class="dim">·</span>  $XDG_RUNTIME_DIR/dev-secrets (tmpfs)' },
      { type: 'wait', ms: 260 },
      { type: 'line', html: '' },
      { type: 'prompt' },
      { type: 'type', text: 'machine ssh blog', cls: 'cmd', speed: 28 },
      { type: 'wait', ms: 200 },
      { type: 'nl' },
      { type: 'line', html: '<span class="user">you</span>@<span class="host">blog</span>:<span class="muted">/workspace</span><span class="dim">$</span>' }
    ];

    let timeline = []; // array of millisecond positions per step for the clock
    let totalMs = 0;
    let cancelToken = 0;
    let elapsedTimer = null;

    function clear() {
      demoBody.innerHTML = '';
    }
    function appendHTML(html) {
      const span = document.createElement('span');
      span.innerHTML = html;
      demoBody.appendChild(span);
    }
    function appendText(text, cls) {
      const span = document.createElement('span');
      if (cls) span.className = cls;
      span.textContent = text;
      demoBody.appendChild(span);
    }
    function appendCursor() {
      const c = document.createElement('span');
      c.className = 'cursor';
      demoBody.appendChild(c);
    }
    function removeCursor() {
      const c = demoBody.querySelector('.cursor');
      if (c) c.remove();
    }
    function newline() {
      demoBody.appendChild(document.createTextNode('\n'));
    }
    function sleep(ms) {
      return new Promise((res) => setTimeout(res, ms));
    }

    function fmt(s) {
      const m = Math.floor(s / 60).toString().padStart(2, '0');
      const ss = Math.floor(s % 60).toString().padStart(2, '0');
      return `${m}:${ss}`;
    }
    function setClock(elapsedSec) {
      if (!demoClock) return;
      demoClock.textContent = `${fmt(elapsedSec)} / ${fmt(TOTAL)}`;
    }
    function startClock() {
      if (elapsedTimer) clearInterval(elapsedTimer);
      const startedAt = performance.now();
      setClock(0);
      elapsedTimer = setInterval(() => {
        const s = Math.min(TOTAL, (performance.now() - startedAt) / 1000);
        setClock(s);
      }, 250);
    }
    function stopClock() {
      if (elapsedTimer) clearInterval(elapsedTimer);
    }

    async function play() {
      const token = ++cancelToken;
      clear();
      startClock();
      for (const step of script) {
        if (token !== cancelToken) return;

        if (step.type === 'prompt') {
          removeCursor();
          appendHTML('<span class="dim">$</span> ');
          appendCursor();
          continue;
        }
        if (step.type === 'type') {
          removeCursor();
          const span = document.createElement('span');
          if (step.cls) span.className = step.cls;
          demoBody.appendChild(span);
          appendCursor();
          const speed = reduced ? 1 : (step.speed || 30);
          for (let i = 0; i < step.text.length; i++) {
            if (token !== cancelToken) return;
            span.textContent += step.text[i];
            await sleep(speed + (reduced ? 0 : Math.random() * 28));
          }
          continue;
        }
        if (step.type === 'nl') {
          removeCursor();
          newline();
          continue;
        }
        if (step.type === 'line') {
          removeCursor();
          newline();
          appendHTML(step.html);
          continue;
        }
        if (step.type === 'wait') {
          await sleep(reduced ? 0 : (step.ms || 200));
          continue;
        }
      }
      // settle: leave a trailing prompt cursor
      removeCursor();
      appendCursor();
      stopClock();
      setClock(TOTAL);

      // loop with 2s pause unless reduced motion (then stop)
      if (!reduced) {
        await sleep(2000);
        if (token === cancelToken) play();
      }
    }

    // restart button
    if (demoRestart) {
      demoRestart.addEventListener('click', () => play());
    }

    // autoplay on first scroll-into-view
    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver(
        (entries) => {
          for (const e of entries) {
            if (e.isIntersecting) {
              play();
              io.disconnect();
            }
          }
        },
        { threshold: 0.3 }
      );
      io.observe(demoBody);
    } else {
      play();
    }
  }
})();
