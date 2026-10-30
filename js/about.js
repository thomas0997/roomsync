/* ============================================================
   ROOMSYNC — about.js
   Switches between the three About panels client-side (no page
   reload). Feedback and Contact send to the API.
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

  // Feedback and Contact send to the API (POST /feedback, POST /contact). No login needed.
  var apiBase = (window.ROOMSYNC && window.ROOMSYNC.API_BASE) || '';

  async function sendForm(form, path, fields, okMessage) {
    var button = form.querySelector('.abt-btn-submit');
    var payload = {};
    fields.forEach(function (name) {
      var input = form.elements[name];
      var value = input ? input.value.trim() : '';
      if (name === 'rating') { payload[name] = parseInt(value, 10); return; }
      if (name === 'room' && !value) { return; }          // the room is optional
      payload[name] = value;
    });
    button.disabled = true;
    try {
      var res = await fetch(apiBase + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.status === 204) { form.reset(); showToast(okMessage); }
      else if (res.status === 429) { showToast('Too many messages. Please try again in a while.'); }
      else if (res.status === 422) { showToast('Please check the form and try again.'); }
      else { showToast('Something went wrong. Please try again.'); }
    } catch (e) {
      showToast("Couldn't reach the server. Check your connection.");
    } finally {
      button.disabled = false;
    }
  }

  // If you are logged in, start with your name filled in (Reset keeps it).
  var knownName = '';
  try { knownName = (JSON.parse(localStorage.getItem('roomsync_user') || '{}').name || ''); } catch (e) { knownName = ''; }

  var feedbackForm = document.getElementById('feedbackForm');
  if (feedbackForm) {
    if (knownName) { feedbackForm.elements.name.defaultValue = knownName; feedbackForm.elements.name.value = knownName; }
    feedbackForm.addEventListener('submit', function (e) {
      e.preventDefault();
      sendForm(feedbackForm, '/feedback', ['name', 'room', 'rating', 'message', 'website'], 'Thanks for the feedback!');
    });
  }

  var contactForm = document.getElementById('contactForm');
  if (contactForm) {
    if (knownName) { contactForm.elements.name.defaultValue = knownName; contactForm.elements.name.value = knownName; }
    contactForm.addEventListener('submit', function (e) {
      e.preventDefault();
      sendForm(contactForm, '/contact', ['name', 'email', 'message', 'website'], "Message sent. We'll get back to you soon!");
    });
  }

});
