/* ============================================================
   FoodiePlug — Django Toast Notifications
   ============================================================ */

(function () {
  'use strict';

  var AUTO_DISMISS_MS = 5000;
  var EXIT_ANIMATION_MS = 220;

  var icons = {
    success: '<path d="m5 12 4 4L19 6"/>',
    error: '<path d="M18 6 6 18M6 6l12 12"/>',
    warning: '<path d="M12 9v4m0 4h.01"/><path d="M10.3 3.9 2.6 17.2A2 2 0 0 0 4.3 20h15.4a2 2 0 0 0 1.7-2.8L13.7 3.9a2 2 0 0 0-3.4 0Z"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4m0-4h.01"/>'
  };

  var titles = {
    success: 'Success',
    error: 'Something went wrong',
    warning: 'Heads up',
    info: 'Information',
    debug: 'Information'
  };

  function dismiss(toast) {
    if (!toast || toast.classList.contains('is-leaving')) return;

    toast.classList.add('is-leaving');

    window.setTimeout(function () {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, EXIT_ANIMATION_MS);
  }

  function initializeToast(toast) {
    if (toast.dataset.initialized === 'true') return;
    toast.dataset.initialized = 'true';

    var closeBtn = toast.querySelector('.toast-close');

    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        dismiss(toast);
      });
    }

    var timer = null;
    var remaining = AUTO_DISMISS_MS;
    var startedAt = 0;

    function start(duration) {
      if (timer || remaining <= 0) return;

      startedAt = Date.now();

      timer = window.setTimeout(function () {
        timer = null;
        remaining = 0;
        dismiss(toast);
      }, duration);
    }

    function pause() {
      if (!timer) return;

      window.clearTimeout(timer);
      timer = null;

      remaining = Math.max(
        0,
        remaining - (Date.now() - startedAt)
      );

      toast.classList.add('is-paused');
    }

    function resume() {
      toast.classList.remove('is-paused');

      if (remaining <= 0) {
        dismiss(toast);
        return;
      }

      start(remaining);
    }

    toast.addEventListener('mouseenter', pause);
    toast.addEventListener('mouseleave', resume);
    toast.addEventListener('focusin', pause);

    toast.addEventListener('focusout', function (event) {
      if (
        event.relatedTarget &&
        toast.contains(event.relatedTarget)
      ) {
        return;
      }

      resume();
    });

    // Reduced motion disables animation, not auto-dismiss.
    start(AUTO_DISMISS_MS);
  }

  function createToast(message, level, container) {
    var allowedLevels = ['success', 'error', 'warning', 'info', 'debug'];

    if (allowedLevels.indexOf(level) === -1) {
      level = 'info';
    }

    var toast = document.createElement('div');
    toast.className = 'foodie-toast ' + level;
    toast.setAttribute(
      'role',
      level === 'error' ? 'alert' : 'status'
    );

    var icon = document.createElement('span');
    icon.className = 'toast-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true">' +
      icons[level] +
      '</svg>';

    var content = document.createElement('div');
    content.className = 'toast-content';

    var title = document.createElement('strong');
    title.className = 'toast-title';
    title.textContent = titles[level];

    var text = document.createElement('span');
    text.className = 'toast-message';
    text.textContent = message;

    content.appendChild(title);
    content.appendChild(text);

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'toast-close';
    close.setAttribute('aria-label', 'Dismiss notification');
    close.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M18 6 6 18M6 6l12 12"/>' +
      '</svg>';

    var progress = document.createElement('span');
    progress.className = 'toast-progress';
    progress.setAttribute('aria-hidden', 'true');

    toast.appendChild(icon);
    toast.appendChild(content);
    toast.appendChild(close);
    toast.appendChild(progress);

    container.appendChild(toast);
    initializeToast(toast);
  }

  function init() {
    var container = document.getElementById('toast-container');

    if (!container) {
      console.warn('FoodiePlug: #toast-container was not found.');
      return;
    }

    // Convert Django's hidden messages into visible toast elements.
    var flashMessages = document.getElementById('flash-messages');

    if (flashMessages) {
      flashMessages.querySelectorAll('[data-level]').forEach(function (item) {
        var message = item.textContent.trim();
        var level = (item.dataset.level || 'info')
          .trim()
          .split(/\\s+/)[0];

        if (message) {
          createToast(message, level, container);
        }
      });

      flashMessages.remove();
    }

    // Also initialize toast elements already rendered by a template.
    container.querySelectorAll('.foodie-toast').forEach(initializeToast);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();