(function () {
  'use strict';

  /* ---------------- search ---------------- */

  // Small in-page index standing in for a real search API. Replace with a
  // fetch() to your search/help-article backend when one exists.
  var HELP_INDEX = [
    { title: "How do I reset my password?", description: "Steps to reset a forgotten FoodiePlug password by email.", category: "Account & Login", keywords: "password reset forgot login" },
    { title: "How do I change my password?", description: "Update your password from your account settings.", category: "Account & Login", keywords: "password change update security" },
    { title: "I can't log in to my account", description: "Common reasons login might fail and how to fix them.", category: "Troubleshooting", keywords: "password login cant sign in" },
    { title: "Why isn't my password being accepted?", description: "Password requirements and common formatting issues.", category: "Account & Login", keywords: "password accepted invalid requirements" },
    { title: "How do I create a FoodiePlug account?", description: "Steps to register and set up your FoodiePlug profile.", category: "Account & Login", keywords: "create account register signup" },
    { title: "How do I change my username or email?", description: "Update your identifying account details.", category: "Account & Login", keywords: "username email change update" },
    { title: "How does FoodiePlug create my meal plan?", description: "How preferences, budget, and AI suggestions combine into a plan.", category: "Meal Planning", keywords: "meal plan create how works" },
    { title: "Can I change my food preferences?", description: "Update dietary preferences any time from account settings.", category: "Meal Planning", keywords: "preferences dietary change food" },
    { title: "How does FoodiePlug use my grocery prices?", description: "How user-entered prices power budgeting estimates.", category: "Budget & Prices", keywords: "grocery prices budget estimate" },
    { title: "Are FoodiePlug food prices always accurate?", description: "Why prices are estimates and can vary by location and time.", category: "Budget & Prices", keywords: "prices accurate estimate vary" },
    { title: "How does the AI food assistant work?", description: "What FoodiePlug's AI-powered recommendations do and don't do.", category: "AI Food Assistant", keywords: "ai assistant recommendations how works" },
    { title: "Can I delete my account?", description: "Steps to close and delete your FoodiePlug account.", category: "Account Settings", keywords: "delete account close remove" },
    { title: "How do I contact FoodiePlug support?", description: "Ways to reach the FoodiePlug support team.", category: "Troubleshooting", keywords: "contact support help reach" }
  ];

  var searchInput = document.getElementById('help-search');
  var searchWrap = document.querySelector('.search-wrap');
  var clearBtn = document.querySelector('.search-clear');
  var resultsSection = document.getElementById('search-results');
  var resultsList = document.getElementById('results-list');
  var resultsHeading = document.getElementById('results-heading');
  var noResults = document.getElementById('no-results');
  var browseContent = document.querySelectorAll('.browse-content');

  function renderResults(query) {
    var q = query.trim().toLowerCase();

    if (!q) {
      resultsSection.classList.remove('is-visible');
      browseContent.forEach(function (el) { el.classList.remove('is-hidden'); });
      return;
    }

    browseContent.forEach(function (el) { el.classList.add('is-hidden'); });
    resultsSection.classList.add('is-visible');

    var matches = HELP_INDEX.filter(function (item) {
      var haystack = (item.title + ' ' + item.description + ' ' + item.category + ' ' + item.keywords).toLowerCase();
      return haystack.indexOf(q) !== -1;
    });

    resultsHeading.textContent = 'Search results for \u2018' + query.trim() + '\u2019';

    if (matches.length === 0) {
      resultsList.innerHTML = '';
      noResults.classList.add('is-visible');
      return;
    }

    noResults.classList.remove('is-visible');
    resultsList.innerHTML = matches.map(function (item) {
      return (
        '<div class="result-item">' +
          '<div class="result-item-text">' +
            '<h3>' + escapeHtml(item.title) + '</h3>' +
            '<p>' + escapeHtml(item.description) + '</p>' +
            '<span class="tag">' + escapeHtml(item.category) + '</span>' +
          '</div>' +
          '<span class="arrow" aria-hidden="true">\u2192</span>' +
        '</div>'
      );
    }).join('');
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      searchWrap.classList.toggle('has-value', searchInput.value.length > 0);
      renderResults(searchInput.value);
    });

    searchInput.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        searchInput.value = '';
        searchWrap.classList.remove('has-value');
        renderResults('');
      }
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      searchInput.value = '';
      searchWrap.classList.remove('has-value');
      renderResults('');
      searchInput.focus();
    });
  }

  /* ---------------- FAQ accordion (single-open) ---------------- */

  document.querySelectorAll('.faq-item').forEach(function (item) {
    var question = item.querySelector('.faq-question');
    var answer = item.querySelector('.faq-answer');
    if (!question || !answer) return;

    question.addEventListener('click', function () {
      var isOpen = item.getAttribute('data-open') === 'true';
      document.querySelectorAll('.faq-item[data-open="true"]').forEach(function (openItem) {
        if (openItem !== item) {
          openItem.setAttribute('data-open', 'false');
          openItem.querySelector('.faq-question').setAttribute('aria-expanded', 'false');
          openItem.querySelector('.faq-answer').style.maxHeight = null;
        }
      });

      item.setAttribute('data-open', String(!isOpen));
      question.setAttribute('aria-expanded', String(!isOpen));
      answer.style.maxHeight = isOpen ? null : answer.scrollHeight + 'px';
    });
  });

  /* ---------------- article feedback ---------------- */

  var feedbackYes = document.getElementById('feedback-yes');
  var feedbackNo = document.getElementById('feedback-no');
  var followup = document.getElementById('feedback-followup');
  var feedbackSubmit = document.getElementById('feedback-submit');
  var feedbackThanks = document.getElementById('feedback-thanks');

  if (feedbackYes && feedbackNo) {
    feedbackYes.addEventListener('click', function () {
      feedbackYes.classList.add('is-selected');
      feedbackNo.classList.remove('is-selected');
      if (followup) followup.classList.remove('is-visible');
      if (feedbackThanks) feedbackThanks.classList.add('is-visible');
    });

    feedbackNo.addEventListener('click', function () {
      feedbackNo.classList.add('is-selected');
      feedbackYes.classList.remove('is-selected');
      if (feedbackThanks) feedbackThanks.classList.remove('is-visible');
      if (followup) followup.classList.add('is-visible');
    });
  }

  if (feedbackSubmit) {
    feedbackSubmit.addEventListener('click', function () {
      if (followup) followup.classList.remove('is-visible');
      if (feedbackThanks) feedbackThanks.classList.add('is-visible');
    });
  }
})();