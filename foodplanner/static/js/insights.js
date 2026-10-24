/**
 * FoodiePlug — Insights page script
 * static/js/insights.js
 *
 * - period selector (shows the custom range fields, auto-applies other periods)
 * - insight category filter (the page works without it; chips are hidden until this runs)
 * - spending trend line chart, drawn as SVG from the JSON the backend renders
 *   into <script id="spending-series">. No chart library, no hardcoded data.
 */
(function () {
  'use strict';

  var page = document.getElementById('in-page');
  if (!page) return;

  function $(id) { return document.getElementById(id); }

  /* ------------------------------------------------------------------ period controls */
  var form = $('in-period-form');
  var select = $('in-period');
  var custom = $('in-custom');

  if (form && select && custom) {
    select.addEventListener('change', function () {
      if (select.value === 'custom') {
        custom.hidden = false;
        var start = $('in-start');
        if (start) start.focus();
      } else {
        custom.hidden = true;
        form.submit();                    // presets apply immediately
      }
    });
  }

  /* ------------------------------------------------------------------ insight filter */
  var filters = $('in-filters');
  var feed = $('in-feed');
  var feedEmpty = $('in-feed-empty');

  if (filters && feed) {
    filters.hidden = false;
    var chips = [].slice.call(filters.querySelectorAll('.in-chip'));
    var cards = [].slice.call(feed.querySelectorAll('.in-insight'));

    filters.addEventListener('click', function (e) {
      var chip = e.target.closest('.in-chip');
      if (!chip) return;
      var wanted = chip.dataset.filter;

      chips.forEach(function (c) {
        var on = c === chip;
        c.classList.toggle('is-active', on);
        c.setAttribute('aria-pressed', on ? 'true' : 'false');
      });

      var shown = 0;
      cards.forEach(function (card) {
        var match = wanted === 'all' || card.dataset.category === wanted;
        card.hidden = !match;
        if (match) shown += 1;
      });
      if (feedEmpty) feedEmpty.hidden = shown !== 0;
    });
  }

  /* ------------------------------------------------------------------ spending trend chart */
  var host = $('spending-chart');
  var dataNode = $('spending-series');
  var tip = $('spending-tip');

  if (host && dataNode) {
    var rows = [];
    try { rows = JSON.parse(dataNode.textContent) || []; } catch (e) { rows = []; }

    var SVG_NS = 'http://www.w3.org/2000/svg';

    var el = function (name, attrs) {
      var node = document.createElementNS(SVG_NS, name);
      Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
      return node;
    };

    var money = function (n) { return 'KES ' + Math.round(n).toLocaleString('en-KE'); };

    var niceMax = function (max) {
      var pow = Math.pow(10, Math.floor(Math.log10(max)));
      var n = max / pow;
      return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * pow;
    };

    var rangeText = function (r) {
      return r.start === r.end ? r.label : r.label + ' (' + r.start + ' to ' + r.end + ')';
    };

    var draw = function () {
      var old = host.querySelector('svg');
      if (old) host.removeChild(old);
      if (tip) tip.hidden = true;

      var W = Math.max(300, Math.round(host.clientWidth));
      var H = 250, L = 58, R = 14, T = 14, B = 34;
      var innerW = W - L - R, innerH = H - T - B;

      var max = 1;
      rows.forEach(function (r) { if (r.tracked && r.amount > max) max = r.amount; });
      var top = niceMax(max);

      var x = function (i) { return rows.length === 1 ? L + innerW / 2 : L + i * innerW / (rows.length - 1); };
      var y = function (v) { return T + innerH - (v / top) * innerH; };

      var tracked = rows.filter(function (r) { return r.tracked; });
      var total = tracked.reduce(function (s, r) { return s + r.amount; }, 0);

      var svg = el('svg', {
        'class': 'in-svg', viewBox: '0 0 ' + W + ' ' + H, role: 'img',
        'aria-label': 'Spending trend. Total ' + money(total) + ' across ' + rows.length + ' ' +
          (host.dataset.granularity || 'period') + (rows.length === 1 ? '' : 's') + '. The data table below lists every value.'
      });

      // grid + y axis
      for (var k = 0; k <= 4; k += 1) {
        var v = top * k / 4, yy = y(v);
        svg.appendChild(el('line', { 'class': 'in-grid-line', x1: L, x2: W - R, y1: yy, y2: yy }));
        var label = el('text', { 'class': 'in-axis-text', x: L - 8, y: yy + 4, 'text-anchor': 'end' });
        label.textContent = v >= 1000 ? (v / 1000).toLocaleString('en-KE') + 'k' : String(Math.round(v));
        svg.appendChild(label);
      }

      // x axis labels (thinned so they never overlap)
      var maxLabels = Math.max(2, Math.floor(innerW / 64));
      var step = Math.ceil(rows.length / maxLabels);
      rows.forEach(function (r, i) {
        if (i % step !== 0 && i !== rows.length - 1) return;
        var t = el('text', { 'class': 'in-axis-text', x: x(i), y: H - 10, 'text-anchor': 'middle' });
        t.textContent = r.label;
        svg.appendChild(t);
      });

      // line + area, broken wherever a bucket wasn't tracked
      var run = [];
      var flush = function () {
        if (run.length > 1) {
          var d = run.map(function (p, i) { return (i ? 'L' : 'M') + p[0] + ' ' + p[1]; }).join(' ');
          var area = d + ' L' + run[run.length - 1][0] + ' ' + y(0) + ' L' + run[0][0] + ' ' + y(0) + ' Z';
          svg.appendChild(el('path', { 'class': 'in-area', d: area }));
          svg.appendChild(el('path', { 'class': 'in-line', d: d }));
        }
        run = [];
      };
      rows.forEach(function (r, i) {
        if (r.tracked) run.push([x(i), y(r.amount)]); else flush();
      });
      flush();

      // points: focusable, with tooltips
      rows.forEach(function (r, i) {
        var cx = x(i), cy = r.tracked ? y(r.amount) : y(0);
        var text = rangeText(r) + ': ' + (r.tracked ? money(r.amount) : 'not tracked (no budget was active)');

        var g = el('g', { 'class': 'in-pt', tabindex: '0', role: 'img', 'aria-label': text });
        g.appendChild(el('circle', { 'class': 'in-hit', cx: cx, cy: cy, r: 14 }));
        g.appendChild(el('circle', { 'class': 'in-dot' + (r.tracked ? '' : ' is-gap'), cx: cx, cy: cy, r: r.tracked ? 4.5 : 4 }));

        var show = function () {
          if (!tip) return;
          var box = svg.getBoundingClientRect();
          tip.textContent = text;
          tip.style.left = (cx * box.width / W) + 'px';
          tip.style.top = (cy * box.height / H) + 'px';
          tip.hidden = false;
        };
        var hide = function () { if (tip) tip.hidden = true; };

        g.addEventListener('mouseenter', show);
        g.addEventListener('mouseleave', hide);
        g.addEventListener('focus', show);
        g.addEventListener('blur', hide);
        svg.appendChild(g);
      });

      host.insertBefore(svg, host.firstChild);
    };

    if (rows.length) {
      draw();
      var timer = null;
      window.addEventListener('resize', function () {
        clearTimeout(timer);
        timer = setTimeout(draw, 150);
      });
    }
  }
})();