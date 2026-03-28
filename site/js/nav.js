// nav.js — scroll spy + mobile hamburger with focus trap
(function () {
  var sections = document.querySelectorAll('section[id]');
  var links = document.querySelectorAll('nav .links a');

  function onScroll() {
    if (window.location.pathname !== '/' && window.location.pathname !== '/index.html') return;
    var current = '';
    sections.forEach(function (sec) {
      if (sec.getBoundingClientRect().top <= 80) current = sec.id;
    });
    links.forEach(function (a) {
      a.classList.toggle('active', a.getAttribute('href') === '#' + current);
    });
  }
  document.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  var nav = document.getElementById('main-nav');
  var burger = document.getElementById('nav-burger');
  var backdrop = document.getElementById('nav-backdrop');
  var _prevFocus = null;

  function openMenu() {
    _prevFocus = document.activeElement;
    nav.classList.add('nav-open');
    burger.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
    var firstLink = nav.querySelector('#nav-links a');
    if (firstLink) firstLink.focus();
  }

  function closeMenu() {
    nav.classList.remove('nav-open');
    burger.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
    if (_prevFocus) _prevFocus.focus();
  }

  if (nav && burger) {
    burger.addEventListener('click', function () {
      nav.classList.contains('nav-open') ? closeMenu() : openMenu();
    });
    if (backdrop) backdrop.addEventListener('click', closeMenu);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && nav.classList.contains('nav-open')) closeMenu();
    });
    nav.addEventListener('keydown', function (e) {
      if (e.key !== 'Tab' || !nav.classList.contains('nav-open')) return;
      var focusable = nav.querySelectorAll('#nav-links a, .nav-burger');
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    });
    document.querySelectorAll('#nav-links a').forEach(function (a) {
      a.addEventListener('click', closeMenu);
    });
  }
})();
