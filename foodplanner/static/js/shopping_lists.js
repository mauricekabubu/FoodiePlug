/**
 * FoodiePlug — Shopping lists index
 * static/js/shopping_lists.js  (loaded only on the lists index, after dashboard.js)
 *
 * dashboard.js already opens/closes `.modal-overlay` dialogs from [data-open-modal] and
 * [data-close-modal] and toggles `.dropdown` menus. This file adds what the index needs on top:
 *   - ONE shared rename modal and ONE shared delete modal, filled from the clicked card
 *   - inline validation in the rename modal
 *   - archive / restore (a shared POST form; works for the list's owner only, enforced by the server)
 *   - the card menu opens upwards when there is no room below, and arrow keys move through it
 *   - changing the sort order applies immediately
 *
 * Every action is still a normal Django POST with a CSRF token. Toasts come from the
 * Django messages script already on the page.
 */
(function () {
  'use strict';

  if (!document.querySelector('[data-lists-index]')) return;

  function $(id) { return document.getElementById(id); }

  /* ------------------------------------------------------------------ shared rename modal */
  var renameModal = $('rename-list-modal');
  var renameForm = $('rename-list-form');
  var renameInput = $('rename-list-name');
  var renameError = $('rename-list-error');
  var originalName = '';

  function showRenameError(message) {
    renameError.textContent = message;
    renameError.hidden = false;
    renameInput.setAttribute('aria-invalid', 'true');
    renameInput.focus();
  }

  function clearRenameError() {
    renameError.hidden = true;
    renameError.textContent = '';
    renameInput.removeAttribute('aria-invalid');
  }

  if (renameModal && renameForm && renameInput && renameError) {
    renameInput.addEventListener('input', clearRenameError);

    renameForm.addEventListener('submit', function (e) {
      var value = renameInput.value.trim();

      if (!value) { e.preventDefault(); showRenameError('Enter a name for your list.'); return; }
      if (value.length > 120) { e.preventDefault(); showRenameError('Use 120 characters or fewer.'); return; }

      if (value === originalName) {                        // nothing changed: just close
        e.preventDefault();
        var close = renameModal.querySelector('[data-close-modal]');
        if (close) close.click();
        return;
      }

      renameInput.value = value;
      var btn = renameForm.querySelector('button[type="submit"]');
      if (btn) { btn.dataset.label = btn.textContent; btn.disabled = true; btn.textContent = 'Saving\u2026'; }
    });
  }

  /* ------------------------------------------------------------------ shared delete modal */
  var deleteModal = $('delete-list-modal');
  var deleteForm = $('delete-list-form');
  var deleteTitle = $('delete-list-title');
  var deleteDesc = $('delete-list-desc');

  if (deleteForm) {
    deleteForm.addEventListener('submit', function () {
      var btn = deleteForm.querySelector('button[type="submit"]');
      if (btn) { btn.dataset.label = btn.textContent; btn.disabled = true; btn.textContent = 'Deleting\u2026'; }
    });
  }

  /* ------------------------------------------------------------------ clicks on card menu items */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-form-action]');
    if (!btn) return;

    var target = btn.dataset.openModal;
    var name = btn.dataset.name || '';

    if (target === 'rename-list-modal' && renameForm) {
      renameForm.action = btn.dataset.formAction;
      originalName = name;
      renameInput.value = name;
      clearRenameError();
      setTimeout(function () { renameInput.focus(); renameInput.select(); }, 60);
      return;
    }

    if (target === 'delete-list-modal' && deleteForm) {
      deleteForm.action = btn.dataset.formAction;

      var count = parseInt(btn.dataset.items, 10) || 0;
      deleteTitle.textContent = 'Delete \u201C' + name + '\u201D?';

      var text = count
        ? 'This permanently deletes the list and its ' + count + ' item' + (count === 1 ? '' : 's') + '.'
        : 'This list has no items.';
      text += ' This can\u2019t be undone.';
      if (btn.dataset.canArchive === '1') text += ' If you might need it later, archive it instead.';
      deleteDesc.textContent = text;

      // Focus the safe choice, so Enter can't delete by accident.
      var cancel = deleteModal.querySelector('[data-close-modal].btn-outline');
      if (cancel) setTimeout(function () { cancel.focus(); }, 60);
      return;
    }

    // Archive / restore: no confirmation needed, nothing is deleted.
    if (btn.hasAttribute('data-list-action')) {
      var form = $('list-action-form');
      if (!form) return;
      form.action = btn.dataset.formAction;
      form.submit();
    }
  });

  /* ------------------------------------------------------------------ card menus */
  // Open upwards when the menu would run off the bottom of the screen.
  document.addEventListener('click', function (e) {
    var trigger = e.target.closest('.shop-card-menu-btn');
    if (!trigger) return;

    var menu = trigger.closest('.dropdown');
    setTimeout(function () {
      var panel = menu.querySelector('.dropdown-panel');
      menu.classList.remove('opens-up');
      var box = panel.getBoundingClientRect();
      if (box.height && box.bottom > window.innerHeight - 8) menu.classList.add('opens-up');
    }, 0);
  });

  // Arrow keys / Home / End move between menu items.
  document.addEventListener('keydown', function (e) {
    var item = e.target.closest && e.target.closest('.shop-card-menu .shop-menu-btn');
    if (!item) return;

    var items = [].slice.call(item.closest('.dropdown-panel').querySelectorAll('.shop-menu-btn'));
    var index = items.indexOf(item);
    var next = null;

    if (e.key === 'ArrowDown') next = items[(index + 1) % items.length];
    else if (e.key === 'ArrowUp') next = items[(index - 1 + items.length) % items.length];
    else if (e.key === 'Home') next = items[0];
    else if (e.key === 'End') next = items[items.length - 1];

    if (next) { e.preventDefault(); next.focus(); }
  });

  /* ------------------------------------------------------------------ search / sort */
  var searchForm = $('lists-search-form');
  var sortSelect = $('lists-sort');
  if (searchForm && sortSelect) {
    sortSelect.addEventListener('change', function () { searchForm.submit(); });   // the page number is dropped
  }

  /* ------------------------------------------------------------------ back/forward cache */
  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    [renameForm, deleteForm].forEach(function (form) {
      if (!form) return;
      var btn = form.querySelector('button[type="submit"]');
      if (btn) { btn.disabled = false; if (btn.dataset.label) btn.textContent = btn.dataset.label; }
    });
  });
})();