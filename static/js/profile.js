/**
 * FoodiePlug — Settings page script
 * static/js/settings.js
 *
 * Owns Settings-page behaviour only (dashboard.js stays global):
 *   - section navigation (one section at a time; all sections stay visible without JS)
 *   - theme picker: delegates to the global sidebar toggle, so there is one theme mechanism
 *   - avatar preview / "keep current photo"
 *   - unsaved-changes status + leave-page warning
 *   - double-submit protection
 *
 * Every form is a normal Django POST. Nothing here calls preventDefault on a real submit.
 */
(function () {
  'use strict';

  var page = document.getElementById('st-page');
  if (!page) return;

  function $(id) { return document.getElementById(id); }
  function all(sel, root) { return [].slice.call((root || document).querySelectorAll(sel)); }

  function toast(message, level) {
    level = level || 'success';
    if (typeof window.showToast === 'function') { window.showToast(message, level); return; }
    var container = $('toast-container');
    if (!container) return;
    var t = document.createElement('div');
    t.className = 'toast toast-' + level;
    t.textContent = message;
    container.appendChild(t);
    setTimeout(function () { t.remove(); }, 4000);
  }

  /* ------------------------------------------------------------------ section navigation */
  var panels = all('[data-panel]', page);
  var links = all('.st-nav [data-section]', page);
  var valid = panels.map(function (p) { return p.dataset.panel; });

  function show(name, updateHash) {
    if (valid.indexOf(name) === -1) name = valid[0];

    panels.forEach(function (p) { p.hidden = p.dataset.panel !== name; });
    links.forEach(function (a) {
      var on = a.dataset.section === name;
      a.classList.toggle('is-active', on);
      if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });

    if (updateHash && window.history && history.replaceState) {
      history.replaceState(null, '', '#' + name);
    }
  }

  page.classList.add('st-js');            // CSS only hides panels once JS is running

  var initial = (location.hash || '').replace('#', '') || page.dataset.active || valid[0];
  show(initial, false);

  links.forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault();
      show(a.dataset.section, true);
      var panel = $(a.dataset.section);
      if (panel && panel.scrollIntoView) panel.scrollIntoView({ block: 'start' });
    });
  });

  all('[data-section-link]', page).forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault();
      show(a.dataset.sectionLink, true);
    });
  });

  window.addEventListener('hashchange', function () {
    var name = (location.hash || '').replace('#', '');
    if (valid.indexOf(name) > -1) show(name, false);
  });

  /* ------------------------------------------------------------------ theme picker */
  var themeButtons = all('[data-st-theme]', page);
  var themeStatus = $('st-theme-status');

  function storedTheme() {
    try { return localStorage.getItem('foodieplug-theme') || 'system'; } catch (e) { return 'system'; }
  }

  function paintTheme() {
    var current = storedTheme();
    themeButtons.forEach(function (b) {
      b.setAttribute('aria-pressed', b.dataset.stTheme === current ? 'true' : 'false');
    });
  }

  themeButtons.forEach(function (b) {
    b.addEventListener('click', function () {
      var value = b.dataset.stTheme;
      var global = document.querySelector('.theme-toggle [data-theme-value="' + value + '"]');

      if (global) {
        global.click();                       // the app's own toggle sets storage, data-theme and its state
      } else {                                // fallback if the sidebar toggle isn't on the page
        try { localStorage.setItem('foodieplug-theme', value); } catch (e) {}
        var resolved = value === 'system'
          ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
          : value;
        document.documentElement.setAttribute('data-theme', resolved);
      }

      window.setTimeout(function () {
        paintTheme();
        if (themeStatus) themeStatus.textContent = 'Theme set to ' + b.querySelector('.st-theme-name').textContent + '.';
      }, 0);
    });
  });

  paintTheme();

  /* ------------------------------------------------------------------ avatar preview */
  var fileInput = $('id_avatar');
  var avatarImg = $('st-avatar-img');
  var avatarInitial = $('st-avatar-initial');
  var removeBox = $('id_remove_avatar');
  var MAX_BYTES = 5 * 1024 * 1024;           // friendly early warning only; the server is the real check

  function resetAvatar() {
    if (!avatarImg) return;
    if (avatarImg.dataset.currentSrc) {
      avatarImg.src = avatarImg.dataset.currentSrc;
      avatarImg.hidden = false;
    } else {
      avatarImg.removeAttribute('src');
      avatarImg.hidden = true;
      if (avatarInitial) avatarInitial.hidden = false;
    }
  }

  if (fileInput && avatarImg) {
    fileInput.addEventListener('change', function () {
      var file = fileInput.files && fileInput.files[0];
      if (!file) { resetAvatar(); return; }

      if (!/^image\/(jpeg|png|webp)$/.test(file.type)) {
        toast('Please choose a JPG, PNG or WebP image.', 'error');
        fileInput.value = ''; resetAvatar(); return;
      }
      if (file.size > MAX_BYTES) {
        toast('That image is over 5 MB. Please choose a smaller one.', 'error');
        fileInput.value = ''; resetAvatar(); return;
      }

      var reader = new FileReader();
      reader.onload = function (e) {
        avatarImg.src = e.target.result;
        avatarImg.hidden = false;
        if (avatarInitial) avatarInitial.hidden = true;
        if (removeBox) removeBox.checked = false;
      };
      reader.readAsDataURL(file);
    });
  }

  if (removeBox && fileInput) {
    removeBox.addEventListener('change', function () { if (removeBox.checked) { fileInput.value = ''; resetAvatar(); } });
  }

  /* ------------------------------------------------------------------ unsaved changes + double submit */
  var forms = all('form[data-settings-form]', page);
  var submitting = false;

  function statusOf(form) { return form.querySelector('.st-status'); }

  function setDirty(form, dirty) {
    form.dataset.dirty = dirty ? '1' : '';
    var s = statusOf(form);
    if (!s) return;
    s.className = 'st-status' + (dirty ? ' is-dirty' : '');
    s.textContent = dirty ? 'Unsaved changes' : '';
  }

  forms.forEach(function (form) {
    var submit = form.querySelector('button[type="submit"]');
    if (submit) submit.dataset.label = submit.textContent;

    form.addEventListener('input', function () { setDirty(form, true); });
    form.addEventListener('change', function () { setDirty(form, true); });

    form.addEventListener('reset', function () {
      window.setTimeout(function () { setDirty(form, false); resetAvatar(); }, 0);
    });

    form.addEventListener('submit', function (e) {
      if (form.dataset.submitting === '1') { e.preventDefault(); return; }
      form.dataset.submitting = '1';
      submitting = true;
      var s = statusOf(form);
      if (s) { s.className = 'st-status is-saving'; s.textContent = 'Saving\u2026'; }
      if (submit) { submit.disabled = true; submit.textContent = 'Saving\u2026'; }
    });
  });

  window.addEventListener('beforeunload', function (e) {
    if (submitting) return;
    var dirty = forms.some(function (f) { return f.dataset.dirty === '1'; });
    if (dirty) { e.preventDefault(); e.returnValue = ''; }
  });

  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    submitting = false;
    forms.forEach(function (form) {
      form.dataset.submitting = '';
      var submit = form.querySelector('button[type="submit"]');
      if (submit) { submit.disabled = false; if (submit.dataset.label) submit.textContent = submit.dataset.label; }
      setDirty(form, false);
    });
    paintTheme();
  });

  var summary = page.querySelector('.st-error-summary');
  if (summary) { summary.focus(); }
})();