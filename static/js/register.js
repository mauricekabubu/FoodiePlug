(function () {
  'use strict';

  var form = document.getElementById('register-form');
  if (!form) return;

  var fields = {
    fullname: document.getElementById('fullname-field'),
    username: document.getElementById('username-field'),
    email: document.getElementById('email-field'),
    password: document.getElementById('password-field'),
    confirm: document.getElementById('confirm-password-field')
  };

  var inputs = {
    fullname: document.getElementById('fullname'),
    username: document.getElementById('username'),
    email: document.getElementById('email'),
    password: document.getElementById('password'),
    confirm: document.getElementById('confirm-password')
  };

  var termsRow = document.getElementById('terms-row');
  var termsCheckbox = document.getElementById('terms');
  var submitBtn = document.getElementById('submit-btn');
  var strengthMeter = document.getElementById('password-strength');

  /* ---------------- password visibility toggles ---------------- */

  document.querySelectorAll('.toggle-visibility').forEach(function (btn) {
    var targetId = btn.getAttribute('aria-controls');
    var input = document.getElementById(targetId);
    if (!input) return;

    btn.addEventListener('click', function () {
      var isVisible = input.type === 'text';
      input.type = isVisible ? 'password' : 'text';
      btn.setAttribute('aria-pressed', String(!isVisible));
      btn.setAttribute('aria-label', isVisible ? 'Show password' : 'Hide password');
      input.focus({ preventScroll: true });
    });
  });

  /* ---------------- error / valid state helpers ---------------- */

  function setError(fieldEl, hasError, message) {
    if (!fieldEl) return;
    fieldEl.classList.toggle('has-error', hasError);
    if (hasError) fieldEl.classList.remove('is-valid');
    var msgEl = fieldEl.querySelector('.error-msg');
    if (msgEl && message) msgEl.textContent = message;
    var input = fieldEl.querySelector('input');
    if (input) input.setAttribute('aria-invalid', hasError ? 'true' : 'false');
  }

  function setValid(fieldEl, isValid) {
    if (!fieldEl) return;
    fieldEl.classList.toggle('is-valid', isValid);
    if (isValid) fieldEl.classList.remove('has-error');
  }

  /* ---------------- field-level validators ---------------- */

  function validateFullname(showError) {
    var ok = inputs.fullname.value.trim().length > 0;
    if (showError) setError(fields.fullname, !ok, 'Please enter your full name.');
    return ok;
  }

  // Demo stand-in for a real availability check — replace with a debounced
  // fetch() to your backend (e.g. /api/check-username/?u=...).
  var TAKEN_USERNAMES = ['admin', 'foodieplug', 'test'];

  function validateUsername(showError) {
    var value = inputs.username.value.trim();
    if (!value) {
      if (showError) setError(fields.username, true, 'Please choose a username.');
      return false;
    }
    if (TAKEN_USERNAMES.indexOf(value.toLowerCase()) !== -1) {
      if (showError) setError(fields.username, true, 'Username is already taken.');
      return false;
    }
    setError(fields.username, false);
    if (showError) setValid(fields.username, true);
    return true;
  }

  function validateEmail(showError) {
    var value = inputs.email.value.trim();
    var pattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    var ok = pattern.test(value);
    if (showError) setError(fields.email, !ok, 'Please enter a valid email address.');
    return ok;
  }

  function passwordStrength(value) {
    if (!value) return 'none';
    var score = 0;
    if (value.length >= 8) score++;
    if (value.length >= 12) score++;
    if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score++;
    if (/\d/.test(value)) score++;
    if (/[^A-Za-z0-9]/.test(value)) score++;

    if (score <= 2) return 'weak';
    if (score <= 3) return 'medium';
    return 'strong';
  }

  function updateStrengthMeter() {
    var value = inputs.password.value;
    fields.password.classList.toggle('has-value', value.length > 0);
    if (!strengthMeter) return;
    var level = passwordStrength(value);
    var labelEl = strengthMeter.querySelector('.strength-label');
    if (level === 'none') {
      strengthMeter.removeAttribute('data-strength');
      if (labelEl) labelEl.textContent = '';
      return;
    }
    strengthMeter.setAttribute('data-strength', level);
    if (labelEl) {
      labelEl.textContent =
        level === 'weak' ? 'Weak password' :
        level === 'medium' ? 'Medium strength' :
        'Strong password';
    }
  }

  function validatePassword(showError) {
    var value = inputs.password.value;
    var ok = value.length >= 8;
    if (showError) setError(fields.password, !ok, 'Password must be at least 8 characters.');
    return ok;
  }

  function validateConfirm(showError) {
    var value = inputs.confirm.value;
    if (!value) {
      if (showError) setError(fields.confirm, true, 'Please confirm your password.');
      return false;
    }
    var matches = value === inputs.password.value;
    if (showError) {
      setError(fields.confirm, !matches, "Passwords don't match.");
      if (matches) setValid(fields.confirm, true);
    }
    return matches;
  }

  function validateTerms(showError) {
    var ok = termsCheckbox.checked;
    if (termsRow) termsRow.classList.toggle('has-error', showError && !ok);
    return ok;
  }

  /* ---------------- live feedback as the user types ---------------- */

  inputs.fullname.addEventListener('input', function () {
    if (fields.fullname.classList.contains('has-error')) validateFullname(true);
  });

  inputs.username.addEventListener('input', function () {
    fields.username.classList.remove('is-valid');
    if (fields.username.classList.contains('has-error')) validateUsername(true);
  });
  inputs.username.addEventListener('blur', function () { validateUsername(true); });

  inputs.email.addEventListener('input', function () {
    if (fields.email.classList.contains('has-error')) validateEmail(true);
  });

  inputs.password.addEventListener('input', function () {
    updateStrengthMeter();
    if (fields.password.classList.contains('has-error')) validatePassword(true);
    if (inputs.confirm.value) validateConfirm(true);
  });

  inputs.confirm.addEventListener('input', function () {
    validateConfirm(true);
  });

  termsCheckbox.addEventListener('change', function () {
    if (termsCheckbox.checked) validateTerms(true);
  });

  /* ---------------- submit ---------------- */

  form.addEventListener('submit', function (event) {
    var validFullname = validateFullname(true);
    var validUsername = validateUsername(true);
    var validEmail = validateEmail(true);
    var validPassword = validatePassword(true);
    var validConfirm = validateConfirm(true);
    var validTerms = validateTerms(true);

    var allValid = validFullname && validUsername && validEmail &&
      validPassword && validConfirm && validTerms;

    if (!allValid) {
      event.preventDefault();
      var firstInvalid = form.querySelector('.has-error input, .terms-row.has-error input');
      if (firstInvalid) firstInvalid.focus();
      return;
    }

    // Let the real POST to /register/ proceed; reflect a loading state
    // in case the response takes a moment.
    submitBtn.classList.add('is-loading');
    submitBtn.disabled = true;
    var label = submitBtn.querySelector('.btn-label');
    if (label) label.textContent = 'Creating account…';
  });

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