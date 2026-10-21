/* ============================================================
   ROOMSYNC — landing.js
   Landing page animation (particles + scroll-scrubbing). This used to be an
   inline <script> in pages/index.html; it lives in a file so the Content
   Security Policy can forbid inline scripts.
   ============================================================ */

/* ---------- Small floating particles behind the hero ----------
   Colored using RoomSync's own locked task-type palette (Exam,
   Quiz, Case Study, Activity, Seatwork, Assignment) — the same
   dots already used in the calendar legend — so this ties back
   to the product's real visual language instead of being generic
   decoration. Varied size/position/speed/path per particle. */
(function () {
  var field = document.getElementById('particleField');
  if (!field) return;
  var colors = ['#DF0000', '#F2B84B', '#C79ADB', '#F2795A', '#009CDF', '#8F8F97'];
  var count = 16;
  for (var i = 0; i < count; i++) {
    var p = document.createElement('span');
    p.className = 'land-particle';
    var size = 5 + Math.random() * 6;
    var top = Math.random() * 100;
    var left = Math.random() * 100;
    var duration = 12 + Math.random() * 14;
    var delay = Math.random() * -20;
    var opacity = 0.2 + Math.random() * 0.22;
    p.style.width = size + 'px';
    p.style.height = size + 'px';
    p.style.top = top + '%';
    p.style.left = left + '%';
    p.style.opacity = opacity;
    p.style.background = colors[i % colors.length];
    p.style.animation = 'land-particle-float ' + duration + 's ease-in-out infinite';
    p.style.animationDelay = delay + 's';
    p.style.setProperty('--px1', (Math.random() * 60 - 30) + 'px');
    p.style.setProperty('--py1', (Math.random() * -60 - 15) + 'px');
    p.style.setProperty('--px2', (Math.random() * 60 - 30) + 'px');
    p.style.setProperty('--py2', (Math.random() * -100 - 30) + 'px');
    p.style.setProperty('--px3', (Math.random() * 60 - 30) + 'px');
    p.style.setProperty('--py3', (Math.random() * -45 - 10) + 'px');
    field.appendChild(p);
  }
})();

/* ---------- Scroll-scrubbing engine ----------
   Each "pin track" is a tall element; the visual content inside
   it is position:sticky, so it stays on screen while you scroll
   through the tall track. We read how far you've scrolled through
   THAT SPECIFIC track (0 to 1) and map it directly to transforms —
   this is what makes it scrub instead of just fade in once. */

function trackProgress(track) {
  var rect = track.getBoundingClientRect();
  var scrollableDistance = track.offsetHeight - window.innerHeight;
  if (scrollableDistance <= 0) return 0;
  var scrolled = -rect.top;
  return Math.min(Math.max(scrolled / scrollableDistance, 0), 1);
}
function lerp(a, b, t) { return a + (b - a) * t; }
function clamp01(v) { return Math.min(Math.max(v, 0), 1); }

var heroTrack = document.getElementById('heroTrack');
var heroText = document.getElementById('heroText');
var heroShot = document.getElementById('heroShot');
var scrollHint = document.getElementById('scrollHint');
var featureTracks = Array.prototype.slice.call(document.querySelectorAll('[data-feature]'));

function render() {

  var p = trackProgress(heroTrack);
  var textP = clamp01(p / 0.45);
  heroText.style.opacity = 1 - textP;
  heroText.style.transform = 'scale(' + lerp(1, 0.85, textP) + ') translateY(' + lerp(0, -40, textP) + 'px)';
  scrollHint.style.opacity = 1 - clamp01(p / 0.15);

  var shotP = clamp01((p - 0.15) / 0.7);
  heroShot.style.opacity = shotP;
  heroShot.style.transform =
    'perspective(1400px) rotateX(' + lerp(35, 0, shotP) + 'deg) ' +
    'scale(' + lerp(0.75, 1, shotP) + ') ' +
    'translateY(' + lerp(120, 0, shotP) + 'px)';

  // Each feature section: label + title fade/rise in during the
  // first third, shot scales up + rises during the middle third,
  // everything holds pinned, then the NEXT section takes over.
  featureTracks.forEach(function (track) {
    var fp = trackProgress(track);
    var label = track.querySelector('[data-f-label]');
    var title = track.querySelector('[data-f-title]');
    var shot = track.querySelector('[data-f-shot]');

    var textIn = clamp01(fp / 0.25);
    label.style.opacity = textIn;
    label.style.transform = 'translateY(' + lerp(16, 0, textIn) + 'px)';
    title.style.opacity = textIn;
    title.style.transform = 'translateY(' + lerp(20, 0, textIn) + 'px)';

    if (shot) {
      var shotIn = clamp01((fp - 0.15) / 0.4);
      shot.style.opacity = shotIn;
      shot.style.transform = 'scale(' + lerp(0.9, 1, shotIn) + ') translateY(' + lerp(50, 0, shotIn) + 'px)';
    }

    var cardStack = track.querySelector('[data-f-cardstack]');
    if (cardStack) {
      var cards = cardStack.querySelectorAll('[data-card]');
      var stackStart = 0.2, stackEnd = 0.95;
      var slice = (stackEnd - stackStart) / cards.length;
      cards.forEach(function (card, i) {
        var cardP = clamp01((fp - (stackStart + i * slice)) / (slice * 0.7));
        card.style.opacity = cardP;
        card.style.transform = 'translateY(' + lerp(28, 0, cardP) + 'px) scale(' + lerp(0.97, 1, cardP) + ')';
      });
    }
  });
}

var ticking = false;
window.addEventListener('scroll', function () {
  if (!ticking) {
    requestAnimationFrame(function () { render(); ticking = false; });
    ticking = true;
  }
});
render();


var revealTargets = document.querySelectorAll('.land-t-card, #closingH2, #closingBtn');
var observer = new IntersectionObserver(function (entries) {
  entries.forEach(function (entry) {
    if (entry.isIntersecting) entry.target.classList.add('land-in');
  });
}, { threshold: 0.2 });
revealTargets.forEach(function (el) { observer.observe(el); });

document.querySelectorAll('.land-room-dots').forEach(function (group) {
  var dots = group.querySelectorAll('.land-room-dot');
  var groupObserver = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        dots.forEach(function (dot, i) {
          setTimeout(function () { dot.classList.add('land-in'); }, i * 130);
        });
        groupObserver.disconnect();
      }
    });
  }, { threshold: 0.4 });
  groupObserver.observe(group);
});