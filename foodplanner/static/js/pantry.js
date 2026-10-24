(function () {
  'use strict';

  /* =========================================================
     TOAST
  ========================================================= */

  function showToast(message, type) {
    var container = document.getElementById('toast-container');
    if (!container) return;

    var toast = document.createElement('div');

    toast.className = 'foodie-toast ' + (type || 'success');
    toast.setAttribute('role', 'status');

    toast.innerHTML =
      '<div class="toast-icon">' +
        '<svg viewBox="0 0 24 24" aria-hidden="true">' +
          '<path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' +
        '</svg>' +
      '</div>' +
      '<div class="toast-content">' +
        '<span class="toast-message"></span>' +
      '</div>' +
      '<button type="button" class="toast-close" aria-label="Dismiss notification">' +
        '<svg viewBox="0 0 24 24" aria-hidden="true">' +
          '<path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' +
        '</svg>' +
      '</button>' +
      '<div class="toast-progress"></div>';

    toast.querySelector('.toast-message').textContent = message;

    container.appendChild(toast);

    function dismiss() {
      if (toast.classList.contains('is-leaving')) return;

      toast.classList.add('is-leaving');

      window.setTimeout(function () {
        toast.remove();
      }, 220);
    }

    toast.querySelector('.toast-close').addEventListener(
      'click',
      dismiss
    );

    window.setTimeout(dismiss, 4000);
  }

  window.foodieToast = showToast;


  /* =========================================================
     CSRF
  ========================================================= */

  function getCookie(name) {
    var cookieValue = null;

    if (document.cookie && document.cookie !== '') {
      var cookies = document.cookie.split(';');

      for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();

        if (cookie.substring(0, name.length + 1) === name + '=') {
          cookieValue = decodeURIComponent(
            cookie.substring(name.length + 1)
          );

          break;
        }
      }
    }

    return cookieValue;
  }

  var csrfToken = getCookie('csrftoken');


  /* =========================================================
     SEARCH + CATEGORY + AVAILABILITY
  ========================================================= */

  var searchInput = document.getElementById('pantry-search-input');
  var searchWrap = document.querySelector('.pantry-search');
  var searchClear = document.querySelector('.pantry-search .search-clear');

  var categoryChips = document.querySelectorAll('.cat-chip');

  var availabilitySelect =
    document.getElementById('availability-filter');

  var sortSelect = document.getElementById('pantry-sort');
  var filterForm = document.getElementById('pantry-filter-form');

  function submitPantryFilters() {
    if (!filterForm) return;
    if (typeof filterForm.requestSubmit === 'function') {
      filterForm.requestSubmit();
    } else {
      filterForm.submit();
    }
  }

  var items = document.querySelectorAll('.pantry-item');

  var activeCategory = 'all';


  function applyFilters() {
    var query =
      (searchInput && searchInput.value.trim().toLowerCase()) || '';

    var availability =
      (availabilitySelect && availabilitySelect.value) || 'all';

    var visibleCount = 0;

    items.forEach(function (item) {

      var matchesCategory =
        activeCategory === 'all' ||
        item.dataset.category === activeCategory;

      var matchesAvailability =
        availability === 'all' ||
        item.dataset.status === availability;

      var matchesSearch =
        !query ||
        item.dataset.search.indexOf(query) !== -1;

      var visible =
        matchesCategory &&
        matchesAvailability &&
        matchesSearch;

      item.style.display = visible ? '' : 'none';

      if (visible) {
        visibleCount++;
      }
    });

    var noResults =
      document.getElementById('pantry-no-results');

    if (noResults) {
      noResults.style.display =
        visibleCount === 0 ? 'block' : 'none';
    }
  }


  if (searchInput) {
    searchInput.addEventListener('input', function () {

      if (searchWrap) {
        searchWrap.classList.toggle(
          'has-value',
          searchInput.value.length > 0
        );
      }

      applyFilters();
    });
  }


  if (searchClear) {
    searchClear.addEventListener('click', function () {

      if (!searchInput) return;

      searchInput.value = '';

      if (searchWrap) {
        searchWrap.classList.remove('has-value');
      }

      applyFilters();

      searchInput.focus();
      submitPantryFilters();
    });
  }


  if (availabilitySelect) {
    availabilitySelect.addEventListener(
      'change',
      function () {
        applyFilters();
        submitPantryFilters();
      }
    );
  }

  if (sortSelect) {
    sortSelect.addEventListener('change', submitPantryFilters);
  }

  var mobileAvailability = document.getElementById('mobile-availability-filter');
  var mobileSort = document.getElementById('mobile-sort');
  var filterModal = document.getElementById('filter-modal');
  var applyMobileFilters = filterModal && filterModal.querySelector('.modal-actions button');
  if (applyMobileFilters) {
    applyMobileFilters.addEventListener('click', function () {
      if (availabilitySelect && mobileAvailability) {
        availabilitySelect.value = mobileAvailability.value;
      }
      if (sortSelect && mobileSort) {
        sortSelect.value = mobileSort.value;
      }
      submitPantryFilters();
    });
  }

  categoryChips.forEach(function (chip) {

    chip.addEventListener('click', function () {

      categoryChips.forEach(function (c) {
        c.classList.remove('is-active');
      });

      chip.classList.add('is-active');

      activeCategory = chip.dataset.category;

      applyFilters();
    });
  });


  /* =========================================================
     QUANTITY STEPPER
  ========================================================= */

  document
    .querySelectorAll('.item-qty-control')
    .forEach(function (control) {

      var valueEl =
        control.querySelector('.qty-value');

      var minus =
        control.querySelector('.qty-minus');

      var plus =
        control.querySelector('.qty-plus');

      var step =
        parseFloat(control.dataset.step || '1');

      var unit =
        control.dataset.unit || '';

      var url =
        control.dataset.url;


      function currentValue() {
        return parseFloat(
          valueEl.dataset.value || '0'
        );
      }


      function render(val) {
        val = Math.max(
          0,
          Math.round(val * 100) / 100
        );

        valueEl.dataset.value = val;

        valueEl.textContent =
          val + ' ' + unit;
      }


      function updateQuantity(newQuantity) {

        if (!url) {
          showToast(
            'Unable to update quantity.',
            'error'
          );

          return;
        }

        var body = new FormData();

        body.append(
          'quantity',
          newQuantity
        );


        fetch(url, {
          method: 'POST',

          body: body,

          credentials: 'same-origin',

          headers: {
            'X-CSRFToken': csrfToken
          }
        })
        .then(function (response) {

          if (!response.ok) {
            throw new Error(
              'Quantity update failed.'
            );
          }

          return response.text();
        })
        .then(function () {

          if (newQuantity <= 0) {
            window.location.reload();
            return;
          }

          render(newQuantity);

          showToast(
            'Quantity updated.',
            'success'
          );
        })
        .catch(function (error) {

          console.error(error);

          showToast(
            'Could not update quantity.',
            'error'
          );
        });
      }


      if (minus) {

        minus.addEventListener(
          'click',
          function () {

            var newValue =
              Math.max(
                0,
                currentValue() - step
              );

            updateQuantity(newValue);
          }
        );
      }


      if (plus) {

        plus.addEventListener(
          'click',
          function () {

            var newValue =
              currentValue() + step;

            updateQuantity(newValue);
          }
        );
      }

    });


  /* =========================================================
     SHOPPING
  ========================================================= */

  document
    .querySelectorAll('.item-shopping-link')
    .forEach(function (link) {

      link.addEventListener(
        'click',
        function (event) {

          event.preventDefault();

          if (link.classList.contains('is-added')) {
            return;
          }

          link.textContent =
            'Added to shopping list';

          link.classList.add('is-added');

          showToast(
            'Added to your shopping list.',
            'success'
          );
        }
      );
    });


  /* =========================================================
     MODALS
  ========================================================= */

  function openModal(modal) {

    if (!modal) return;

    modal.classList.add('is-open');

    var firstField =
      modal.querySelector(
        'input, select, textarea, button'
      );

    if (firstField) {
      firstField.focus();
    }
  }


  function closeModal(modal) {

    if (modal) {
      modal.classList.remove('is-open');
    }
  }


  /* =========================================================
     EDIT / CONSUME / DELETE MODAL DATA
  ========================================================= */

  document
    .querySelectorAll('[data-open-modal]')
    .forEach(function (trigger) {

      trigger.addEventListener(
        'click',
        function () {

          var modal =
            document.getElementById(
              trigger.dataset.openModal
            );

          if (!modal) return;


          /* -------------------------
             EDIT
          ------------------------- */

          if (
            trigger.dataset.openModal ===
            'edit-pantry-modal'
          ) {

            var editForm =
              document.getElementById(
                'edit-pantry-form'
              );

            if (editForm) {

              editForm.action =
                trigger.dataset.formAction || '';

              var quantity =
                editForm.querySelector(
                  '[name="quantity"]'
                );

              var unit =
                editForm.querySelector(
                  '[name="unit"]'
                );

              var storage =
                editForm.querySelector(
                  '[name="storage"]'
                );

              var minimum =
                editForm.querySelector(
                  '[name="minimum_quantity"]'
                );

              var acquired =
                editForm.querySelector(
                  '[name="acquired_at"]'
                );

              var expires =
                editForm.querySelector(
                  '[name="expires_at"]'
                );

              var notes =
                editForm.querySelector(
                  '[name="notes"]'
                );


              if (quantity) {
                quantity.value =
                  trigger.dataset.quantity || '';
              }

              if (unit) {
                unit.value =
                  trigger.dataset.unit || '';
              }

              if (storage) {
                storage.value =
                  trigger.dataset.storage || '';
              }

              if (minimum) {
                minimum.value =
                  trigger.dataset.min || '0';
              }

              if (acquired) {
                acquired.value =
                  trigger.dataset.acquired || '';
              }

              if (expires) {
                expires.value =
                  trigger.dataset.expires || '';
              }

              if (notes) {
                notes.value =
                  trigger.dataset.notes || '';
              }
            }
          }


          /* -------------------------
             CONSUME
          ------------------------- */

          if (
            trigger.dataset.openModal ===
            'use-food-modal'
          ) {

            var useForm =
              document.getElementById(
                'use-food-form'
              );

            if (useForm) {

              useForm.action =
                trigger.dataset.formAction || '';

              var foodName =
                useForm.querySelector(
                  '[name="food_name"]'
                );

              var available =
                useForm.querySelector(
                  '[name="available_quantity"]'
                );

              var consumeQuantity =
                useForm.querySelector(
                  '[name="quantity"]'
                );


              if (foodName) {
                foodName.value =
                  trigger.dataset.name || '';
              }

              if (available) {
                available.value =
                  trigger.dataset.quantity || '';
              }

              if (consumeQuantity) {
                consumeQuantity.max =
                  trigger.dataset.quantity || '';
              }
            }
          }


          /* -------------------------
             DELETE
          ------------------------- */

          if (
            trigger.dataset.openModal ===
            'delete-pantry-modal'
          ) {

            var deleteForm =
              document.getElementById(
                'delete-pantry-form'
              );

            if (deleteForm) {

              deleteForm.action =
                trigger.dataset.formAction || '';
            }
          }


          openModal(modal);
        }
      );
    });


  document
    .querySelectorAll('[data-close-modal]')
    .forEach(function (trigger) {

      trigger.addEventListener(
        'click',
        function () {

          closeModal(
            trigger.closest('.modal-overlay')
          );
        }
      );
    });


  document
    .querySelectorAll('.modal-overlay')
    .forEach(function (overlay) {

      overlay.addEventListener(
        'click',
        function (event) {

          if (event.target === overlay) {
            closeModal(overlay);
          }
        }
      );
    });


  document.addEventListener(
    'keydown',
    function (event) {

      if (event.key === 'Escape') {

        document
          .querySelectorAll(
            '.modal-overlay.is-open'
          )
          .forEach(closeModal);
      }
    }
  );


  /* =========================================================
     REAL FORM SUBMISSION
  ========================================================= */

  function handleFormSubmit(form, successMessage) {
  if (!form) return;

  form.addEventListener('submit', function (event) {

    console.log('FORM SUBMITTED:', form.id);
    console.log('ACTION:', form.action);
    console.log('METHOD:', form.method);

    var submitButton = form.querySelector(
      'button[type="submit"]'
    );

    if (submitButton) {
      submitButton.disabled = true;
    }
  });
}

  /* ADD */

  var addForm =
    document.getElementById(
      'add-pantry-form'
    );

  handleFormSubmit(
    addForm,
    'Added to pantry.'
  );


  /* EDIT */

  var editForm =
    document.getElementById(
      'edit-pantry-form'
    );

  handleFormSubmit(
    editForm,
    'Pantry updated.'
  );


  /* CONSUME */

  var useForm =
    document.getElementById(
      'use-food-form'
    );

  handleFormSubmit(
    useForm,
    'Pantry updated.'
  );


  /* DELETE */

  var deleteForm =
    document.getElementById(
      'delete-pantry-form'
    );

  handleFormSubmit(
    deleteForm,
    'Item removed.'
  );


  /* =========================================================
     INITIAL FILTER
  ========================================================= */

  applyFilters();

})();