/**
 * FoodiePlug — My Meals page script
 * static/js/meals.js
 *
 * Owns My Meals behaviour only (dashboard.js stays global):
 *   - broken-image fallback (the SVG fallback is already in the markup, so we only drop failed <img>)
 *   - client-side sorting of the meal grid
 *   - "Add to Plan" dialog (native <dialog>)
 *   - double-submit protection on POST forms
 *
 * Forms stay normal Django POSTs.
 */
(function () {
  'use strict';

  var page = document.getElementById('ml-page');
  if (!page) return;

  function $(id) { return document.getElementById(id); }

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

  /* ------------------------------------------------------------------ images */
  // Removing the failed <img> reveals the SVG fallback underneath. Once removed it can't error again.
  function dropImage(img) {
    if (img && img.parentNode) img.parentNode.removeChild(img);
  }

  document.addEventListener('error', function (e) {
    var el = e.target;
    if (el && el.tagName === 'IMG' && el.classList.contains('ml-img')) dropImage(el);
  }, true);

  [].slice.call(document.querySelectorAll('img.ml-img')).forEach(function (img) {
    if (img.complete && img.naturalWidth === 0) dropImage(img);   // failed before this script ran
  });

  /* ------------------------------------------------------------------ sorting */
  var grid = $('ml-grid');
  var sortSelect = $('ml-sort');

  if (grid && sortSelect) {
    var cards = [].slice.call(grid.children);
    cards.forEach(function (card, i) { card.dataset.index = i; });

    function minutes(card) {
      var prep = parseInt(card.dataset.prep, 10);
      var cook = parseInt(card.dataset.cook, 10);
      if (isNaN(prep) && isNaN(cook)) return Infinity;            // no time data -> last
      return (isNaN(prep) ? 0 : prep) + (isNaN(cook) ? 0 : cook);
    }

    function compare(mode) {
      if (mode === 'az') return function (a, b) { return a.dataset.name.localeCompare(b.dataset.name); };
      if (mode === 'za') return function (a, b) { return b.dataset.name.localeCompare(a.dataset.name); };
      if (mode === 'time') return function (a, b) {
        var d = minutes(a) - minutes(b);
        return d === 0 || isNaN(d) ? a.dataset.index - b.dataset.index : d;
      };
      return function (a, b) { return a.dataset.index - b.dataset.index; };
    }

    sortSelect.addEventListener('change', function () {
      var url = new URL(window.location.href);
      url.searchParams.set('sort', sortSelect.value);
      url.searchParams.delete('page');
      window.location.assign(url.toString());
    });
  }

  /* ------------------------------------------------------------------ add-to-plan dialog */
  var dialog = $('plan-dialog');

  if (dialog) {
    var mealId = $('plan-meal-id');
    var mealName = $('plan-meal-name');
    var lastTrigger = null;

    function openDialog(trigger) {
      lastTrigger = trigger;
      mealId.value = trigger.dataset.mealId || '';
      mealName.textContent = trigger.dataset.mealName || '';
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
      var first = dialog.querySelector('input[type="date"]');
      if (first) first.focus();
    }

    function closeDialog() {
      if (typeof dialog.close === 'function') dialog.close();
      else dialog.removeAttribute('open');
      if (lastTrigger && document.body.contains(lastTrigger)) lastTrigger.focus();
    }

    document.addEventListener('click', function (e) {
      var opener = e.target.closest('[data-plan-meal]');
      if (opener) { e.preventDefault(); openDialog(opener); return; }
      if (e.target.closest('[data-close-dialog]')) { e.preventDefault(); closeDialog(); return; }
      if (e.target === dialog) closeDialog();                      // click on the backdrop
    });
  }

  /* ------------------------------------------------------------------ double-submit guard */
  [].slice.call(document.querySelectorAll('form[method="post"]')).forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (form.dataset.submitting === '1') { e.preventDefault(); return; }
      form.dataset.submitting = '1';
      var btn = form.querySelector('button[type="submit"]');
      if (btn) { btn.dataset.label = btn.textContent; btn.disabled = true; btn.textContent = 'Saving\u2026'; }
    });
  });

  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    [].slice.call(document.querySelectorAll('form[method="post"]')).forEach(function (form) {
      form.dataset.submitting = '';
      var btn = form.querySelector('button[type="submit"]');
      if (btn) { btn.disabled = false; if (btn.dataset.label) btn.textContent = btn.dataset.label; }
    });
  });

})();



  /* ------------------------------------------------------------------ meal image upload preview */
  var imageInput = $('id_image');
  var imagePreview = $('ml-image-preview-img');
  var imagePlaceholder = $('ml-image-placeholder');
  var removeImageBtn = $('ml-image-remove');

  if (imageInput && imagePreview && imagePlaceholder && removeImageBtn) {
    var previewUrl = null;
    var maxImageSize = 5 * 1024 * 1024;

    var allowedImageTypes = [
      'image/jpeg',
      'image/png',
      'image/webp'
    ];

    function clearMealImagePreview() {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        previewUrl = null;
      }

      imagePreview.removeAttribute('src');
      imagePreview.hidden = true;
      imagePlaceholder.hidden = false;
      removeImageBtn.hidden = true;
      imageInput.value = '';
    }

    imageInput.addEventListener('change', function () {
      var file = imageInput.files && imageInput.files[0];

      if (!file) {
        clearMealImagePreview();
        return;
      }

      if (allowedImageTypes.indexOf(file.type) === -1) {
        clearMealImagePreview();
        toast('Choose a JPG, PNG, or WebP image.', 'error');
        return;
      }

      if (file.size > maxImageSize) {
        clearMealImagePreview();
        toast('Your meal image must be smaller than 5 MB.', 'error');
        return;
      }

      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        previewUrl = null;
      }

      previewUrl = URL.createObjectURL(file);

      imagePreview.onload = function () {
        imagePlaceholder.hidden = true;
        imagePreview.hidden = false;
        removeImageBtn.hidden = false;
      };

      imagePreview.onerror = function () {
        clearMealImagePreview();
        toast('Could not preview this image. Try another file.', 'error');
      };

      imagePreview.src = previewUrl;
    });

    removeImageBtn.addEventListener('click', function () {
      clearMealImagePreview();
    });
  }

    /* ------------------------------------------------------------------ scroll to ingredients */
  // Redirects carry #ingredients natively; this covers the error re-render (no hash in the URL).
  var scrollTarget = document.querySelector('[data-scroll-ingredients]');
  var ingredients = $('ingredients');
  if (scrollTarget && ingredients && !window.location.hash) {
    ingredients.scrollIntoView({ block: 'start' });
  }



