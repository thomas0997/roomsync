/* ============================================================
   ROOMSYNC — notes.js
   Filter pills show/hide file cards by data-type. New Doc/Sheet/
   Upload are stubbed until there's a backend to actually create
   or store files.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  var filterPills = document.querySelectorAll('.notes-filter-pill');
  var fileCards = document.querySelectorAll('.notes-file-card');

  filterPills.forEach(function (pill) {
    pill.addEventListener('click', function () {
      var filter = pill.dataset.filter;

      filterPills.forEach(function (p) { p.classList.remove('notes-filter-active'); });
      pill.classList.add('notes-filter-active');

      fileCards.forEach(function (card) {
        var show = filter === 'all' || card.dataset.type === filter;
        card.style.display = show ? '' : 'none';
      });
    });
  });

  var quickCards = document.querySelectorAll('.notes-quick-card');
  quickCards.forEach(function (card) {
    card.addEventListener('click', function () {
      // TODO: wire up real doc/sheet creation and file upload once the backend exists
      console.log('Quick action clicked — hook up file creation/upload here.');
    });
  });

  var fileCardButtons = document.querySelectorAll('.notes-file-card');
  fileCardButtons.forEach(function (card) {
    card.addEventListener('click', function () {
      // TODO: open the actual file/doc once the backend exists
      console.log('File card clicked:', card.querySelector('.notes-file-name').textContent);
    });
  });

});/* ============================================================
   ROOMSYNC — notes.js
   Filter pills show/hide file cards by data-type. New Doc/Sheet/
   Upload are stubbed until there's a backend to actually create
   or store files.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  var filterPills = document.querySelectorAll('.notes-filter-pill');
  var fileCards = document.querySelectorAll('.notes-file-card');

  filterPills.forEach(function (pill) {
    pill.addEventListener('click', function () {
      var filter = pill.dataset.filter;

      filterPills.forEach(function (p) { p.classList.remove('notes-filter-active'); });
      pill.classList.add('notes-filter-active');

      fileCards.forEach(function (card) {
        var show = filter === 'all' || card.dataset.type === filter;
        card.style.display = show ? '' : 'none';
      });
    });
  });

  var quickCards = document.querySelectorAll('.notes-quick-card');
  quickCards.forEach(function (card) {
    card.addEventListener('click', function () {
      // TODO: wire up real doc/sheet creation and file upload once the backend exists
      console.log('Quick action clicked — hook up file creation/upload here.');
    });
  });

  var fileCardButtons = document.querySelectorAll('.notes-file-card');
  fileCardButtons.forEach(function (card) {
    card.addEventListener('click', function () {
      // TODO: open the actual file/doc once the backend exists
      console.log('File card clicked:', card.querySelector('.notes-file-name').textContent);
    });
  });

});