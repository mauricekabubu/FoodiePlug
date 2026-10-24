(function () {
  'use strict';

  var form = document.getElementById('forgot-password-form');
  var submitBtn = document.getElementById('submit-btn');

  if (form) {
    form.addEventListener('submit', function () {
      submitBtn.classList.add('is-loading');
      submitBtn.disabled = true;
      var label = submitBtn.querySelector('.btn-label');
      if (label) label.textContent = 'Sending…';
    });
  }

  /* ---------------- food photo carousel (mirrors login.js) ---------------- */

  var carousel = document.getElementById('foodCarousel');
  if (carousel) {
    var slides = carousel.querySelectorAll('.food-slide');
    var dots = carousel.querySelectorAll('.carousel-dot');
    var current = 0;
    var timer = null;

    function goTo(index) {
      slides[current] && slides[current].classList.remove('active');
      dots[current] && dots[current].classList.remove('active');
      current = index % slides.length;
      slides[current] && slides[current].classList.add('active');
      dots[current] && dots[current].classList.add('active');
    }
    function start() {
      if (slides.length < 2) return;
      timer = window.setInterval(function () { goTo(current + 1); }, 5000);
    }
    function stop() { if (timer) window.clearInterval(timer); }

    var prefersReducedMotion =
      window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (!prefersReducedMotion) {
      start();
      document.addEventListener('visibilitychange', function () {
        if (document.hidden) stop(); else start();
      });
    }
  }
})();