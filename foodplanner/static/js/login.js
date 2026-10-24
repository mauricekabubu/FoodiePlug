(function () {
  'use strict';

  var form = document.getElementById('login-form');
  var usernameField = document.getElementById('username-field');
  var passwordField = document.getElementById('password-field');
  var usernameInput = document.getElementById('username');
  var passwordInput = document.getElementById('password');
  var togglePassword = document.getElementById('toggle-password');
  var submitBtn = document.getElementById('submit-btn');

  /* ---------------- password visibility toggle ---------------- */

  if (togglePassword && passwordInput) {
    togglePassword.addEventListener('click', function () {
      var isVisible = passwordInput.type === 'text';
      passwordInput.type = isVisible ? 'password' : 'text';
      togglePassword.setAttribute('aria-pressed', String(!isVisible));
      togglePassword.setAttribute(
        'aria-label',
        isVisible ? 'Show password' : 'Hide password'
      );
      // Keep focus on the field so keyboard users don't lose their place.
      passwordInput.focus({ preventScroll: true });
    });
  }

  /* ---------------- validation ---------------- */

  function setError(fieldEl, hasError) {
    if (!fieldEl) return;
    fieldEl.classList.toggle('has-error', hasError);
    var input = fieldEl.querySelector('input');
    if (input) input.setAttribute('aria-invalid', hasError ? 'true' : 'false');
  }

  function clearErrorOnInput(fieldEl, input) {
    if (!input) return;
    input.addEventListener('input', function () {
      if (input.value.trim().length > 0) {
        setError(fieldEl, false);
      }
    });
  }

  clearErrorOnInput(usernameField, usernameInput);
  clearErrorOnInput(passwordField, passwordInput);

  function validate() {
    var valid = true;

    if (!usernameInput.value.trim()) {
      setError(usernameField, true);
      valid = false;
    } else {
      setError(usernameField, false);
    }

    if (!passwordInput.value) {
      setError(passwordField, true);
      valid = false;
    } else {
      setError(passwordField, false);
    }

    return valid;
  }

  /* ---------------- submit / loading state ---------------- */

  if (form) {
    form.addEventListener('submit', function (event) {
      if (!validate()) {
        event.preventDefault();
        var firstInvalid = form.querySelector('.has-error input');
        if (firstInvalid) firstInvalid.focus();
        return;
      }

      // Let the real POST to /login/ proceed; just reflect a loading
      // state in case the response takes a moment (e.g. slow network).
      submitBtn.classList.add('is-loading');
      submitBtn.disabled = true;
    });
  }

  /* ---------------- food photo carousel ---------------- */

  var carousel = document.getElementById('foodCarousel');
  if (carousel) {
    var slides = carousel.querySelectorAll('.food-slide');
    var dots = carousel.querySelectorAll('.carousel-dot');
    var current = 0;
    var intervalMs = 5000;
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
      timer = window.setInterval(function () {
        goTo(current + 1);
      }, intervalMs);
    }

    function stop() {
      if (timer) window.clearInterval(timer);
    }

    var prefersReducedMotion =
      window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (!prefersReducedMotion) {
      start();
      document.addEventListener('visibilitychange', function () {
        if (document.hidden) stop();
        else start();
      });
    }
  }
})();
