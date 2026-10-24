(function () {
  'use strict';

  /* ---------------- mobile "On this page" collapse/expand ---------------- */

  var toc = document.querySelector('.toc');
  var toggle = document.querySelector('.toc-toggle');

  if (toc && toggle) {
    toggle.addEventListener('click', function () {
      var isOpen = toc.getAttribute('data-open') === 'true';
      toc.setAttribute('data-open', String(!isOpen));
      toggle.setAttribute('aria-expanded', String(!isOpen));
    });

    // Collapse automatically once the viewport is wide enough that the
    // desktop sticky TOC takes over, so state doesn't carry over on resize.
    var desktopQuery = window.matchMedia('(min-width: 901px)');
    function syncForViewport(e) {
      if (e.matches) {
        toc.removeAttribute('data-open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    }
    desktopQuery.addEventListener('change', syncForViewport);
  }

  /* ---------------- tap a TOC link on mobile: collapse after navigating ---------------- */

  var tocLinks = document.querySelectorAll('.toc-list a');
  tocLinks.forEach(function (link) {
    link.addEventListener('click', function () {
      if (window.matchMedia('(max-width: 900px)').matches && toc) {
        toc.setAttribute('data-open', 'false');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
      }
    });
  });

  /* ---------------- scroll-spy: highlight the active TOC entry ---------------- */

  var sections = document.querySelectorAll('.legal-doc section[id]');
  if (sections.length && tocLinks.length && 'IntersectionObserver' in window) {
    var linkById = {};
    tocLinks.forEach(function (link) {
      var id = link.getAttribute('href').replace('#', '');
      linkById[id] = link;
    });

    var activeId = null;

    function setActive(id) {
      if (id === activeId) return;
      activeId = id;
      tocLinks.forEach(function (link) { link.classList.remove('active'); });
      if (linkById[id]) linkById[id].classList.add('active');
    }

    var observer = new IntersectionObserver(
      function (entries) {
        var visible = entries
          .filter(function (e) { return e.isIntersecting; })
          .sort(function (a, b) { return a.boundingClientRect.top - b.boundingClientRect.top; });

        if (visible.length > 0) {
          setActive(visible[0].target.id);
        }
      },
      {
        rootMargin: '-96px 0px -70% 0px',
        threshold: 0
      }
    );

    sections.forEach(function (section) { observer.observe(section); });

    // Set the first section active on load.
    setActive(sections[0].id);
  }
})();