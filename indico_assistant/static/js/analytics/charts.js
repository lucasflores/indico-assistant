// Chart primitives for the assistant analytics pages (spec 024, FR-017): hand-written SVG, no library, ported from
// ibis-chat's public/charts.js and the bar/whisker/export helpers of its stats.js. One global: window.AssistantCharts.
// Indico's CSP allows scripts from 'self' only, so every listener is attached with addEventListener.
(function () {
  'use strict';

  // ibis-chat's categorical slots 1-8, in fixed order (dataviz validator: passes CVD and normal-vision separation
  // on a light surface; the contrast warning is why every chart has a tooltip and every number a table nearby).
  var SLOT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'];
  var OTHER = '#b4b8bf', GRID = '#e6e6e6', INK1 = '#222', INK2 = '#666';
  var SVGNS = 'http://www.w3.org/2000/svg';

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function sv(tag, attrs, text) {
    var node = document.createElementNS(SVGNS, tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  // --- formats ---------------------------------------------------------------------------------------------------
  var DASH = '—';
  function missing(v) { return v === null || v === undefined || (typeof v === 'number' && isNaN(v)); }
  function parseDay(d) { var p = String(d).slice(0, 10).split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  var fmt = {
    money: function (v) {
      if (missing(v)) return DASH;
      var a = Math.abs(v);
      return '$' + (a === 0 ? '0' : a >= 1 ? v.toFixed(2) : a >= 0.0001 ? v.toFixed(4) : String(+v.toPrecision(2)));
    },
    ms: function (v) {
      if (missing(v)) return DASH;
      return v < 1000 ? Math.round(v) + ' ms' : v < 120000 ? (v / 1000).toFixed(1) + ' s' : (v / 60000).toFixed(1) + ' min';
    },
    pct: function (v) {
      if (missing(v)) return DASH;
      var p = v * 100;
      return (p > 0 && p < 10 ? p.toFixed(1) : p.toFixed(0)) + '%';
    },
    int: function (v) { return missing(v) ? DASH : Math.round(v).toLocaleString(); },
    num: function (v) { return missing(v) ? DASH : (Math.round(v * 10) / 10).toLocaleString(); },
    // "2026-08-01" is a day in the admin's own timezone: parse it as a local date, never as UTC midnight.
    day: function (d) { return missing(d) ? DASH : parseDay(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }); },
    time: function (iso) {
      return missing(iso) ? DASH : new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
    },
  };

  // Colour follows the entity, not its rank: each palette remembers its keys for the life of the page.
  function palette(known) {
    var seen = {}, next = 0;
    (known || []).forEach(function (k) { seen[k] = SLOT[next++] || OTHER; });
    return function (key) {
      if (key === 'other') return OTHER;
      if (!(key in seen)) seen[key] = SLOT[next++] || OTHER;
      return seen[key];
    };
  }

  // --- tooltip ---------------------------------------------------------------------------------------------------
  var tooltip;
  function showTip(evt, text) {
    if (!tooltip) { tooltip = el('div', 'aa-tooltip'); document.body.appendChild(tooltip); }
    tooltip.textContent = text;
    tooltip.style.display = 'block';
    tooltip.style.left = Math.min(evt.clientX + 12, window.innerWidth - 320) + 'px';
    tooltip.style.top = (evt.clientY + 14) + 'px';
  }
  function hideTip() { if (tooltip) tooltip.style.display = 'none'; }
  function hover(node, text) {
    node.addEventListener('mousemove', function (evt) { showTip(evt, typeof text === 'function' ? text() : text); });
    node.addEventListener('mouseleave', hideTip);
  }

  // --- shared chart pieces ---------------------------------------------------------------------------------------
  function hostWidth(host) { return Math.max(320, host.clientWidth || 640); }

  function svgRoot(W, label) {
    var svg = sv('svg', { width: W, role: 'img', 'aria-label': label || '' });
    svg.style.width = '100%';
    svg.style.height = 'auto';
    return svg;
  }
  function setHeight(svg, W, H) { svg.setAttribute('height', H); svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H); }

  function empty(host, text) { host.textContent = ''; host.appendChild(el('p', 'aa-muted', text || 'Nothing in this range.')); }

  // Round tick values, not fractions of the maximum (ibis-chat).
  function niceTicks(max, integral) {
    if (!(max > 0)) return [];
    var raw = max / 4, mag = Math.pow(10, Math.floor(Math.log10(raw))), norm = raw / mag;
    var step = (norm >= 5 ? 5 : norm >= 2.5 ? 2.5 : norm >= 2 ? 2 : 1) * mag;
    if (integral) step = Math.max(1, Math.round(step));
    function build(st) {
      var out = [];
      for (var i = 1; i * st <= max * 1.000001; i++) out.push(+((i * st).toPrecision(12)));
      return out;
    }
    var ticks = build(step);
    while (ticks.length > 6) { step *= 2; ticks = build(step); }
    return ticks;
  }

  // Legend drawn inside the SVG, so a downloaded chart carries it. Returns the height it used.
  function legend(svg, series, x0, W) {
    if (series.length < 2) return 0;
    var x = x0, y = 12;
    series.forEach(function (s) {
      var w = 18 + s.name.length * 6.2;
      if (x + w > W && x > x0) { x = x0; y += 16; }
      svg.appendChild(sv('rect', { x: x, y: y - 9, width: 10, height: 10, rx: 2, fill: s.color }));
      svg.appendChild(sv('text', { x: x + 14, y: y, 'font-size': 11, fill: INK1 }, s.name));
      x += w + 10;
    });
    return y + 10;
  }

  function yAxis(svg, max, y, padL, W, fmtY, integral) {
    [0].concat(niceTicks(max, integral)).forEach(function (val) {
      svg.appendChild(sv('line', { x1: padL, x2: W - 6, y1: y(val), y2: y(val), stroke: val ? GRID : '#bbb', 'stroke-width': 1 }));
      svg.appendChild(sv('text', { x: padL - 6, y: y(val) + 3, 'text-anchor': 'end', 'font-size': 10, fill: INK2 }, fmtY(val)));
    });
  }

  function xLabels(svg, labels, x, yText) {
    var every = Math.max(1, Math.ceil(labels.length / 10));
    labels.forEach(function (label, i) {
      if (i % every === 0) svg.appendChild(sv('text', { x: x(i), y: yText, 'text-anchor': 'middle', 'font-size': 10, fill: INK2 }, label));
    });
  }

  // Keep at most 8 series: the largest 7 and "other" (a 9th hue is never generated).
  function fold(series) {
    if (series.length <= 8) return series;
    var total = function (s) { return s.values.reduce(function (a, v) { return a + (v || 0); }, 0); };
    var top = series.slice().sort(function (a, b) { return total(b) - total(a); }).slice(0, 7);
    var rest = series.filter(function (s) { return top.indexOf(s) < 0; });
    var other = { name: 'other', color: OTHER, values: series[0].values.map(function (_, i) {
      return rest.reduce(function (a, s) { return a + (s.values[i] || 0); }, 0);
    }) };
    return series.filter(function (s) { return top.indexOf(s) >= 0; }).concat([other]);
  }

  // --- charts ----------------------------------------------------------------------------------------------------

  // Vertical bars over shared labels, stacked by series: [{name, color, values: [number|null per label]}].
  function bars(host, labels, series, opts) {
    opts = opts || {};
    series = fold(series);
    var totals = labels.map(function (_, i) { return series.reduce(function (a, s) { return a + (s.values[i] || 0); }, 0); });
    var max = Math.max.apply(null, [0].concat(totals));
    if (!labels.length || !(max > 0)) return empty(host, opts.empty);
    host.textContent = '';
    var fmtY = opts.fmtY || fmt.int, W = hostWidth(host), padL = 58, padR = 6;
    var svg = svgRoot(W, opts.label);
    var padT = legend(svg, series, padL, W) + 12, plotH = opts.height || 170, H = padT + plotH + 22;
    setHeight(svg, W, H);
    function y(v) { return padT + plotH - (v / max) * plotH; }
    yAxis(svg, max, y, padL, W, fmtY, !opts.fmtY);
    var slot = (W - padL - padR) / labels.length, barW = Math.max(2, Math.min(48, slot * 0.72));
    function cx(i) { return padL + slot * (i + 0.5); }
    labels.forEach(function (label, i) {
      var acc = 0, x = cx(i) - barW / 2;
      series.forEach(function (s) {
        var v = s.values[i] || 0;
        if (v <= 0) return;
        var top = y(acc + v), bottom = acc ? y(acc) - 1 : y(0); // a 1px gap between stacked segments
        svg.appendChild(sv('rect', { x: x, y: top, width: barW, height: Math.max(1, bottom - top), rx: barW > 8 ? 2 : 0, fill: s.color }));
        acc += v;
      });
      var hit = sv('rect', { x: cx(i) - slot / 2, y: padT, width: slot, height: plotH, fill: 'transparent' });
      hover(hit, function () {
        if (series.length < 2) return label + ' — ' + fmtY(totals[i]);
        var parts = series.filter(function (s) { return s.values[i]; }).map(function (s) { return s.name + ': ' + fmtY(s.values[i]); });
        return label + ' — total ' + fmtY(totals[i]) + (parts.length ? ' · ' + parts.join(' · ') : '');
      });
      svg.appendChild(hit);
    });
    xLabels(svg, labels, cx, H - 6);
    host.appendChild(svg);
  }

  // Lines over shared labels: [{name, color, values}] (ibis-chat's lineChart, with a legend in place of end labels).
  function line(host, labels, series, opts) {
    opts = opts || {};
    var max = 0;
    series.forEach(function (s) { s.values.forEach(function (v) { if (v > max) max = v; }); });
    if (!labels.length || !(max > 0)) return empty(host, opts.empty);
    host.textContent = '';
    var fmtY = opts.fmtY || fmt.int, W = hostWidth(host), padL = 58, padR = 14;
    var svg = svgRoot(W, opts.label);
    var padT = legend(svg, series, padL, W) + 12, plotH = opts.height || 170, H = padT + plotH + 22;
    setHeight(svg, W, H);
    var innerW = W - padL - padR;
    function x(i) { return padL + (labels.length === 1 ? innerW / 2 : i * innerW / (labels.length - 1)); }
    function y(v) { return padT + plotH - (v / max) * plotH; }
    yAxis(svg, max, y, padL, W, fmtY, !opts.fmtY);
    series.forEach(function (s) {
      var d = '';
      s.values.forEach(function (v, i) { if (!missing(v)) d += (d ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); });
      svg.appendChild(sv('path', { d: d, fill: 'none', stroke: s.color, 'stroke-width': 2, 'stroke-linejoin': 'round' }));
      if (labels.length <= 40) s.values.forEach(function (v, i) { if (!missing(v)) svg.appendChild(sv('circle', { cx: x(i), cy: y(v), r: 3, fill: s.color })); });
    });
    var cross = sv('line', { x1: 0, x2: 0, y1: padT, y2: padT + plotH, stroke: INK2, 'stroke-dasharray': '2 3', opacity: 0 });
    svg.appendChild(cross);
    var half = labels.length === 1 ? innerW / 2 : innerW / (labels.length - 1) / 2;
    labels.forEach(function (label, i) {
      var hit = sv('rect', { x: x(i) - half, y: padT, width: half * 2, height: plotH, fill: 'transparent' });
      hit.addEventListener('mousemove', function (evt) {
        cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('opacity', 0.6);
        showTip(evt, label + ' — ' + series.map(function (s) { return (series.length > 1 ? s.name + ': ' : '') + fmtY(s.values[i]); }).join(' · '));
      });
      hit.addEventListener('mouseleave', function () { cross.setAttribute('opacity', 0); hideTip(); });
      svg.appendChild(hit);
    });
    xLabels(svg, labels, x, H - 6);
    host.appendChild(svg);
  }

  // Horizontal bars by category: [{label, value, back?, lo?, hi?, note?, text?, tip?, color?}]. `back` draws a lighter
  // bar behind (p90 behind p50); lo/hi a 95% interval whisker; `note` replaces the bar (a rate with too few data).
  function hbars(host, items, opts) {
    opts = opts || {};
    if (!items.length) return empty(host, opts.empty);
    host.textContent = '';
    var f = opts.fmt || fmt.int, W = hostWidth(host), rowH = 24;
    var padL = Math.min(220, 16 + Math.max.apply(null, items.map(function (it) { return String(it.label).length; })) * 6.4);
    var max = opts.max || Math.max.apply(null, items.map(function (it) { return Math.max(it.value || 0, it.back || 0, it.hi || 0); }));
    if (!(max > 0)) max = 1;
    var svg = svgRoot(W, opts.label);
    var padT = legend(svg, opts.legend || [], padL, W) + 6, H = padT + items.length * rowH + 6, plotW = W - padL - 110;
    setHeight(svg, W, H);
    function x(v) { return padL + (v / max) * plotW; }
    items.forEach(function (it, i) {
      var top = padT + i * rowH, mid = top + rowH / 2, color = it.color || opts.color || SLOT[0];
      svg.appendChild(sv('text', { x: padL - 8, y: mid + 4, 'text-anchor': 'end', 'font-size': 11, fill: INK1 }, it.label));
      if (it.note) {
        svg.appendChild(sv('text', { x: padL + 4, y: mid + 4, 'font-size': 11, fill: INK2, 'font-style': 'italic' }, it.note));
      } else {
        if (it.back) svg.appendChild(sv('rect', { x: padL, y: top + 5, width: Math.max(1, x(it.back) - padL), height: rowH - 10, rx: 3, fill: color, opacity: 0.3 }));
        svg.appendChild(sv('rect', { x: padL, y: top + 5, width: Math.max(1, x(it.value || 0) - padL), height: rowH - 10, rx: 3, fill: color }));
        if (!missing(it.lo) && !missing(it.hi)) {
          svg.appendChild(sv('line', { x1: x(it.lo), x2: x(it.hi), y1: mid, y2: mid, stroke: INK1, 'stroke-width': 1.5 }));
          [it.lo, it.hi].forEach(function (v) { svg.appendChild(sv('line', { x1: x(v), x2: x(v), y1: mid - 5, y2: mid + 5, stroke: INK1, 'stroke-width': 1.5 })); });
        }
        var end = Math.max(x(it.value || 0), it.back ? x(it.back) : 0, missing(it.hi) ? 0 : x(it.hi));
        svg.appendChild(sv('text', { x: end + 6, y: mid + 4, 'font-size': 11, fill: INK2 }, it.text || f(it.value)));
      }
      var hit = sv('rect', { x: 0, y: top, width: W, height: rowH, fill: 'transparent' });
      hover(hit, it.tip || (it.label + ': ' + (it.note || it.text || f(it.value))));
      svg.appendChild(hit);
    });
    host.appendChild(svg);
  }

  // --- PNG / SVG download (ibis-chat's chartTools, without the clipboard and the fullscreen dialog) --------------
  function exportable(svgNode, title) {
    var w = +svgNode.getAttribute('width'), h = +svgNode.getAttribute('height'), H = h + 44;
    var clone = svgNode.cloneNode(true);
    clone.setAttribute('xmlns', SVGNS);
    clone.setAttribute('height', H);
    clone.setAttribute('viewBox', '0 -26 ' + w + ' ' + H);
    clone.setAttribute('font-family', '-apple-system, "Segoe UI", Roboto, sans-serif');
    clone.removeAttribute('style');
    clone.insertBefore(sv('rect', { x: 0, y: -26, width: w, height: H, fill: '#fff' }), clone.firstChild);
    clone.appendChild(sv('text', { x: 6, y: -9, 'font-size': 13, 'font-weight': 600, fill: INK1 }, title));
    clone.appendChild(sv('text', { x: 6, y: h + 13, 'font-size': 9, fill: INK2 },
      'Indico assistant analytics · ' + title + ' · ' + new Date().toISOString().slice(0, 16) + 'Z'));
    return { node: clone, w: w, h: H };
  }

  function download(name, blob) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
  }

  function slug(title) { return title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'chart'; }

  function saveSvg(svgNode, title) {
    var ex = exportable(svgNode, title);
    download(slug(title) + '.svg', new Blob([new XMLSerializer().serializeToString(ex.node)], { type: 'image/svg+xml' }));
  }

  function savePng(svgNode, title) {
    var ex = exportable(svgNode, title), img = new Image();
    img.addEventListener('load', function () {
      var canvas = document.createElement('canvas');
      canvas.width = ex.w * 2;
      canvas.height = ex.h * 2;
      var ctx = canvas.getContext('2d');
      ctx.scale(2, 2);
      ctx.drawImage(img, 0, 0);
      canvas.toBlob(function (blob) { download(slug(title) + '.png', blob); }, 'image/png');
    });
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(ex.node));
  }

  // A titled panel holding one chart, with PNG and SVG buttons that read the chart at click time (so a redraw never
  // leaves them pointing at a stale one). opts: {wide: span the whole row, extra: a node beside the title (a switch)}.
  function figure(parent, title, draw, opts) {
    opts = opts || {};
    var box = el('div', 'aa-panel aa-figure' + (opts.wide ? ' aa-wide' : '')), head = el('div', 'aa-panel-head');
    var host = el('div', 'aa-chart');
    head.appendChild(el('h3', null, title));
    if (opts.extra) head.appendChild(opts.extra);
    var tools = el('span', 'aa-tools');
    [['PNG', savePng], ['SVG', saveSvg]].forEach(function (pair) {
      var b = el('button', 'aa-tool', pair[0]);
      b.type = 'button';
      b.title = 'Download this chart as ' + pair[0];
      b.addEventListener('click', function () { var s = host.querySelector('svg'); if (s) pair[1](s, title); });
      tools.appendChild(b);
    });
    head.appendChild(tools);
    box.appendChild(head);
    box.appendChild(host);
    parent.appendChild(box);
    draw(host);
    return host;
  }

  // --- tiles and tables ------------------------------------------------------------------------------------------
  function tile(host, value, key, note, cls) {
    var box = el('div', 'aa-tile' + (cls ? ' ' + cls : ''));
    box.appendChild(el('span', 'aa-v', value));
    box.appendChild(el('span', 'aa-k', key));
    if (note) box.appendChild(el('span', 'aa-note', note));
    host.appendChild(box);
    return box;
  }

  // columns: [[header, row => string|Node, 'num'?]]. Returns the <tbody>, so the turn list can append pages to it.
  function table(host, columns, rows, emptyText) {
    if (!rows.length && emptyText) { host.appendChild(el('p', 'aa-muted', emptyText)); return null; }
    var wrap = el('div', 'aa-table-wrap'), t = el('table', 'aa-table'), head = el('tr'), body = el('tbody');
    columns.forEach(function (c) { head.appendChild(el('th', c[2] || null, c[0])); });
    t.appendChild(el('thead')).appendChild(head);
    t.appendChild(body);
    addRows(body, columns, rows);
    wrap.appendChild(t);
    host.appendChild(wrap);
    return body;
  }
  function addRows(body, columns, rows) {
    rows.forEach(function (row) {
      var tr = el('tr');
      columns.forEach(function (c) {
        var td = el('td', c[2] || null), v = c[1](row);
        if (v instanceof Node) td.appendChild(v); else td.textContent = missing(v) ? DASH : String(v);
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  }

  window.AssistantCharts = {
    SLOT: SLOT, OTHER: OTHER, el: el, fmt: fmt, missing: missing, parseDay: parseDay, palette: palette, hover: hover,
    niceTicks: niceTicks, bars: bars, line: line, hbars: hbars, figure: figure, saveSvg: saveSvg, savePng: savePng,
    tile: tile, table: table, addRows: addRows,
  };
})();
