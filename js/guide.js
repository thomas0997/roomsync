/* ============================================================
   ROOMSYNC — guide.js
   Highlights the table-of-contents link of the section you are reading.
   ============================================================ */
(function () {
  'use strict';
  var toc = document.querySelector('.gd-toc');
  if (!toc) { return; }
  var links = Array.prototype.slice.call(toc.querySelectorAll('a[href^="#"]'));
  var sections = links.map(function (a) { return document.getElementById(a.getAttribute('href').slice(1)); });

  function setActive(id) {
    links.forEach(function (a) {
      var on = a.getAttribute('href') === '#' + id;
      a.classList.toggle('gd-active', on);
      if (on) {
        a.setAttribute('aria-current', 'true');
        // On a phone the chips scroll sideways: keep the active one in view.
        if (toc.scrollWidth > toc.clientWidth) {
          toc.scrollTo({ left: a.offsetLeft - 18, behavior: 'smooth' });
        }
      } else {
        a.removeAttribute('aria-current');
      }
    });
  }

  function update() {
    var line = 150;   // a section counts as "current" once its top passes this line
    var current = sections[0];
    sections.forEach(function (sec) {
      if (sec && sec.getBoundingClientRect().top <= line) { current = sec; }
    });
    // Bottom of the page: the last section may be too short to reach the line.
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) {
      current = sections[sections.length - 1];
    }
    if (current) { setActive(current.id); }
  }

  var ticking = false;
  window.addEventListener('scroll', function () {
    if (ticking) { return; }
    ticking = true;
    window.requestAnimationFrame(function () { ticking = false; update(); });
  }, { passive: true });
  window.addEventListener('resize', update);
  update();
})();
