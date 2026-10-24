/**
 * FoodiePlug — Settings page script
 * static/js/settings.js
 *
 *   - section panels: show one section at a time (all sections stay visible without JS)
 *   - theme picker: uses the same 'foodieplug-theme' key and data-theme attribute as the rest of the app
 *   - unsaved-changes tracking, "Cancel changes" reset, and a warning before leaving
 *   - double-submit protection
 *
 * Forms stay normal Django POSTs: the server decides whether anything was saved.
 */
(function () {
  'use strict';

  var page = document.getElementById('st-page');
  if (!page) return;

  function $(id) { return document.getElementById(id); }
  function all(selector, root) { return [].slice.call((root || document).querySelectorAll(selector)); }

  /* ------------------------------------------------------------------ section panels */
  var panels = all('[data-panel]');
  var navLinks = all('[data-nav]');
  var picker = $('st-select');
  var ids = panels.map(function (p) { return p.id; });

  function show(id, userInitiated) {
    if (ids.indexOf(id) === -1) id = ids[0];

    panels.forEach(function (p) { p.hidden = p.id !== id; });
    navLinks.forEach(function (a) {
      if (a.dataset.nav === id) a.setAttribute('aria-current', 'true');
      else a.removeAttribute('aria-current');
    });
    if (picker) picker.value = id;

    if (userInitiated) {
      var panel = $(id);
      if (panel && panel.getBoundingClientRect().top < 0) panel.scrollIntoView({ block: 'start' });
    }
  }

  if (panels.length) {
    var fromHash = window.location.hash.replace('#', '');
    show(ids.indexOf(fromHash) > -1 ? fromHash : (page.dataset.activeSection || ids[0]), false);

    window.addEventListener('hashchange', function () {
      show(window.location.hash.replace('#', ''), true);
    });

    if (picker) {
      picker.addEventListener('change', function () {
        window.location.hash = picker.value;          // triggers hashchange; Back button works
      });
    }
  }

  /* ------------------------------------------------------------------ theme picker */
  var KEY = 'foodieplug-theme';
  var radios = all('input[name="theme"]');
  var themeStatus = $('st-theme-status');
  var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function storedTheme() {
    try { return localStorage.getItem(KEY) || 'system'; } catch (e) { return 'system'; }
  }

  function applyTheme(pref) {
    var resolved = pref === 'system' ? (media && media.matches ? 'dark' : 'light') : pref;
    document.documentElement.setAttribute('data-theme', resolved);

    // keep the sidebar's own theme buttons in step
    all('[data-theme-value]').forEach(function (btn) {
      btn.setAttribute('aria-pressed', btn.dataset.themeValue === pref ? 'true' : 'false');
    });
  }

  if (radios.length) {
    var current = storedTheme();
    radios.forEach(function (r) { r.checked = r.value === current; });

    radios.forEach(function (radio) {
      radio.addEventListener('change', function () {
        if (!radio.checked) return;
        var saved = true;
        try { localStorage.setItem(KEY, radio.value); } catch (e) { saved = false; }

        applyTheme(radio.value);

        if (themeStatus) {
          themeStatus.className = 'st-status ' + (saved ? 'is-ok' : 'is-dirty');
          themeStatus.textContent = saved
            ? 'Saved on this device: ' + radio.value.charAt(0).toUpperCase() + radio.value.slice(1) + '.'
            : 'Applied for now, but your browser blocked saving it.';
        }
      });
    });

    if (media) {
      var onSystemChange = function () { if (storedTheme() === 'system') applyTheme('system'); };
      if (media.addEventListener) media.addEventListener('change', onSystemChange);
      else if (media.addListener) media.addListener(onSystemChange);
    }
  }

  /* ------------------------------------------------------------------ unsaved changes + submit guard */
  var forms = all('form[data-settings-form]');
  var submitting = false;

  function isDirty(form) {
    return all('input, textarea, select', form).some(function (field) {
      if (field.type === 'hidden' || field.type === 'submit' || field.disabled) return false;
      if (field.type === 'checkbox' || field.type === 'radio') return field.checked !== field.defaultChecked;
      return field.value !== field.defaultValue;
    });
  }

  function anyDirty() { return forms.some(isDirty); }

  forms.forEach(function (form) {
    var status = form.querySelector('.st-status');

    function refresh() {
      if (!status) return;
      if (isDirty(form)) {
        status.className = 'st-status is-dirty';
        status.textContent = 'Unsaved changes';
      } else {
        status.className = 'st-status';
        status.textContent = '';
      }
    }

    form.addEventListener('input', refresh);
    form.addEventListener('change', refresh);
    form.addEventListener('reset', function () { setTimeout(refresh, 0); });

    form.addEventListener('submit', function (e) {
      if (form.dataset.submitting === '1') { e.preventDefault(); return; }
      form.dataset.submitting = '1';
      submitting = true;

      var btn = form.querySelector('button[type="submit"]');
      if (btn) { btn.dataset.label = btn.textContent; btn.disabled = true; btn.textContent = 'Saving\u2026'; }
      if (status) { status.className = 'st-status'; status.textContent = 'Saving\u2026'; }
    });
  });

  window.addEventListener('beforeunload', function (e) {
    if (submitting || !anyDirty()) return;
    e.preventDefault();
    e.returnValue = '';
  });

  // Back/forward cache: undo the "Saving…" state
  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    submitting = false;
    forms.forEach(function (form) {
      form.dataset.submitting = '';
      var btn = form.querySelector('button[type="submit"]');
      if (btn) { btn.disabled = false; if (btn.dataset.label) btn.textContent = btn.dataset.label; }
      var status = form.querySelector('.st-status');
      if (status) { status.className = 'st-status'; status.textContent = ''; }
    });
  });
})();