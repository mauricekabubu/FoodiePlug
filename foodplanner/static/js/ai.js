/**
 * FoodiePlug — AI Assistant page script
 * static/js/ai.js
 *
 * Owns all AI Assistant behaviour:
 *   - sending messages and rendering replies (text, rich cards, action buttons)
 *   - honest loading / error / "not connected yet" states
 *   - confirmation before any action that changes user data
 *   - context source switches (what FoodiePlug data the AI may use)
 *   - new / open / rename / delete conversation
 *   - mobile "Your data" bottom sheet
 *
 * dashboard.js stays global. Nothing here invents an answer: if the chat
 * endpoint is "#" (not wired yet) the page says so instead of faking a reply.
 *
 * Every string from the server is inserted with textContent, never innerHTML.
 *
 * Conversation endpoint (data-conversation-url) contract:
 *   GET    -> { id, title, messages: [{ role: "user"|"assistant", content, cards?, actions? }] }
 *   PATCH  -> { title }                (rename)
 *   DELETE -> 2xx                      (delete)
 * The URL in the template contains a 32-character placeholder
 * (00000000000000000000000000000000) which urlFor() swaps for the real id.
 */
(function () {
  'use strict';

  var page = document.getElementById('ai-page');
  if (!page) return;

  function $(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  /* ------------------------------------------------------------------ config */
  var cfg = $('ai-config') ? $('ai-config').dataset : {};
  function configured(url) { return !!url && url !== '#'; }
  var chatUrl = cfg.chatUrl;
  var conversationUrl = cfg.conversationUrl;

  var ID_PLACEHOLDER = '00000000000000000000000000000000';

  // Swaps the 32-zero placeholder in the template URL for the real conversation id.
  function urlFor(template, id) {
    if (!template || id === undefined || id === null || id === '') {
      throw new Error('Conversation URL or ID is missing.');
    }
    if (template.indexOf(ID_PLACEHOLDER) === -1) {
      throw new Error('Conversation URL placeholder was not found in: ' + template);
    }
    var realId = String(id).trim();
    if (!realId || realId === ID_PLACEHOLDER) {
      throw new Error('Refusing to request a conversation with a missing or placeholder ID: "' + realId + '"');
    }
    // Function replacer: the id is inserted literally, never parsed for "$&"-style patterns.
    var url = template.replace(ID_PLACEHOLDER, function () { return encodeURIComponent(realId); });
    if (url.indexOf(ID_PLACEHOLDER) !== -1) {
      throw new Error('Conversation URL still contains the placeholder: ' + url);
    }
    return url;
  }

  function safeUrl(u) { return typeof u === 'string' && /^(\/(?!\/)|#)/.test(u) ? u : '#'; }

  var csrfInput = document.querySelector('#ai-form input[name="csrfmiddlewaretoken"]');
  function csrf() { return csrfInput ? csrfInput.value : ''; }

  var log = $('ai-log');
  var welcome = $('ai-welcome');
  var chips = $('ai-chips');
  var input = $('ai-input');
  var sendBtn = $('ai-send');
  var form = $('ai-form');

  var state = { conversationId: null, busy: false, lastMessage: null };
  var actionStore = {};
  var actionSeq = 0;
  var openingConversation = false;

  var STRINGS = {
    notConnected: "FoodiePlug AI isn't connected to the server yet, so I can't answer this. Your FoodiePlug data hasn't been changed.",
    data: "I couldn't access your FoodiePlug data right now.",
    llm: "I couldn't generate a response right now. Your FoodiePlug data hasn't been changed.",
    network: "I couldn't reach FoodiePlug AI right now. Your FoodiePlug data hasn't been changed.",
    rate: "You've reached your AI usage limit for now. You can try again later."
  };

  var BASIS = {
    data: 'Your data',
    calculated: 'Calculated',
    estimate: 'Estimate',
    general: 'General guidance',
    ai: 'AI suggestion'
  };

  var SPARK = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M12 3l1.4 3.6L17 8l-3.6 1.4L12 13l-1.4-3.6L7 8l3.6-1.4L12 3z"/></svg>';

  /* ------------------------------------------------------------------ toasts */
  function toast(message, level) {
    level = level || 'success';
    if (typeof window.showToast === 'function') { window.showToast(message, level); return; }
    var container = $('toast-container');
    if (!container) return;
    var t = el('div', 'toast toast-' + level, message);
    container.appendChild(t);
    setTimeout(function () { t.remove(); }, 4000);
  }

  /* ------------------------------------------------------------------ status */
  (function initStatus() {
    var status = $('ai-status');
    if (!status || configured(chatUrl)) return;
    status.classList.add('is-offline');
    $('ai-status-text').textContent = "FoodiePlug AI isn't connected yet";
  })();

  /* ------------------------------------------------------------------ context sources */
  var PREF_KEY = 'foodieplug-ai-context';
  var switches = [].slice.call(document.querySelectorAll('[data-source]'));

  function loadPrefs() {
    try { return JSON.parse(localStorage.getItem(PREF_KEY)) || {}; } catch (e) { return {}; }
  }
  function savePrefs() {
    var prefs = {};
    switches.forEach(function (s) { if (!s.disabled) prefs[s.dataset.source] = s.checked; });
    try { localStorage.setItem(PREF_KEY, JSON.stringify(prefs)); } catch (e) {}
  }
  function enabledSources() {
    return switches.filter(function (s) { return s.checked && !s.disabled; })
                   .map(function (s) { return s.dataset.source; });
  }

  (function initSources() {
    var prefs = loadPrefs();
    switches.forEach(function (s) {
      if (!s.disabled && prefs[s.dataset.source] === false) s.checked = false;
      s.addEventListener('change', savePrefs);
    });
  })();

  /* ------------------------------------------------------------------ message rendering */
  function renderText(container, text) {
    String(text || '').split(/\n{2,}/).forEach(function (block) {
      var lines = block.split('\n').filter(function (l) { return l.trim() !== ''; });
      if (!lines.length) return;

      var bullet = /^\s*[-*\u2022]\s+/;
      var numbered = /^\s*\d+[.)]\s+/;

      if (lines.every(function (l) { return bullet.test(l); })) {
        var ul = el('ul');
        lines.forEach(function (l) { ul.appendChild(el('li', null, l.replace(bullet, ''))); });
        container.appendChild(ul);
      } else if (lines.every(function (l) { return numbered.test(l); })) {
        var ol = el('ol');
        lines.forEach(function (l) { ol.appendChild(el('li', null, l.replace(numbered, ''))); });
        container.appendChild(ol);
      } else {
        var p = el('p');
        lines.forEach(function (l, i) {
          if (i) p.appendChild(document.createElement('br'));
          p.appendChild(document.createTextNode(l));
        });
        container.appendChild(p);
      }
    });
  }

  function buildCard(card) {
    var type = card.type || '';
    var node = el('section', 'ai-card' +
      (type.indexOf('shopping') > -1 ? ' is-shopping' : '') +
      (type.indexOf('budget') > -1 ? ' is-budget' : '') +
      (type.indexOf('pantry') > -1 ? ' is-pantry' : '') +
      (card.tone === 'warn' ? ' is-warn' : ''));

    var head = el('div', 'ai-card-head');
    head.appendChild(el('h3', null, card.title || 'Suggestion'));
    if (card.basis && BASIS[card.basis]) head.appendChild(el('span', 'ai-basis', BASIS[card.basis]));
    node.appendChild(head);

    if (card.highlight && card.highlight.value) {
      var hl = el('p', 'ai-highlight');
      hl.appendChild(el('span', null, card.highlight.label || ''));
      hl.appendChild(el('strong', null, card.highlight.value));
      node.appendChild(hl);
    }

    if (card.items && card.items.length) {
      var items = el('ul', 'ai-items');
      card.items.forEach(function (it) {
        var li = el('li');
        var have = it.status === 'have';
        var missing = it.status === 'missing';
        if (have || missing) {
          var mark = el('span', have ? 'ai-mark-have' : 'ai-mark-missing', have ? '\u2713' : '\u2715');
          mark.setAttribute('aria-hidden', 'true');
          li.appendChild(mark);
          li.appendChild(el('span', 'ai-sr', have ? 'In your pantry: ' : 'Missing: '));
        }
        li.appendChild(el('span', null, it.name || ''));
        if (it.note) li.appendChild(el('small', null, it.note));
        items.appendChild(li);
      });
      node.appendChild(items);
    }

    if (card.rows && card.rows.length) {
      var rows = el('dl', 'ai-rows');
      card.rows.forEach(function (r) {
        var row = el('div');
        row.appendChild(el('dt', null, r.label || ''));
        row.appendChild(el('dd', null, r.value || ''));
        rows.appendChild(row);
      });
      node.appendChild(rows);
    }

    if (card.points && card.points.length) {
      var pts = el('ul', 'ai-points');
      card.points.forEach(function (p) { pts.appendChild(el('li', null, p)); });
      node.appendChild(pts);
    }

    if (card.actions && card.actions.length) node.appendChild(buildActions(card.actions));
    return node;
  }

  function buildActions(actions) {
    var wrap = el('div', 'ai-actions');
    actions.forEach(function (a) {
      if (!a || !a.label) return;
      if (a.kind === 'link') {
        var link = el('a', a.primary ? 'btn-solid' : 'btn-outline', a.label);
        link.href = safeUrl(a.url);
        wrap.appendChild(link);
      } else {
        var btn = el('button', a.primary ? 'btn-solid' : 'btn-outline', a.label);
        btn.type = 'button';
        var id = String(++actionSeq);
        actionStore[id] = a;
        btn.dataset.actionId = id;
        wrap.appendChild(btn);
      }
    });
    return wrap;
  }

  function scrollToEnd() { log.scrollTop = log.scrollHeight; }

  function showConversation() {
    welcome.hidden = true;
    if (chips && chips.children.length) chips.hidden = false;
  }

  function addUser(text) {
    showConversation();
    var msg = el('div', 'ai-msg is-user');
    msg.appendChild(el('div', 'ai-msg-who', 'You'));
    var body = el('div', 'ai-msg-body');
    renderText(body, text);
    msg.appendChild(body);
    log.appendChild(msg);
    scrollToEnd();
    return msg;
  }

  function addAI(opts) {
    showConversation();
    var msg = el('div', 'ai-msg is-ai' +
      (opts.variant === 'error' ? ' is-error' : '') +
      (opts.variant === 'success' ? ' is-success' : ''));

    var who = el('div', 'ai-msg-who');
    var mark = el('span', 'ai-mark');
    mark.innerHTML = SPARK;                       // constant markup, no user data
    who.appendChild(mark);
    who.appendChild(el('span', null, 'FoodiePlug AI'));
    msg.appendChild(who);

    var body = el('div', 'ai-msg-body');
    if (opts.text) renderText(body, opts.text);

    if (opts.cards && opts.cards.length) {
      var cards = el('div', 'ai-cards');
      opts.cards.forEach(function (c) { cards.appendChild(buildCard(c)); });
      body.appendChild(cards);
    }
    if (opts.actions && opts.actions.length) body.appendChild(buildActions(opts.actions));

    msg.appendChild(body);
    log.appendChild(msg);
    scrollToEnd();
    return msg;
  }

  function addLoading() {
    showConversation();
    var msg = el('div', 'ai-msg is-ai');
    var who = el('div', 'ai-msg-who');
    who.appendChild(el('span', null, 'FoodiePlug AI'));
    msg.appendChild(who);

    var body = el('div', 'ai-msg-body');
    var typing = el('span', 'ai-typing');
    typing.appendChild(el('span', null, 'FoodiePlug AI is working on your question\u2026'));
    var dots = el('span', 'ai-dots');
    dots.setAttribute('aria-hidden', 'true');
    dots.appendChild(document.createElement('i'));
    dots.appendChild(document.createElement('i'));
    dots.appendChild(document.createElement('i'));
    typing.appendChild(dots);
    body.appendChild(typing);
    msg.appendChild(body);
    log.appendChild(msg);
    scrollToEnd();
    return msg;
  }

  /* ------------------------------------------------------------------ sending */
  function setBusy(on) {
    state.busy = on;
    page.setAttribute('aria-busy', on ? 'true' : 'false');
    updateSend();
  }

  function updateSend() {
    sendBtn.disabled = state.busy || !input.value.trim();
  }

  function autosize() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 160) + 'px';
  }

  function errorMessage(status, data) {
    var code = data && data.error && data.error.code;
    if (status === 429 || code === 'rate_limit') return { text: STRINGS.rate, variant: 'error' };
    var text = code === 'data' ? STRINGS.data : STRINGS.llm;
    return {
      text: text,
      variant: 'error',
      actions: [{ kind: 'retry', label: 'Try again' }]
    };
  }

  async function requestAI(text) {
    if (!configured(chatUrl)) {
      addAI({ text: STRINGS.notConnected, variant: 'error' });
      return;
    }

    setBusy(true);
    var loading = addLoading();

    try {
      var res = await fetch(chatUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          'X-CSRFToken': csrf()
        },
        body: JSON.stringify({
          message: text,
          conversation_id: state.conversationId,
          context: { sources: enabledSources() }
        })
      });

      var data = null;
      try { data = await res.json(); } catch (e) { data = null; }
      loading.remove();

      if (!res.ok || (data && data.error)) {
        addAI(errorMessage(res.status, data));
      } else if (!data || (typeof data.response !== 'string' && !(data.cards && data.cards.length))) {
        addAI(errorMessage(res.status, null));
      } else {
        if (data.conversation_id) setConversation(data.conversation_id, data.conversation_title || text);
        addAI({ text: data.response, cards: data.cards, actions: data.actions });
      }
    } catch (err) {
      loading.remove();
      addAI({ text: STRINGS.network, variant: 'error', actions: [{ kind: 'retry', label: 'Try again' }] });
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  function sendMessage(text) {
    text = (text || '').trim();
    if (!text || state.busy) return;
    state.lastMessage = text;
    addUser(text);
    input.value = '';
    autosize();
    updateSend();
    requestAI(text);
  }

  /* ------------------------------------------------------------------ actions (always backend-authoritative) */
  function lc(label) { return String(label || 'do that').toLowerCase(); }

  async function runAction(action, button) {
    if (button) button.disabled = true;

    if (!configured(action.endpoint)) {
      addAI({ text: "I couldn't " + lc(action.label) + ". Actions aren't connected yet, so nothing was changed.", variant: 'error' });
      if (button) button.disabled = false;
      return;
    }

    var failure = function () {
      addAI({
        text: "I couldn't " + lc(action.label) + ". Nothing was changed.",
        variant: 'error',
        actions: [{ kind: 'api', label: 'Try again', endpoint: action.endpoint, payload: action.payload }]
      });
      if (button) button.disabled = false;
    };

    try {
      var res = await fetch(action.endpoint, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRFToken': csrf() },
        body: JSON.stringify(action.payload || {})
      });
      var data = null;
      try { data = await res.json(); } catch (e) { data = null; }

      if (res.ok && !(data && data.ok === false)) {
        addAI({ text: (data && data.message) || 'Done.', cards: data && data.cards, actions: data && data.actions, variant: 'success' });
        if (button) button.textContent = action.label + ' \u2713';
      } else {
        failure();
      }
    } catch (err) {
      failure();
    }
  }

  /* ------------------------------------------------------------------ modals (this file owns them) */
  var modals = [].slice.call(document.querySelectorAll('.ai-modal'));
  var modalOrigin = null;
  var pressOnBackdrop = false;
  var pending = null;     // { type: 'action'|'delete'|'rename', ... }

  function openModals() { return modals.filter(function (m) { return m.classList.contains('is-open'); }); }

  function openModal(modal, origin) {
    modalOrigin = origin || document.activeElement;
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    window.requestAnimationFrame(function () {
      var target = modal.querySelector('input[type="text"]') || modal.querySelector('.btn-solid');
      if (target) target.focus();
    });
  }

  function closeModal(modal, restoreFocus) {
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    if (!openModals().length) {
      document.body.classList.remove('modal-open');
      if (restoreFocus !== false && modalOrigin && document.body.contains(modalOrigin)) modalOrigin.focus();
      modalOrigin = null;
    }
  }

  function confirm(opts, origin) {
    $('ai-confirm-title').textContent = opts.title || 'Please confirm';
    $('ai-confirm-text').textContent = opts.text || '';
    var ok = $('ai-confirm-ok');
    ok.textContent = opts.label || 'Confirm';
    ok.classList.toggle('is-danger', !!opts.danger);
    openModal($('ai-confirm-modal'), origin);
  }

  $('ai-confirm-ok').addEventListener('click', function () {
    var job = pending;
    pending = null;
    closeModal($('ai-confirm-modal'), false);
    if (!job) return;
    if (job.type === 'action') runAction(job.action, job.button);
    else if (job.type === 'delete') deleteConversation(job.id, job.item);
  });

  $('ai-rename-ok').addEventListener('click', function () {
    var job = pending;
    var title = $('ai-rename-input').value.trim();
    if (!job || job.type !== 'rename' || !title) return;
    pending = null;
    closeModal($('ai-rename-modal'), false);
    renameConversation(job.id, title, job.item);
  });

  document.addEventListener('click', function (e) {
    var top = openModals().pop();
    if (!top) return;
    var closer = e.target.closest('[data-close-modal]');
    if (closer && top.contains(closer)) {
      e.preventDefault();
      e.stopPropagation();
      pending = null;
      closeModal(top);
      return;
    }
    if (e.target === top && pressOnBackdrop) { pending = null; closeModal(top); }
  }, true);

  document.addEventListener('mousedown', function (e) {
    pressOnBackdrop = !!(e.target.classList && e.target.classList.contains('ai-modal'));
  }, true);

  document.addEventListener('keydown', function (e) {
    var top = openModals().pop();
    if (top) {
      if (e.key === 'Escape') { e.preventDefault(); pending = null; closeModal(top); return; }
      if (e.key === 'Tab') {
        var f = top.querySelectorAll('button:not([disabled]), input:not([disabled])');
        if (!f.length) return;
        var first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
      return;
    }
    if (e.key === 'Escape' && sheetOpen()) closeSheet();
  });

  /* ------------------------------------------------------------------ conversations */
  function setActive(id) {
    [].slice.call(document.querySelectorAll('#ai-history li[data-conversation-id]')).forEach(function (li) {
      li.classList.toggle('is-active', String(li.dataset.conversationId) === String(id));
    });
  }

  function buildHistoryItem(id, title) {
    var li = el('li');
    li.dataset.conversationId = id;

    var link = el('a', null, title);
    link.href = '#';
    link.dataset.openConversation = id;
    li.appendChild(link);

    var rename = el('button', 'icon-btn');
    rename.type = 'button';
    rename.dataset.renameConversation = id;
    rename.dataset.title = title;
    rename.setAttribute('aria-label', 'Rename ' + title);
    rename.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true"><path d="M4 20l1-4 11-11 3 3-11 11-4 1z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    li.appendChild(rename);

    var del = el('button', 'icon-btn');
    del.type = 'button';
    del.dataset.deleteConversation = id;
    del.dataset.title = title;
    del.setAttribute('aria-label', 'Delete ' + title);
    del.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true"><path d="M5 7h14M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m-9 0l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    li.appendChild(del);
    return li;
  }

  function setConversation(id, title) {
    var isNew = String(state.conversationId) !== String(id);
    state.conversationId = id;
    if (isNew && !document.querySelector('#ai-history li[data-conversation-id="' + id + '"]')) {
      var history = $('ai-history');
      var empty = $('ai-history-empty');
      if (empty) empty.remove();

      var list = history.querySelector('ul[data-today]');
      if (!list) {
        var label = el('p', 'ai-history-group', 'Today');
        list = el('ul', 'ai-history');
        list.dataset.today = '1';
        history.insertBefore(list, history.firstChild);
        history.insertBefore(label, list);
      }
      var short = String(title).length > 60 ? String(title).slice(0, 57) + '\u2026' : String(title);
      list.insertBefore(buildHistoryItem(id, short), list.firstChild);
    }
    setActive(id);
  }

  function newConversation() {
    if (state.busy) return;
    [].slice.call(log.querySelectorAll('.ai-msg')).forEach(function (m) { m.remove(); });
    welcome.hidden = false;
    if (chips) chips.hidden = true;
    state.conversationId = null;
    state.lastMessage = null;
    setActive(null);
    input.value = '';
    autosize();
    updateSend();
    input.focus();
  }

  // Accepts { messages: [...] } or { conversation: { messages: [...] } } and role/sender/human naming.
  function normalizeMessages(data) {
    var list = data && (data.messages || (data.conversation && data.conversation.messages));
    if (!Array.isArray(list)) return null;
    return list.map(function (m) {
      var role = String(m.role || m.sender || '').toLowerCase();
      var content = m.content != null ? m.content : (m.text != null ? m.text : m.message);
      return {
        role: (role === 'user' || role === 'human') ? 'user' : 'assistant',
        content: content,
        cards: m.cards,
        actions: m.actions
      };
    });
  }

  function httpError(message, status) {
    var e = new Error(message);
    e.status = status;
    return e;
  }

  async function openConversation(id) {
    if (openingConversation || state.busy) return;

    if (!configured(conversationUrl)) {
      toast("Opening past conversations isn't available yet.", 'error');
      return;
    }

    openingConversation = true;
    var url = null;

    try {
      url = urlFor(conversationUrl, id);

      var res = await fetch(url, {
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' }
      });

      // A login redirect or an error page must not be parsed as JSON.
      if (res.redirected) throw httpError('Redirected to ' + res.url, 401);
      if (!res.ok) throw httpError('HTTP ' + res.status, res.status);

      var type = res.headers.get('content-type') || '';
      if (type.indexOf('application/json') === -1) {
        throw httpError('Expected JSON but received "' + type + '" from ' + res.url, res.status);
      }

      var data = await res.json();
      var messages = normalizeMessages(data);
      if (!messages) throw httpError('Response has no messages array', res.status);

      newConversation();
      messages.forEach(function (m) {
        if (m.role === 'user') addUser(m.content);
        else addAI({ text: m.content, cards: m.cards, actions: m.actions });
      });

      state.conversationId = data.id || data.conversation_id || id;
      setActive(state.conversationId);
      closeSheet();
    } catch (err) {
      console.error('openConversation failed', { id: id, url: url, error: err });

      var message = "I couldn't open that conversation. Nothing was changed.";
      if (err.status === 404) message = 'That conversation could not be found. It may have been deleted.';
      else if (err.status === 403) message = "You don't have access to that conversation.";
      else if (err.status === 401) message = 'Your session expired. Please sign in again.';
      toast(message, 'error');
    } finally {
      openingConversation = false;
    }
  }

  async function renameConversation(id, title, item) {
    if (!configured(conversationUrl)) { toast("Renaming conversations isn't available yet.", 'error'); return; }
    try {
      var res = await fetch(urlFor(conversationUrl, id), {
        method: 'PATCH',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRFToken': csrf() },
        body: JSON.stringify({ title: title })
      });
      if (!res.ok) throw httpError('HTTP ' + res.status, res.status);
      if (item) {
        item.querySelector('a').textContent = title;
        [].slice.call(item.querySelectorAll('button')).forEach(function (b) { b.dataset.title = title; });
      }
      toast('Conversation renamed.');
    } catch (err) {
      console.error('renameConversation failed', { id: id, error: err });
      toast("I couldn't rename that conversation. Nothing was changed.", 'error');
    }
  }

  async function deleteConversation(id, item) {
    if (!configured(conversationUrl)) { toast("Deleting conversations isn't available yet.", 'error'); return; }
    try {
      var res = await fetch(urlFor(conversationUrl, id), {
        method: 'DELETE',
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json', 'X-CSRFToken': csrf() }
      });
      if (!res.ok) throw httpError('HTTP ' + res.status, res.status);
      if (item) item.remove();
      if (String(state.conversationId) === String(id)) newConversation();
      toast('Conversation deleted.');
    } catch (err) {
      console.error('deleteConversation failed', { id: id, error: err });
      toast("I couldn't delete that conversation. Nothing was changed.", 'error');
    }
  }

  /* ------------------------------------------------------------------ mobile sheet */
  var sheet = $('ai-context');
  var scrim = $('ai-scrim');
  var sheetBtn = $('ai-context-open');

  function sheetOpen() { return sheet.classList.contains('is-open'); }
  function openSheet() {
    sheet.classList.add('is-open');
    scrim.classList.add('is-open');
    sheetBtn.setAttribute('aria-expanded', 'true');
    var close = $('ai-context-close');
    if (close) close.focus();
  }
  function closeSheet() {
    if (!sheetOpen()) return;
    sheet.classList.remove('is-open');
    scrim.classList.remove('is-open');
    sheetBtn.setAttribute('aria-expanded', 'false');
    sheetBtn.focus();
  }

  sheetBtn.addEventListener('click', function () { sheetOpen() ? closeSheet() : openSheet(); });
  $('ai-context-close').addEventListener('click', closeSheet);
  scrim.addEventListener('click', closeSheet);

  /* ------------------------------------------------------------------ wiring */
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    sendMessage(input.value);
  });

  input.addEventListener('input', function () { autosize(); updateSend(); });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      sendMessage(input.value);
    }
  });

  $('ai-new').addEventListener('click', newConversation);

  document.addEventListener('click', function (e) {
    // suggested prompts (welcome cards + chips)
    var prompt = e.target.closest('[data-prompt]');
    if (prompt && page.contains(prompt)) {
      e.preventDefault();
      sendMessage(prompt.dataset.prompt);
      return;
    }

    // action buttons inside AI messages
    var actionBtn = e.target.closest('button[data-action-id]');
    if (actionBtn) {
      var action = actionStore[actionBtn.dataset.actionId];
      if (!action) return;

      if (action.kind === 'retry') {
        if (state.lastMessage && !state.busy) requestAI(state.lastMessage);
        return;
      }
      if (action.confirm) {
        pending = { type: 'action', action: action, button: actionBtn };
        confirm({
          title: action.confirm.title || 'Please confirm',
          text: action.confirm.text || 'Apply this change to your FoodiePlug data?',
          label: action.confirm.label || action.label
        }, actionBtn);
      } else {
        runAction(action, actionBtn);
      }
      return;
    }

    // conversation history
    var open = e.target.closest('[data-open-conversation]');
    if (open) { e.preventDefault(); openConversation(open.dataset.openConversation); return; }

    var rename = e.target.closest('[data-rename-conversation]');
    if (rename) {
      pending = { type: 'rename', id: rename.dataset.renameConversation, item: rename.closest('li') };
      $('ai-rename-input').value = rename.dataset.title || '';
      openModal($('ai-rename-modal'), rename);
      return;
    }

    var del = e.target.closest('[data-delete-conversation]');
    if (del) {
      pending = { type: 'delete', id: del.dataset.deleteConversation, item: del.closest('li') };
      confirm({
        title: 'Delete conversation?',
        text: '\u201c' + (del.dataset.title || 'This conversation') + '\u201d will be deleted. This can\u2019t be undone.',
        label: 'Delete',
        danger: true
      }, del);
    }
  });

  updateSend();
})();