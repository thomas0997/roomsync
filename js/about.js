/* ============================================================
   ROOMSYNC — about.js
   Switches between the three About panels client-side (no page
   reload). Feedback/Contact forms are stubbed until there's a
   backend to actually send anything.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  var tabs = document.querySelectorAll('.abt-tab');
  var panels = document.querySelectorAll('.abt-panel');
  var eyebrow = document.getElementById('abtEyebrow');
  var title = document.getElementById('abtTitle');
  var subtitle = document.getElementById('abtSubtitle');

  var heroText = {
    aboutus: {
      eyebrow: 'ABOUT',
      title: 'The team behind <span class="dim">room</span>sync',
      subtitle: 'A group of students from Holy Angel University who joined forces to comply with requirements.<br>Built for the course 6IWEB.'
    },
    feedback: {
      eyebrow: 'FEEDBACK',
      title: "Tell us what's not working&hellip;",
      subtitle: 'Good, bad, or somewhere in between, we want to hear it.'
    },
    contact: {
      eyebrow: 'CONTACT US',
      title: 'Get in touch',
      subtitle: "Questions, bug reports, or just want to say hi? We're around."
    }
  };

  function activateTab(tabName) {
    tabs.forEach(function (t) {
      var isMatch = t.dataset.tab === tabName;
      t.classList.toggle('abt-tab-active', isMatch);
      t.setAttribute('aria-selected', isMatch ? 'true' : 'false');
    });
    panels.forEach(function (p) {
      var isMatch = p.dataset.panel === tabName;
      p.hidden = !isMatch;
      p.classList.toggle('abt-panel-active', isMatch);
    });

    var text = heroText[tabName];
    if (text) {
      eyebrow.textContent = text.eyebrow;
      title.innerHTML = text.title;
      subtitle.innerHTML = text.subtitle;
    }
  }

  tabs.forEach(function (tab) {
    tab.addEventListener('click', function () {
      activateTab(tab.dataset.tab);
    });
  });

  function showToast(message) {
    var toast = document.createElement('div');
    toast.className = 'abt-toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(function () {
      toast.classList.add('abt-toast-show');
    });
    setTimeout(function () {
      toast.classList.remove('abt-toast-show');
      setTimeout(function () { toast.remove(); }, 250);
    }, 2200);
  }

  var feedbackForm = document.getElementById('feedbackForm');
  if (feedbackForm) {
    feedbackForm.addEventListener('submit', function (e) {
      e.preventDefault();
      // TODO: send this to a real backend once one exists
      console.log('Feedback submitted (not actually sent anywhere yet).');
      showToast('Thanks for the feedback!');
      feedbackForm.reset();
    });
  }

  var contactForm = document.getElementById('contactForm');
  if (contactForm) {
    contactForm.addEventListener('submit', function (e) {
      e.preventDefault();
      // TODO: send this to a real backend once one exists
      console.log('Contact message submitted (not actually sent anywhere yet).');
      showToast("Message sent — we'll get back to you soon!");
      contactForm.reset();
    });
  }

});