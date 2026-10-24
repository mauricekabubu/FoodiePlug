/**
 * FoodiePlug — Food Library page script
 * static/js/library.js
 *
 * Owns everything Food Library specific:
 *   - the "Add to pantry" modal (open, close, backdrop, Escape, focus, scroll lock)
 *   - filling the modal for the clicked food
 *   - double-submit protection on the add-to-pantry form
 *
 * This file does NOT depend on dashboard.js. Its click handler runs in the
 * capture phase and stops propagation for this modal's triggers, so even if
 * dashboard.js (or any other script) has a generic [data-open-modal] /
 * [data-close-modal] handler, it can never double-handle this modal.
 *
 * The form is a normal Django POST: no fetch/AJAX, the CSRF token is untouched,
 * and the first legitimate submit is never prevented.
 *
 * Load after dashboard.js:
 *   <script src="{% static 'js/dashboard.js' %}"></script>
 *   <script src="{% static 'js/library.js' %}"></script>
 */
(function () {
  'use strict';

  var MODAL_ID = 'add-to-pantry-modal';
  var OPEN_CLASS = 'is-open';
  var BODY_LOCK_CLASS = 'modal-open';

  var modal = document.getElementById(MODAL_ID);
  var form = document.getElementById('add-to-pantry-form');

  /* ------------------------------------------------------------------
   * Add-to-pantry modal
   * ------------------------------------------------------------------ */
  function initModal() {
    if (!modal || !form) return;

    var panel = modal.querySelector('.modal-panel');
    var foodIdInput = document.getElementById('atp-food-id');
    var title = document.getElementById('add-to-pantry-title');
    var qtyInput = document.getElementById('atp-quantity');
    var submitBtn = form.querySelector('button[type="submit"]');
    var submitLabel = submitBtn ? submitBtn.textContent : '';

    var lastTrigger = null;      // button that opened the modal (for focus restore)
    var pressStartedOnBackdrop = false;

    modal.setAttribute('aria-hidden', 'true');

    function isOpen() {
      return modal.classList.contains(OPEN_CLASS);
    }

    function resetSubmit() {
      form.dataset.submitting = '';
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = submitLabel;
      }
    }

    function openModal(trigger) {
      lastTrigger = trigger;

      form.reset();                                   // clear values from a previous food
      resetSubmit();
      foodIdInput.value = trigger.dataset.foodId || '';
      title.textContent = 'Add ' + (trigger.dataset.foodName || 'food') + ' to pantry';

      modal.classList.add(OPEN_CLASS);
      modal.setAttribute('aria-hidden', 'false');
      document.body.classList.add(BODY_LOCK_CLASS);

      // Focus after the modal is displayed
      window.requestAnimationFrame(function () {
        var target = qtyInput || form.querySelector('input, select, textarea, button');
        if (target) {
          try { target.focus({ preventScroll: true }); } catch (err) { target.focus(); }
        }
      });
    }

    function closeModal(restoreFocus) {
      modal.classList.remove(OPEN_CLASS);
      modal.setAttribute('aria-hidden', 'true');
      document.body.classList.remove(BODY_LOCK_CLASS);

      if (restoreFocus !== false && lastTrigger && document.body.contains(lastTrigger)) {
        try { lastTrigger.focus({ preventScroll: true }); } catch (err) { lastTrigger.focus(); }
      }
      lastTrigger = null;
    }

    /* ---- open / close (capture phase: this file is the sole owner) ---- */
    document.addEventListener('click', function (e) {
      // Open
      var opener = e.target.closest('[data-open-modal="' + MODAL_ID + '"]');
      if (opener) {
        e.preventDefault();
        e.stopPropagation();
        openModal(opener);
        return;
      }

      if (!isOpen()) return;

      // Close button / Cancel button inside this modal
      var closer = e.target.closest('[data-close-modal]');
      if (closer && modal.contains(closer)) {
        e.preventDefault();
        e.stopPropagation();
        closeModal();
        return;
      }

      // Backdrop: only when the press AND the release were both on the overlay itself
      if (e.target === modal && pressStartedOnBackdrop) {
        e.stopPropagation();
        closeModal();
      }
    }, true);

    document.addEventListener('mousedown', function (e) {
      pressStartedOnBackdrop = (e.target === modal);
    }, true);

    /* ---- keyboard: Escape closes, Tab stays inside the dialog ---- */
    document.addEventListener('keydown', function (e) {
      if (!isOpen()) return;

      if (e.key === 'Escape' || e.key === 'Esc') {
        e.preventDefault();
        closeModal();
        return;
      }

      if (e.key === 'Tab' && panel) {
        var focusable = panel.querySelectorAll(
          'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (!focusable.length) return;
        var first = focusable[0];
        var last = focusable[focusable.length - 1];

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    });

    /* ---- submit: normal Django POST; only repeat submits are blocked ---- */
    form.addEventListener('submit', function (e) {
      if (form.dataset.submitting === '1') {
        e.preventDefault();
        return;
      }
      form.dataset.submitting = '1';
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Adding\u2026';
      }
    });

    /* ---- Back button (bfcache): never come back to an open modal / stuck button ---- */
    window.addEventListener('pageshow', function (e) {
      if (!e.persisted) return;
      resetSubmit();
      closeModal(false);
    });
  }

  function init() {
    initModal();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();