// Edit meals in meals.html 
/**
 * FoodiePlug — My Meals page script
 * static/js/meals.js
 *
 * Owns My Meals behaviour only (dashboard.js stays global):
 *   - broken-image fallback (the SVG fallback is already in the markup, so we only drop failed <img>)
 *   - client-side sorting of the meal grid
 *   - "Add to Plan" dialog (native <dialog>)
 *   - double-submit protection on POST forms
 *   - meal image preview (create + edit; edit keeps the current image unless replaced)
 *   - edit page: strike-through for ingredients marked for removal, focus on errors
 *   - scroll to the Ingredients section after a failed add
 *
 * Forms stay normal Django POSTs.
 *
 * NOTE: every block must stay INSIDE the IIFE below. Code placed after the closing
 * `})();` can't see `$` or `toast` and throws a ReferenceError, which also stops
 * anything that comes after it.
 */
(function () {
  'use strict';

  var page = document.getElementById('ml-page');
  if (!page) return;

  function $(id) { return document.getElementById(id); }

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

  // `hidden` as a property doesn't exist on SVG elements, so use the attribute.
  function setHidden(el, hide) {
    if (!el) return;
    if (hide) el.setAttribute('hidden', '');
    else el.removeAttribute('hidden');
  }

  /* ------------------------------------------------------------------ images */
  // Removing the failed <img> reveals the SVG fallback underneath. Once removed it can't error again.
  function dropImage(img) {
    if (img && img.parentNode) img.parentNode.removeChild(img);
  }

  document.addEventListener('error', function (e) {
    var el = e.target;
    if (el && el.tagName === 'IMG' && el.classList.contains('ml-img')) dropImage(el);
  }, true);

  [].slice.call(document.querySelectorAll('img.ml-img')).forEach(function (img) {
    if (img.complete && img.naturalWidth === 0) dropImage(img);   // failed before this script ran
  });

  /* ------------------------------------------------------------------ sorting */
  var grid = $('ml-grid');
  var sortSelect = $('ml-sort');

  if (grid && sortSelect) {
    var cards = [].slice.call(grid.children);
    cards.forEach(function (card, i) { card.dataset.index = i; });

    var minutes = function (card) {
      var prep = parseInt(card.dataset.prep, 10);
      var cook = parseInt(card.dataset.cook, 10);
      if (isNaN(prep) && isNaN(cook)) return Infinity;            // no time data -> last
      return (isNaN(prep) ? 0 : prep) + (isNaN(cook) ? 0 : cook);
    };

    var compare = function (mode) {
      if (mode === 'az') return function (a, b) { return a.dataset.name.localeCompare(b.dataset.name); };
      if (mode === 'za') return function (a, b) { return b.dataset.name.localeCompare(a.dataset.name); };
      if (mode === 'time') return function (a, b) {
        var d = minutes(a) - minutes(b);
        return d === 0 || isNaN(d) ? a.dataset.index - b.dataset.index : d;
      };
      return function (a, b) { return a.dataset.index - b.dataset.index; };
    };

    sortSelect.addEventListener('change', function () {
      var url = new URL(window.location.href);
      url.searchParams.set('sort', sortSelect.value);
      url.searchParams.delete('page');
      window.location.assign(url.toString());
    });
  }

  /* ------------------------------------------------------------------ add-to-plan dialog */
  var dialog = $('plan-dialog');

  if (dialog) {
    var mealId = $('plan-meal-id');
    var mealName = $('plan-meal-name');
    var lastTrigger = null;

    var openDialog = function (trigger) {
      lastTrigger = trigger;
      mealId.value = trigger.dataset.mealId || '';
      mealName.textContent = trigger.dataset.mealName || '';
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
      var first = dialog.querySelector('input[type="date"]');
      if (first) first.focus();
    };

    var closeDialog = function () {
      if (typeof dialog.close === 'function') dialog.close();
      else dialog.removeAttribute('open');
      if (lastTrigger && document.body.contains(lastTrigger)) lastTrigger.focus();
    };

    document.addEventListener('click', function (e) {
      var opener = e.target.closest('[data-plan-meal]');
      if (opener) { e.preventDefault(); openDialog(opener); return; }
      if (e.target.closest('[data-close-dialog]')) { e.preventDefault(); closeDialog(); return; }
      if (e.target === dialog) closeDialog();                      // click on the backdrop
    });
  }

  /* ------------------------------------------------------------------ double-submit guard */
  [].slice.call(document.querySelectorAll('form[method="post"]')).forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (form.dataset.submitting === '1') { e.preventDefault(); return; }
      form.dataset.submitting = '1';
      var btn = form.querySelector('button[type="submit"]');
      if (btn) { btn.dataset.label = btn.textContent; btn.disabled = true; btn.textContent = 'Saving\u2026'; }
    });
  });

  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    [].slice.call(document.querySelectorAll('form[method="post"]')).forEach(function (form) {
      form.dataset.submitting = '';
      var btn = form.querySelector('button[type="submit"]');
      if (btn) { btn.disabled = false; if (btn.dataset.label) btn.textContent = btn.dataset.label; }
    });
  });

  /* ------------------------------------------------------------------ meal image preview (create + edit) */
  var imageInput = $('id_image');
  var imagePreview = $('ml-image-preview-img');
  var imagePlaceholder = $('ml-image-placeholder');
  var removeImageBtn = $('ml-image-remove');

  if (imageInput && imagePreview && imagePlaceholder && removeImageBtn) {
    var previewUrl = null;
    var maxImageSize = 5 * 1024 * 1024;
    var allowedImageTypes = ['image/jpeg', 'image/png', 'image/webp'];
    // On the edit page the saved image is already shown; "undo" returns to it.
    var currentSrc = imagePreview.getAttribute('data-current-src') || '';

    var releasePreview = function () {
      if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
    };

    var resetMealImagePreview = function () {
      releasePreview();
      imageInput.value = '';
      imagePreview.onload = null;
      imagePreview.onerror = null;
      removeImageBtn.hidden = true;

      if (currentSrc) {
        imagePreview.src = currentSrc;
        setHidden(imagePreview, false);
        setHidden(imagePlaceholder, true);
      } else {
        imagePreview.removeAttribute('src');
        setHidden(imagePreview, true);
        setHidden(imagePlaceholder, false);
      }
    };

    imageInput.addEventListener('change', function () {
      var file = imageInput.files && imageInput.files[0];

      if (!file) { resetMealImagePreview(); return; }

      if (allowedImageTypes.indexOf(file.type) === -1) {
        resetMealImagePreview();
        toast('Choose a JPG, PNG, or WebP image.', 'error');
        return;
      }

      if (file.size > maxImageSize) {
        resetMealImagePreview();
        toast('Your meal image must be smaller than 5 MB.', 'error');
        return;
      }

      releasePreview();
      previewUrl = URL.createObjectURL(file);

      imagePreview.onload = function () {
        setHidden(imagePlaceholder, true);
        setHidden(imagePreview, false);
        removeImageBtn.hidden = false;
      };

      imagePreview.onerror = function () {
        resetMealImagePreview();
        toast('Could not preview this image. Try another file.', 'error');
      };

      imagePreview.src = previewUrl;
    });

    removeImageBtn.addEventListener('click', resetMealImagePreview);
  }

  /* ------------------------------------------------------------------ edit page: ingredients marked for removal */
  [].slice.call(document.querySelectorAll('.ml-remove-toggle input')).forEach(function (box) {
    var sync = function () {
      var row = box.closest('.ml-edit-ing');
      if (row) row.classList.toggle('is-removed', box.checked);
    };
    box.addEventListener('change', sync);
    sync();
  });

  /* ------------------------------------------------------------------ focus the error summary (edit page) */
  var errorSummary = $('ml-error-summary');
  if (errorSummary) {
    errorSummary.scrollIntoView({ block: 'center' });
    errorSummary.focus({ preventScroll: true });
  }

  /* ------------------------------------------------------------------ scroll to ingredients */
  // Redirects carry #ingredients natively; this covers the error re-render (no hash in the URL).
  var scrollTarget = document.querySelector('[data-scroll-ingredients]');
  var ingredientsSection = $('ingredients');
  if (scrollTarget && ingredientsSection && !window.location.hash) {
    ingredientsSection.scrollIntoView({ block: 'start' });
  }
})();


