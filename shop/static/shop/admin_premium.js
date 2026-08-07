(function () {
  'use strict';

  // Force dark theme to match the premium palette
  var KEY = 'jazzmin-theme-mode';
  if (window.localStorage) {
    if (!localStorage.getItem(KEY)) {
      localStorage.setItem(KEY, 'dark');
    }
    var mode = localStorage.getItem(KEY) === 'light' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-bs-theme', mode);
  }

  function onReady(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  onReady(function () {
    var doc = document;

    // Fade entrance helper (companion to the CSS animation)
    var cards = doc.querySelectorAll('#changelist .card, .card');
    for (var i = 0; i < cards.length; i++) {
      cards[i].style.setProperty('animation-delay', (i * 60) + 'ms');
    }

    // Tab pills on the change form: keep active state after navigation
    var activeTab = window.location.hash;
    if (activeTab && doc.querySelector(activeTab)) {
      var target = doc.querySelector(activeTab);
      var trigger = doc.querySelector('a[data-bs-toggle="pill"][href="' + activeTab + '"]');
      if (trigger && typeof bootstrap !== 'undefined' && bootstrap.Tab) {
        new bootstrap.Tab(trigger).show();
      }
    }

    // Sticky-flip the sidebar brand glow on scroll
    var header = doc.querySelector('.app-header');
    var sidebar = doc.querySelector('.app-sidebar');
    if (header && window.addEventListener) {
      function onScroll() {
        if (window.scrollY > 8) {
          header.classList.add('admin-scrolled');
        } else {
          header.classList.remove('admin-scrolled');
        }
      }
      window.addEventListener('scroll', onScroll, { passive: true });
      onScroll();
    }

    // Gold focus glow for brand image
    var brandImg = doc.querySelector('.brand-link .brand-image');
    if (brandImg && sidebar) {
      sidebar.classList.add('admin-has-brand');
    }
  });
})();