/**
 * FoodiePlug — My Meals page script
 * static/js/meals.js
 *
 * Owns My Meals behaviour only (dashboard.js stays global):
 *   - broken-image fallback (the SVG fallback is already in the markup, so we only drop failed <img>)
 *   - client-side sorting of the meal grid
 *   - "Add to Plan" dialog (native <dialog>)
 *   - "Archive meal" confirmation dialog (forms still work as plain POSTs without JS)
 *   - double-submit protection on POST forms
 *   - meal image preview (create + edit; edit keeps the current image unless replaced)
 *   - edit page: strike-through for ingredients marked for removal, focus on errors
 *   - scroll to the Ingredients section after a failed add
 *
 * Forms stay normal Django POSTs.
 *
 * NOTE: every block must stay INSIDE the IIFE below. Code placed after the closing
 * `})();` can't see `$` or `toast` and throws a ReferenceError, which also stops
 * anything that comes after it.
 */
(function () {
  'use strict';

  var page = document.getElementById('ml-page');
  if (!page) return;

  function $(id) { return document.getElementById(id); }

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

  // `hidden` as a property doesn't exist on SVG elements, so use the attribute.
  function setHidden(el, hide) {
    if (!el) return;
    if (hide) el.setAttribute('hidden', '');
    else el.removeAttribute('hidden');
  }

  /* ------------------------------------------------------------------ images */
  // Removing the failed <img> reveals the SVG fallback underneath. Once removed it can't error again.
  function dropImage(img) {
    if (img && img.parentNode) img.parentNode.removeChild(img);
  }

  document.addEventListener('error', function (e) {
    var el = e.target;
    if (el && el.tagName === 'IMG' && el.classList.contains('ml-img')) dropImage(el);
  }, true);

  [].slice.call(document.querySelectorAll('img.ml-img')).forEach(function (img) {
    if (img.complete && img.naturalWidth === 0) dropImage(img);   // failed before this script ran
  });

  /* ------------------------------------------------------------------ sorting */
  var grid = $('ml-grid');
  var sortSelect = $('ml-sort');

  if (grid && sortSelect) {
    var cards = [].slice.call(grid.children);
    cards.forEach(function (card, i) { card.dataset.index = i; });

    var minutes = function (card) {
      var prep = parseInt(card.dataset.prep, 10);
      var cook = parseInt(card.dataset.cook, 10);
      if (isNaN(prep) && isNaN(cook)) return Infinity;            // no time data -> last
      return (isNaN(prep) ? 0 : prep) + (isNaN(cook) ? 0 : cook);
    };

    var compare = function (mode) {
      if (mode === 'az') return function (a, b) { return a.dataset.name.localeCompare(b.dataset.name); };
      if (mode === 'za') return function (a, b) { return b.dataset.name.localeCompare(a.dataset.name); };
      if (mode === 'time') return function (a, b) {
        var d = minutes(a) - minutes(b);
        return d === 0 || isNaN(d) ? a.dataset.index - b.dataset.index : d;
      };
      return function (a, b) { return a.dataset.index - b.dataset.index; };
    };

    sortSelect.addEventListener('change', function () {
      var url = new URL(window.location.href);
      url.searchParams.set('sort', sortSelect.value);
      url.searchParams.delete('page');
      window.location.assign(url.toString());
    });
  }

  /* ------------------------------------------------------------------ add-to-plan dialog */
  var dialog = $('plan-dialog');

  if (dialog) {
    var mealId = $('plan-meal-id');
    var mealName = $('plan-meal-name');
    var lastTrigger = null;

    var openDialog = function (trigger) {
      lastTrigger = trigger;
      mealId.value = trigger.dataset.mealId || '';
      mealName.textContent = trigger.dataset.mealName || '';
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
      var first = dialog.querySelector('input[type="date"]');
      if (first) first.focus();
    };

    var closeDialog = function () {
      if (typeof dialog.close === 'function') dialog.close();
      else dialog.removeAttribute('open');
      if (lastTrigger && document.body.contains(lastTrigger)) lastTrigger.focus();
    };

    document.addEventListener('click', function (e) {
      var opener = e.target.closest('[data-plan-meal]');
      if (opener) { e.preventDefault(); openDialog(opener); return; }
      if (e.target.closest('[data-close-dialog]')) { e.preventDefault(); closeDialog(); return; }
      if (e.target === dialog) closeDialog();                      // click on the backdrop
    });
  }

  /* ------------------------------------------------------------------ archive confirmation dialog */
  // Archive buttons live in real <form method="post" data-archive-form> elements, so archiving works
  // even if this script fails. With JS, the submit is paused to ask first.
  var archiveDialog = $('archive-dialog');

  if (archiveDialog) {
    var archiveName = $('archive-meal-name');
    var archiveConfirm = $('archive-confirm');
    var pendingForm = null;
    var archiveTrigger = null;

    var openArchive = function (form, trigger) {
      pendingForm = form;
      archiveTrigger = trigger;
      archiveName.textContent = form.dataset.mealName || 'this meal';
      if (typeof archiveDialog.showModal === 'function') archiveDialog.showModal();
      else archiveDialog.setAttribute('open', '');
      archiveConfirm.focus();
    };

    var closeArchive = function () {
      if (typeof archiveDialog.close === 'function') archiveDialog.close();
      else archiveDialog.removeAttribute('open');
      if (archiveTrigger && document.body.contains(archiveTrigger)) archiveTrigger.focus();
      pendingForm = null;
    };

    // Capture phase + stopPropagation so the double-submit guard below doesn't disable the button early.
    document.addEventListener('submit', function (e) {
      var form = e.target;
      if (!form || !form.matches || !form.matches('form[data-archive-form]')) return;
      e.preventDefault();
      e.stopPropagation();
      openArchive(form, document.activeElement);
    }, true);

    archiveConfirm.addEventListener('click', function () {
      if (!pendingForm) return;
      var form = pendingForm;
      archiveConfirm.disabled = true;
      archiveConfirm.textContent = 'Archiving\u2026';
      form.submit();                       // programmatic submit: skips the handler above
    });

    archiveDialog.addEventListener('click', function (e) {
      if (e.target === archiveDialog || e.target.closest('[data-close-archive]')) closeArchive();
    });

    archiveDialog.addEventListener('close', function () { pendingForm = null; });   // Escape key
  }

  /* ------------------------------------------------------------------ double-submit guard */
  [].slice.call(document.querySelectorAll('form[method="post"]')).forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (form.dataset.submitting === '1') { e.preventDefault(); return; }
      form.dataset.submitting = '1';
      var btn = form.querySelector('button[type="submit"]');
      if (btn) { btn.dataset.label = btn.textContent; btn.disabled = true; btn.textContent = 'Saving\u2026'; }
    });
  });

  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    [].slice.call(document.querySelectorAll('form[method="post"]')).forEach(function (form) {
      form.dataset.submitting = '';
      var btn = form.querySelector('button[type="submit"]');
      if (btn) { btn.disabled = false; if (btn.dataset.label) btn.textContent = btn.dataset.label; }
    });
    var confirmBtn = $('archive-confirm');
    if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.textContent = 'Archive meal'; }
  });

  /* ------------------------------------------------------------------ meal image preview (create + edit) */
  var imageInput = $('id_image');
  var imagePreview = $('ml-image-preview-img');
  var imagePlaceholder = $('ml-image-placeholder');
  var removeImageBtn = $('ml-image-remove');

  if (imageInput && imagePreview && imagePlaceholder && removeImageBtn) {
    var previewUrl = null;
    var maxImageSize = 5 * 1024 * 1024;
    var allowedImageTypes = ['image/jpeg', 'image/png', 'image/webp'];
    // On the edit page the saved image is already shown; "undo" returns to it.
    var currentSrc = imagePreview.getAttribute('data-current-src') || '';

    var releasePreview = function () {
      if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
    };

    var resetMealImagePreview = function () {
      releasePreview();
      imageInput.value = '';
      imagePreview.onload = null;
      imagePreview.onerror = null;
      removeImageBtn.hidden = true;

      if (currentSrc) {
        imagePreview.src = currentSrc;
        setHidden(imagePreview, false);
        setHidden(imagePlaceholder, true);
      } else {
        imagePreview.removeAttribute('src');
        setHidden(imagePreview, true);
        setHidden(imagePlaceholder, false);
      }
    };

    imageInput.addEventListener('change', function () {
      var file = imageInput.files && imageInput.files[0];

      if (!file) { resetMealImagePreview(); return; }

      if (allowedImageTypes.indexOf(file.type) === -1) {
        resetMealImagePreview();
        toast('Choose a JPG, PNG, or WebP image.', 'error');
        return;
      }

      if (file.size > maxImageSize) {
        resetMealImagePreview();
        toast('Your meal image must be smaller than 5 MB.', 'error');
        return;
      }

      releasePreview();
      previewUrl = URL.createObjectURL(file);

      imagePreview.onload = function () {
        setHidden(imagePlaceholder, true);
        setHidden(imagePreview, false);
        removeImageBtn.hidden = false;
      };

      imagePreview.onerror = function () {
        resetMealImagePreview();
        toast('Could not preview this image. Try another file.', 'error');
      };

      imagePreview.src = previewUrl;
    });

    removeImageBtn.addEventListener('click', resetMealImagePreview);
  }

  /* ------------------------------------------------------------------ edit page: ingredients marked for removal */
  [].slice.call(document.querySelectorAll('.ml-remove-toggle input')).forEach(function (box) {
    var sync = function () {
      var row = box.closest('.ml-edit-ing');
      if (row) row.classList.toggle('is-removed', box.checked);
    };
    box.addEventListener('change', sync);
    sync();
  });

  /* ------------------------------------------------------------------ focus the error summary (edit page) */
  var errorSummary = $('ml-error-summary');
  if (errorSummary) {
    errorSummary.scrollIntoView({ block: 'center' });
    errorSummary.focus({ preventScroll: true });
  }

  /* ------------------------------------------------------------------ scroll to ingredients */
  // Redirects carry #ingredients natively; this covers the error re-render (no hash in the URL).
  var scrollTarget = document.querySelector('[data-scroll-ingredients]');
  var ingredientsSection = $('ingredients');
  if (scrollTarget && ingredientsSection && !window.location.hash) {
    ingredientsSection.scrollIntoView({ block: 'start' });
  }
})();