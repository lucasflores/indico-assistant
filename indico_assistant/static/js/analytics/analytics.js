// The assistant's analytics page and trace page (spec 024, FR-014..FR-021). Both draw only what the admin JSON API
// returns. The page is picked by its container: #assistant-analytics (the stats, the turn list) or #assistant-trace
// (one turn). The range and filters live in location.hash, so a link reproduces the view. Charts: charts.js.
(function () {
  'use strict';
  var C = window.AssistantCharts, el = C.el, f = C.fmt;

  var STAGES = {
    QueryClassification: 'Classifier', SQLGeneration: 'SQL generator', SQLCorrection: 'Correction',
    ResponseSummary: 'Formatter', KnowledgeAnswer: 'Knowledge answer', ChatAnswer: 'Chat answer', PlanDraft: 'Planner',
    Lookup: 'Tool loop', Step: 'Tool loop', Final: 'Tool loop',
  };
  var KINDS = { llm: 'model call', sql: 'query', jev: 'Jev', tool: 'tool call' };
  var ROUTES = ['data', 'knowledge', 'chat', 'change', 'connector', 'none'];
  var OUTCOMES = ['answered', 'failed', 'timeout', 'access_denied', 'refusal', 'cannot_plan'];
  var RANGES = [['24h', '24 hours'], ['7d', '7 days'], ['30d', '30 days'], ['90d', '90 days'], ['all', 'All']];
  var TEXT_ORDER = ['prompt', 'response', 'sql', 'rows'];
  var MIN_RATE = 10; // FR-016's minimum for rates the payload sends as raw counts (tool failures)
  var color = { route: C.palette(ROUTES), stage: C.palette(), model: C.palette(), kind: C.palette(['llm', 'sql', 'jev', 'tool']), error: C.palette() };

  function stage(name) { return STAGES[name] || name || '—'; }
  function gate(r, what) { return r && 'min' in r ? 'not enough ' + (what ? what + ' ' : '') + '(' + r.n + ' of ' + r.min + ')' : null; }
  function rateText(r, what) { return !r ? '—' : gate(r, what) || f.pct(r.rate); }
  function sum(rows, key) { return rows.reduce(function (a, r) { return a + (r[key] || 0); }, 0); }
  function append(parent, child) { parent.appendChild(child); return child; }

  // --- state in the hash, and the API ----------------------------------------------------------------------------
  function readHash() {
    var s = {};
    location.hash.replace(/^#/, '').split('&').forEach(function (pair) {
      var i = pair.indexOf('=');
      try { if (i > 0) s[decodeURIComponent(pair.slice(0, i))] = decodeURIComponent(pair.slice(i + 1)); } catch (e) { /* skip */ }
    });
    return s;
  }

  function setHash(patch) {
    var s = readHash();
    Object.keys(patch).forEach(function (k) { if (patch[k] === null || patch[k] === '') delete s[k]; else s[k] = String(patch[k]); });
    location.hash = Object.keys(s).map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(s[k]); }).join('&');
  }

  function nextDay(day) { var d = C.parseDay(day); d.setDate(d.getDate() + 1); return isoDay(d); }
  function isoDay(d) { return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }

  // The API's query for a state: the range (or since/until, "until" inclusive in the page) and the filters.
  function query(s, extra) {
    var p = new URLSearchParams();
    if (s.since) { p.set('since', s.since); if (s.until) p.set('until', nextDay(s.until)); } else p.set('range', s.range || '30d');
    ['route', 'model', 'user', 'event', 'category', 'admins'].forEach(function (k) { if (s[k]) p.set(k, s[k]); });
    Object.keys(extra || {}).forEach(function (k) { if (extra[k] !== undefined && extra[k] !== null && extra[k] !== '') p.set(k, extra[k]); });
    return p.toString();
  }

  function getJSON(url) {
    return fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } }).then(function (res) {
      return res.text().then(function (body) {
        var data = null;
        try { data = JSON.parse(body); } catch (e) { /* not JSON */ }
        if (!res.ok) {
          var err = data && (data.message || data.description || (data.error && (data.error.message || data.error.title)));
          throw new Error('Error ' + res.status + ': ' + (err || res.statusText || body.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 200)));
        }
        if (data === null) throw new Error('The server did not answer with JSON.');
        return data;
      });
    });
  }

  // --- small builders --------------------------------------------------------------------------------------------
  function section(body, title, note) {
    var box = append(body, el('section', 'aa-section'));
    box.appendChild(el('h2', null, title));
    if (note) box.appendChild(el('p', 'aa-muted', note));
    return append(box, el('div', 'aa-grid'));
  }

  function panel(grid, title, wide, note) {
    var box = append(grid, el('div', 'aa-panel' + (wide ? ' aa-wide' : '')));
    box.appendChild(el('div', 'aa-panel-head')).appendChild(el('h3', null, title));
    if (note) box.appendChild(el('p', 'aa-muted', note));
    return box;
  }

  function tiles(parent) { return append(parent, el('div', 'aa-tiles')); }

  function link(text, href) { var a = el('a', null, text); a.href = href; return a; }

  function button(text, cls, onClick) {
    var b = el('button', cls, text);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  }

  function labelled(text, control, after) {
    var l = el('label', 'aa-control');
    if (!after) l.appendChild(el('span', null, text));
    l.appendChild(control);
    if (after) l.appendChild(el('span', null, text));
    return l;
  }

  function select(values, current, anyText, onChange, labelOf) {
    var sel = el('select');
    [''].concat(values).forEach(function (v) {
      var o = el('option', null, v ? (labelOf ? labelOf(v) : v) : anyText);
      o.value = v;
      sel.appendChild(o);
    });
    sel.value = current || '';
    sel.addEventListener('change', function () { onChange(sel.value); });
    return sel;
  }

  // --- days: one shared axis for every per-day chart ---------------------------------------------------------------
  function dayIn(iso, tz) {
    try {
      var p = {};
      new Intl.DateTimeFormat('en-US', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' })
        .formatToParts(new Date(iso)).forEach(function (x) { p[x.type] = x.value; });
      return p.year + '-' + p.month + '-' + p.day;
    } catch (e) { return String(iso).slice(0, 10); }
  }

  // The range's days in the admin's timezone; for a long range ("all"), from the first day with data.
  function dayList(d) {
    var seen = [].concat(d.adoption.turns, d.adoption.users.daily, d.cost.spend.route, d.errors.by_type)
      .map(function (r) { return r.day; }).sort();
    if (!seen.length) return [];
    var tz = d.params.tz, start = dayIn(d.params.since, tz);
    var end = dayIn(new Date(new Date(d.params.until).getTime() - 1).toISOString(), tz);
    if (seen[seen.length - 1] > end) end = seen[seen.length - 1];
    if (start > seen[0] || (C.parseDay(end) - C.parseDay(start)) / 864e5 > 400) start = seen[0];
    var out = [], day = start;
    while (day <= end && out.length < 1000) { out.push(day); day = nextDay(day); }
    return out;
  }

  // Rows {day, <key>, <value>} as stacked series over the day axis; `label` merges keys that share a label.
  function perDay(rows, days, key, value, colorOf, label) {
    var at = {}, by = {};
    days.forEach(function (day, i) { at[day] = i; });
    rows.forEach(function (r) {
      var k = label ? label(r[key]) : String(r[key]);
      by[k] = by[k] || days.map(function () { return 0; });
      if (r.day in at) by[k][at[r.day]] += r[value] || 0;
    });
    return Object.keys(by).sort(function (a, b) { return rank(a) - rank(b) || (a < b ? -1 : 1); })
      .map(function (k) { return { name: k, color: colorOf(k), values: by[k] }; });
  }

  // ===== the analytics page ======================================================================================
  function analyticsPage(root) {
    var ds = root.dataset, ctx = { urls: { stats: ds.statsUrl, turns: ds.turnsUrl, exp: ds.exportUrl, turn: ds.turnPage }, set: setHash };
    root.textContent = '';
    var header = append(root, el('div', 'aa-header')), status = append(root, el('div', 'aa-status'));
    var body = append(root, el('div', 'aa-body'));
    var data = null, statsQuery = null, token = 0;

    function load() {
      var s = readHash(), q = query(s);
      ctx.state = s;
      drawHeader(header, s, data, ctx);
      if (q === statsQuery && data) { if (ctx.reloadTurns) ctx.reloadTurns(); return; } // only the outcome changed
      statsQuery = q;
      var mine = ++token;
      status.className = 'aa-status aa-loading';
      status.textContent = 'Loading…';
      body.classList.add('aa-stale');
      getJSON(ctx.urls.stats + '?' + q).then(function (payload) {
        if (mine !== token) return;
        data = payload;
        status.className = 'aa-status';
        status.textContent = '';
        body.classList.remove('aa-stale');
        drawHeader(header, s, data, ctx);
        drawAll(body, data, ctx);
      }).catch(function (err) {
        if (mine !== token) return;
        statsQuery = null;
        status.className = 'aa-status aa-error';
        status.textContent = 'Could not load the analytics. ' + err.message;
        body.classList.remove('aa-stale');
        body.textContent = '';
      });
    }
    window.addEventListener('hashchange', load);
    load();
  }

  function drawHeader(host, s, d, ctx) {
    host.textContent = '';
    var top = append(host, el('div', 'aa-row')), filters = append(host, el('div', 'aa-row'));
    var tabs = append(top, el('div', 'aa-tabs'));
    RANGES.forEach(function (r) {
      var b = tabs.appendChild(button(r[1], 'aa-tab', function () { ctx.set({ range: r[0], since: null, until: null }); }));
      b.dataset.range = r[0];
      if (!s.since && (s.range || '30d') === r[0]) b.classList.add('active');
    });
    var from = el('input'), to = el('input');
    from.type = to.type = 'date';
    from.value = s.since || '';
    to.value = s.until || '';
    [from, to].forEach(function (input) {
      input.addEventListener('change', function () { if (from.value) ctx.set({ since: from.value, until: to.value || null, range: null }); });
    });
    top.appendChild(labelled('From', from));
    top.appendChild(labelled('to', to));

    var routes = [], models = [];
    if (d && d.facets) {  // (the range's routes and models, whatever the filters: picking one keeps the others)
      routes = routes.concat(d.facets.routes);
      models = models.concat(d.facets.models);
    }
    if (s.route) routes.push(s.route);
    if (s.model) models.push(s.model);
    routes = unique(routes).sort(function (a, b) { return rank(a) - rank(b) || (a < b ? -1 : 1); });
    filters.appendChild(labelled('Route', select(routes, s.route, 'All routes', function (v) { ctx.set({ route: v }); })));
    filters.appendChild(labelled('Model', select(unique(models).sort(), s.model, 'All models', function (v) { ctx.set({ model: v }); })));
    var admins = el('input');
    admins.type = 'checkbox';
    admins.checked = s.admins === '1';
    admins.addEventListener('change', function () { ctx.set({ admins: admins.checked ? '1' : null }); });
    filters.appendChild(labelled('Include admins', admins, true));
    [['user', 'User'], ['event', 'Event'], ['category', 'Category']].forEach(function (pair) {
      if (!s[pair[0]]) return;
      var name = d ? nameOf(d, pair[0], s[pair[0]]) : null;
      var chip = button(pair[1] + ' ' + (name ? name + ' (#' + s[pair[0]] + ')' : '#' + s[pair[0]]) + ' ×', 'aa-chip', function () {
        var patch = {};
        patch[pair[0]] = null;
        ctx.set(patch);
      });
      chip.title = 'Remove this filter';
      filters.appendChild(chip);
    });
    var exp = append(filters, el('span', 'aa-export')), q = query(s);
    exp.appendChild(link('Export CSV', ctx.urls.exp + '?' + q));
    exp.appendChild(document.createTextNode(' · '));
    exp.appendChild(link('with text', ctx.urls.exp + '?' + q + '&text=1'));
  }

  function unique(xs) { return xs.filter(function (x, i) { return x && xs.indexOf(x) === i; }); }
  function rank(route) { var i = ROUTES.indexOf(route); return i < 0 ? 99 : i; }

  function nameOf(d, kind, id) {
    var rows = kind === 'user' ? d.cost.spenders : kind === 'event' ? d.adoption.events : d.adoption.categories;
    var hit = rows.filter(function (r) { return String(r[kind === 'user' ? 'user_id' : kind + '_id']) === String(id); })[0];
    return hit ? hit.name || hit.title : null;
  }

  function drawAll(body, d, ctx) {
    body.textContent = '';
    ctx.reloadTurns = null;
    if (!d.tiles.turns) { body.appendChild(el('p', 'aa-empty', 'No turns in this range.')); return; }
    ctx.days = dayList(d);
    ctx.labels = ctx.days.map(f.day);
    [overview, adoption, cost, speed, quality, routing, depth, plans, errors, turnList].forEach(function (draw) { draw(body, d, ctx); });
  }

  function filterLink(text, patch, ctx) { return button(text, 'aa-link', function () { ctx.set(patch); }); }
  function traceLink(ctx, id, text) { return link(text, ctx.urls.turn + id + '/'); }

  // --- sections --------------------------------------------------------------------------------------------------
  function overview(body, d) {
    var t = d.tiles, row = tiles(append(section(body, 'Overview'), el('div', 'aa-wide')));
    C.tile(row, f.int(t.turns), 'turns');
    C.tile(row, f.int(t.users), 'active users');
    C.tile(row, f.money(t.spend), 'spend', t.calls ? f.pct(t.unpriced_share) + ' of calls not priced (' + t.unpriced + ' of ' + t.calls + ')' : null,
      t.unpriced_share > 0.1 ? 'aa-warn' : '');
    C.tile(row, f.ms(t.p50_ms), 'median answer time');
    var sat = t.satisfaction;
    if ('min' in sat) C.tile(row, '—', 'satisfaction', 'not enough ratings (' + sat.n + ' of ' + sat.min + ')');
    else C.tile(row, f.pct(sat.rate), 'satisfaction', '95% interval ' + f.pct(sat.lo) + '–' + f.pct(sat.hi) + ' · ' + sat.n + ' ratings');
    C.tile(row, f.money(t.cost_per_helpful), 'cost per helpful answer');
  }

  function adoption(body, d, ctx) {
    var g = section(body, 'Adoption'), a = d.adoption;
    C.figure(g, 'Turns per day, by route', function (h) {
      C.bars(h, ctx.labels, perDay(a.turns, ctx.days, 'route', 'turns', color.route), { label: 'Turns per day by route' });
    }, { wide: true });
    C.figure(g, 'Active users per day', function (h) {
      C.line(h, ctx.labels, perDay(a.users.daily.map(function (r) { return { day: r.day, k: 'users', users: r.users }; }), ctx.days, 'k', 'users', function () { return C.SLOT[0]; }));
    });
    C.figure(g, 'Active users per week', function (h) {
      C.bars(h, a.users.weekly.map(function (r) { return 'week of ' + f.day(r.week); }), [{ name: 'users', color: C.SLOT[0], values: a.users.weekly.map(function (r) { return r.users; }) }]);
    });
    var chats = tiles(panel(g, 'Chats and returning users'));
    C.tile(chats, f.int(a.chats.chats), 'chats');
    C.tile(chats, f.num(a.chats.turns_per_chat_p50), 'turns per chat (median)', 'at most ' + f.int(a.chats.turns_per_chat_max));
    C.tile(chats, f.int(a.returning.returning) + ' of ' + f.int(a.returning.users), 'returning users', 'had asked before this range');
    C.table(panel(g, 'Top events', false, 'Click one to filter by it.'), [
      ['Event', function (r) {
        var cell = el('span');
        cell.appendChild(filterLink(r.title || 'Event #' + r.event_id, { event: r.event_id }, ctx));
        if (r.deleted) cell.appendChild(el('span', 'aa-badge', 'deleted'));
        return cell;
      }],
      ['Turns', function (r) { return f.int(r.turns); }, 'num'],
    ], a.events, 'No event pages in this range.');
    C.table(panel(g, 'Top categories', false, 'Click one to filter by it.'), [
      ['Category', function (r) { return filterLink(r.title || 'Category #' + r.category_id, { category: r.category_id }, ctx); }],
      ['Turns', function (r) { return f.int(r.turns); }, 'num'],
    ], a.categories, 'No categories in this range.');
  }

  function cost(body, d, ctx) {
    var g = section(body, 'Cost & tokens', 'Spend is what the providers billed; calls they did not price are left out, never estimated.');
    var c = d.cost, by = 'route', sw = el('span', 'aa-switch'), host;
    ['route', 'stage', 'model'].forEach(function (k) {
      sw.appendChild(button('by ' + k, 'aa-tab' + (k === by ? ' active' : ''), function (evt) {
        by = k;
        Array.prototype.forEach.call(sw.children, function (b) { b.classList.toggle('active', b === evt.target); });
        draw(host);
      }));
    });
    function draw(h) {
      C.bars(h, ctx.labels, perDay(c.spend[by], ctx.days, 'key', 'spend', color[by], by === 'stage' ? stage : null), { fmtY: f.money, label: 'Spend per day by ' + by });
    }
    host = C.figure(g, 'Spend per day', draw, { wide: true, extra: sw });
    C.table(panel(g, 'Cost per turn, by route'), [
      ['Route', function (r) { return r.route; }],
      ['Priced turns', function (r) { return f.int(r.n); }, 'num'],
      ['Median', function (r) { return f.money(r.p50); }, 'num'],
      ['p90', function (r) { return f.money(r.p90); }, 'num'],
    ], c.per_turn, 'No priced turns.');
    C.table(panel(g, 'Tokens by stage'), [
      ['Stage', function (r) { return stage(r.stage); }],
      ['Kind', function (r) { return KINDS[r.kind] || r.kind; }],
      ['Calls', function (r) { return f.int(r.calls); }, 'num'],
      ['Tokens in', function (r) { return f.int(r.prompt); }, 'num'],
      ['Tokens out', function (r) { return f.int(r.completion); }, 'num'],
    ], c.tokens, 'No model calls.');
    C.table(panel(g, 'Top spenders', false, 'Click one to filter by the user.'), [
      ['User', function (r) { return r.user_id === null ? 'deleted user' : filterLink((r.name || 'User') + ' #' + r.user_id, { user: r.user_id }, ctx); }],
      ['Turns', function (r) { return f.int(r.turns); }, 'num'],
      ['Spend', function (r) { return f.money(r.spend); }, 'num'],
    ], c.spenders, 'No priced turns.');
    C.table(panel(g, 'Costliest turns'), [
      ['Turn', function (r) { return traceLink(ctx, r.id, '#' + r.id + ' · ' + f.time(r.started_at)); }, 'aa-nowrap'],
      ['Route', function (r) { return r.route; }],
      ['Model calls', function (r) { return f.int(r.llm_calls); }, 'num'],
      ['Cost', function (r) { return f.money(r.cost_usd); }, 'num'],
    ], c.costliest, 'No priced turns.');
  }

  function speed(body, d) {
    var g = section(body, 'Speed'), sp = d.speed, row = tiles(append(g, el('div', 'aa-wide')));
    function p(x) { return x.n ? 'p90 ' + f.ms(x.p90) + ' · ' + f.int(x.n) + (x.n === 1 ? ' sample' : ' samples') : 'none in this range'; }
    C.tile(row, f.ms(sp.queue.p50), 'queue wait (median)', p(sp.queue));
    C.tile(row, f.ms(sp.sql.p50), 'query time (median)', p(sp.sql));
    C.tile(row, f.ms(sp.jev.p50), 'Jev time (median)', p(sp.jev));
    C.tile(row, f.int(sp.time_limit_hits), 'time-limit hits', 'answers stopped by the soft limit', sp.time_limit_hits ? 'aa-warn' : '');
    C.figure(g, 'Answer time by route (median, p90 lighter)', function (h) {
      C.hbars(h, sp.latency.map(function (r) {
        return { label: r.route, value: r.p50, back: r.p90, color: color.route(r.route),
          text: f.ms(r.p50) + ' · p90 ' + f.ms(r.p90), tip: r.route + ': median ' + f.ms(r.p50) + ', p90 ' + f.ms(r.p90) + ' (' + r.n + ' turns)' };
      }), { fmt: f.ms, empty: 'No finished turns.' });
    });
    C.table(panel(g, 'Step time, by kind and stage'), [
      ['Kind', function (r) { return KINDS[r.kind] || r.kind; }],
      ['Stage', function (r) { return stage(r.stage); }],
      ['Steps', function (r) { return f.int(r.n); }, 'num'],
      ['Median', function (r) { return f.ms(r.p50); }, 'num'],
      ['p90', function (r) { return f.ms(r.p90); }, 'num'],
    ], sp.steps, 'No steps.');
    C.table(panel(g, 'Model time, by model'), [
      ['Model', function (r) { return r.model; }],
      ['Calls', function (r) { return f.int(r.n); }, 'num'],
      ['Median', function (r) { return f.ms(r.p50); }, 'num'],
      ['p90', function (r) { return f.ms(r.p90); }, 'num'],
    ], sp.models, 'No model calls.');
  }

  function satisfactionItems(rows, colorOf) {
    return rows.map(function (r) {
      var note = gate(r, 'ratings');
      return note ? { label: r.key, note: note }
        : { label: r.key, value: r.rate, lo: r.lo, hi: r.hi, color: colorOf ? colorOf(r.key) : C.SLOT[0],
          text: f.pct(r.rate) + ' (' + f.pct(r.lo) + '–' + f.pct(r.hi) + ', n ' + r.n + ')',
          tip: r.key + ': ' + f.pct(r.rate) + ' helpful, 95% interval ' + f.pct(r.lo) + '–' + f.pct(r.hi) + ' (' + r.n + ' ratings)' };
    });
  }

  function quality(body, d, ctx) {
    var g = section(body, 'Quality'), q = d.quality, sat = q.satisfaction;
    [['route', color.route], ['intent', null], ['model', color.model]].forEach(function (pair) {
      C.figure(g, 'Helpful share by ' + pair[0], function (h) {
        C.hbars(h, satisfactionItems(sat[pair[0]], pair[1]), { max: 1, fmt: f.pct, empty: 'No ratings in this range.' });
      });
    });
    var health = tiles(panel(g, 'Ratings and data answers'));
    C.tile(health, rateText(q.unrated), 'answers left unrated', q.unrated && !('min' in q.unrated) ? 'of ' + f.int(q.unrated.n) + ' answered' : null);
    [['answered', 'data answers answered'], ['corrected', 'needed a correction'], ['timed_out', 'had a query time out'],
      ['empty', 'returned no rows'], ['truncated', 'were cut off']].forEach(function (pair) {
      var r = q.data[pair[0]];
      C.tile(health, rateText(r), pair[1], r && !('min' in r) ? 'of ' + f.int(r.n) + ' data answers' : null);
    });
    C.table(panel(g, 'Thumbs-down queue', true, 'Newest first, with the comment while the chat exists.'), [
      ['Time', function (r) { return f.time(r.started_at); }, 'aa-nowrap'],
      ['Route', function (r) { return r.route; }],
      ['Model', function (r) { return r.model; }],
      ['Cost', function (r) { return f.money(r.cost_usd); }, 'num'],
      ['Wait', function (r) { return f.ms(r.wait_ms); }, 'num'],
      ['Comment', function (r) { return r.private ? el('span', 'aa-badge', 'private') : r.comment; }, 'aa-comment'],
      ['Trace', function (r) { return traceLink(ctx, r.id, 'open #' + r.id); }],
    ], q.queue, 'No thumbs-down in this range.');
    var outcomes = unique(q.outcomes.map(function (r) { return r.outcome; })), byRoute = {};
    q.outcomes.forEach(function (r) { (byRoute[r.route] = byRoute[r.route] || { route: r.route })[r.outcome] = r.turns; });
    C.table(panel(g, 'Outcomes by route'), [['Route', function (r) { return r.route; }]].concat(outcomes.map(function (o) {
      return [o.replace(/_/g, ' '), function (r) { return r[o] ? f.int(r[o]) : ''; }, 'num'];
    })), Object.keys(byRoute).sort(function (a, b) { return rank(a) - rank(b); }).map(function (k) { return byRoute[k]; }), 'No turns.');
    C.table(panel(g, 'Issue reports by kind', false, 'Every report made in the range; the filters do not apply.'), [
      ['Kind', function (r) { return r.kind; }],
      ['Reports', function (r) { return f.int(r.reports); }, 'num'],
      ['Citing an answer', function (r) { return f.int(r.with_turn); }, 'num'],
    ], q.reports, 'No issue reports in this range.');
  }

  function routing(body, d) {
    var g = section(body, 'Routing'), r = d.routing, buckets = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    // width_bucket gives 1..10, 11 for a confidence of exactly 1.0 and 0 below 0: fold them into the end buckets
    r.jev_confidence.forEach(function (b) { buckets[Math.min(9, Math.max(0, b.bucket - 1))] += b.turns; });
    C.figure(g, 'Jev confidence', function (h) {
      C.bars(h, buckets.map(function (_, i) { return (i / 10).toFixed(1) + '–' + ((i + 1) / 10).toFixed(1); }),
        [{ name: 'turns', color: C.SLOT[6], values: buckets }], { empty: 'Jev decided no routes in this range.' });
    });
    C.table(panel(g, 'Jev skipped, by reason'), [
      ['Reason', function (x) { return x.reason || 'unknown'; }],
      ['Calls', function (x) { return f.int(x.calls); }, 'num'],
    ], r.jev_skips, 'Jev was never skipped in this range.');
    C.table(panel(g, 'How the route was decided'), [
      ['Decided by', function (x) { return x.decided_by; }],
      ['Fallback', function (x) { return x.fallback || '—'; }],
      ['Turns', function (x) { return f.int(x.turns); }, 'num'],
    ], r.decided_by, 'No turns.');
    C.table(panel(g, 'Thumbs-down and reports, by route'), [
      ['Route', function (x) { return x.route; }],
      ['Thumbs-down', function (x) { return f.int(x.thumbs_down); }, 'num'],
      ['Reports', function (x) { return f.int(x.reports); }, 'num'],
    ], r.negative, 'No turns.');
  }

  function depth(body, d) {
    var g = section(body, 'Agent depth'), dp = d.depth;
    C.table(panel(g, 'Model calls per turn, by route'), [
      ['Route', function (r) { return r.route; }],
      ['Turns', function (r) { return f.int(r.n); }, 'num'],
      ['Mean', function (r) { return f.num(r.mean); }, 'num'],
      ['Median', function (r) { return f.num(r.p50); }, 'num'],
      ['p90', function (r) { return f.num(r.p90); }, 'num'],
      ['Max', function (r) { return f.int(r.max); }, 'num'],
    ], dp.calls, 'No finished turns.');
    C.figure(g, 'Correction loops per data answer', function (h) {
      C.bars(h, dp.corrections.map(function (r) { return r.corrections === 1 ? '1 correction' : r.corrections + ' corrections'; }),
        [{ name: 'turns', color: C.SLOT[0], values: dp.corrections.map(function (r) { return r.turns; }) }], { empty: 'No data answers.' });
    });
    C.table(panel(g, 'Tool calls, by tool', true), [
      ['Tool', function (r) { return r.tool; }],
      ['Calls', function (r) { return f.int(r.calls); }, 'num'],
      ['Failed', function (r) { return f.int(r.failed); }, 'num'],
      ['Failure rate', function (r) { return r.calls < MIN_RATE ? 'not enough (' + r.calls + ' of ' + MIN_RATE + ')' : f.pct(r.failed / r.calls); }, 'num'],
      ['Median time', function (r) { return f.ms(r.p50_ms); }, 'num'],
    ], dp.tools, 'No tool calls in this range.');
  }

  function plans(body, d) {
    var g = section(body, 'Plans', 'Plans made in the range; of the filters, only the user applies.'), fu = d.plans.funnel;
    C.figure(g, 'Plan funnel', function (h) {
      if (!fu.shown) { h.appendChild(el('p', 'aa-muted', 'No plans made in this range.')); return; }
      C.hbars(h, [['shown', fu.shown], ['confirmed', fu.confirmed], ['done', fu.done], ['undone', fu.undone]].map(function (p, i) {
        return { label: p[0], value: p[1], color: C.SLOT[i], text: f.int(p[1]) + (i ? ' (' + f.pct(p[1] / fu.shown) + ' of shown)' : '') };
      }));
    });
    var box = panel(g, 'Time to confirm, and failed plans by action'), row = tiles(box);
    C.tile(row, fu.n ? f.ms(fu.p50) : '—', 'time to confirm (median)', fu.n ? 'p90 ' + f.ms(fu.p90) + ' · ' + fu.n + ' confirmed' : 'none confirmed');
    C.table(box, [
      ['Action', function (r) { return r.action; }],
      ['Status', function (r) { return r.status; }],
      ['Plans', function (r) { return f.int(r.plans); }, 'num'],
    ], d.plans.failures, 'No failed plans in this range.');
  }

  function errors(body, d, ctx) {
    var g = section(body, 'Errors'), e = d.errors;
    C.figure(g, 'Errors per day, by kind', function (h) {
      C.bars(h, ctx.labels, perDay(e.by_type, ctx.days, 'kind', 'errors', color.error), { empty: 'No errors in this range.' });
    }, { wide: true });
    var row = tiles(panel(g, 'Answers with no end record', true,
      'Turns past the hard time limit that never wrote an end: the worker died, or the final write failed (the worker log tells which).'));
    C.tile(row, f.int(e.no_end_record), 'no end record', null, e.no_end_record ? 'aa-bad' : '');
    C.tile(row, f.int(sum(e.by_type, 'errors')), 'errors in this range');
  }

  // --- the turn list ---------------------------------------------------------------------------------------------
  function turnColumns(ctx) {
    return [
      ['Turn', function (r) { return traceLink(ctx, r.id, '#' + r.id + ' · ' + f.time(r.started_at)); }, 'aa-nowrap'],
      ['User', function (r) { return r.user_id === null ? 'deleted user' : (r.user_name || 'User') + ' #' + r.user_id + (r.is_admin ? ' (admin)' : ''); }],
      ['Route', function (r) { return r.route; }],
      ['Outcome', function (r) {
        var o = r.outcome || 'running';
        return el('span', o === 'answered' ? null : 'aa-badge aa-badge-bad', o.replace(/_/g, ' ') + (r.error_code ? ': ' + r.error_code : ''));
      }],
      ['Cost', function (r) { return f.money(r.cost_usd); }, 'num'],
      ['Calls', function (r) { return f.int(r.llm_calls); }, 'num'],
      ['Wait', function (r) { return f.ms(r.wait_ms); }, 'num'],
      ['Rating', function (r) { return r.rating === 1 ? 'helpful' : r.rating === -1 ? el('span', 'aa-badge aa-badge-bad', 'not helpful') : ''; }],
      ['Text', function (r) { return r.private ? el('span', 'aa-badge', 'private') : ''; }],
    ];
  }

  function turnList(body, d, ctx) {
    var g = section(body, 'Turns'), box = panel(g, 'Newest first', true), host = el('div');
    var outcome = select(OUTCOMES, ctx.state.outcome, 'Any outcome', function (v) { ctx.set({ outcome: v }); }, function (o) { return o.replace(/_/g, ' '); });
    box.querySelector('.aa-panel-head').appendChild(labelled('Outcome', outcome));
    box.appendChild(host);
    var columns = turnColumns(ctx), token = 0;
    function page(before, tbody, more) {
      var mine = ++token;
      if (!before) { host.textContent = ''; host.appendChild(el('p', 'aa-muted', 'Loading turns…')); }
      getJSON(ctx.urls.turns + '?' + query(ctx.state, { outcome: ctx.state.outcome, before: before })).then(function (res) {
        if (mine !== token) return;
        if (!before) { host.textContent = ''; tbody = C.table(host, columns, res.turns, 'No turns match.'); } else C.addRows(tbody, columns, res.turns);
        if (more) more.remove();
        if (res.next_before) host.appendChild(button('Load more', 'aa-more', function (evt) { evt.target.disabled = true; page(res.next_before, tbody, evt.target); }));
      }).catch(function (err) {
        if (mine !== token) return;
        if (more) more.disabled = false;
        host.appendChild(el('p', 'aa-error', 'Could not load the turns. ' + err.message));
      });
    }
    ctx.reloadTurns = function () { outcome.value = ctx.state.outcome || ''; page(null); };
    page(null);
  }

  // ===== the trace page ==========================================================================================
  function tracePage(root) {
    root.textContent = '';
    var status = append(root, el('p', 'aa-status aa-loading', 'Loading the trace…'));
    getJSON(root.dataset.traceUrl).then(function (d) { status.remove(); drawTrace(root, d); }).catch(function (err) {
      status.className = 'aa-status aa-error';
      status.textContent = 'Could not load this turn. ' + err.message;
    });
  }

  function ms(a, b) { return a && b ? new Date(b) - new Date(a) : null; }

  function facts(host, pairs) {
    var grid = append(host, el('dl', 'aa-facts'));
    pairs.forEach(function (p) {
      if (p[1] === null || p[1] === undefined || p[1] === '') return;
      var box = append(grid, el('div', 'aa-fact'));
      box.appendChild(el('dt', null, p[0]));
      box.appendChild(el('dd', null, p[1]));
    });
  }

  function drawTrace(root, d) {
    var t = d.turn, head = append(root, el('section', 'aa-section'));
    head.appendChild(el('h2', null, 'Turn #' + t.id + ' · ' + f.time(t.started_at)));
    var outcome = (t.outcome || 'no end record').replace(/_/g, ' ') + (t.error_code ? ' (' + t.error_code + ')' : '');
    facts(head, [
      ['Started', f.time(t.started_at)],
      ['User', t.user_id === null ? 'deleted user' : '#' + t.user_id + (t.is_admin ? ' (admin)' : '')],
      ['Event', t.event_id ? '#' + t.event_id + (t.category_id ? ' in category #' + t.category_id : '') : null],
      ['Route', t.route || 'none'],
      ['Decided by', [t.decided_by || 'not recorded', t.jev_confidence === null ? null : 'confidence ' + t.jev_confidence.toFixed(2),
        t.fallback ? 'fallback: ' + t.fallback : null].filter(Boolean).join(' · ')],
      ['Outcome', outcome],
      ['Model calls', f.int(t.llm_calls)],
      ['Tokens in / out', f.int(t.prompt_tokens) + ' / ' + f.int(t.completion_tokens)],
      ['Cost', f.money(t.cost_usd)],
      ['Unpriced calls', f.int(t.unpriced_calls)],
      ['Answer time', f.ms(ms(t.queued_at || t.started_at, t.finished_at))],
      ['Queue wait', f.ms(ms(t.queued_at, t.started_at))],
      ['Intent', t.intent],
      ['Corrections', t.corrections === null ? null : f.int(t.corrections)],
      ['Rows', t.row_count === null ? null : f.int(t.row_count) + (t.truncated ? ' (cut off)' : '')],
      ['Query time', t.sql_ms === null ? null : f.ms(t.sql_ms)],
      ['Tool calls', t.tool_calls === null ? null : f.int(t.tool_calls)],
      ['Text', t.private ? 'private' : d.text === 'kept' ? 'kept' : 'no longer kept'],
    ]);

    var qa = append(root, el('section', 'aa-section'));
    qa.appendChild(el('h2', null, 'Question and answer'));
    if (d.text === 'private') qa.appendChild(el('p', 'aa-notice', "No text is kept for this answer (it read the user's GitHub data)."));
    else if (d.text !== 'kept') qa.appendChild(el('p', 'aa-notice', 'The text of this answer is no longer kept.'));
    else {
      [['Question', d.question], ['Answer', d.answer]].forEach(function (p) {
        qa.appendChild(el('h3', null, p[0]));
        qa.appendChild(el('div', 'aa-message', p[1] || '(not in the chat any more)'));
      });
    }

    var tl = append(root, el('section', 'aa-section'));
    tl.appendChild(el('h2', null, 'Timeline'));
    timeline(tl, d.steps, t);

    var fb = append(root, el('section', 'aa-section'));
    fb.appendChild(el('h2', null, 'Rating'));
    fb.appendChild(el('p', null, t.rating === 1 ? 'Helpful' : t.rating === -1 ? 'Not helpful' : 'Not rated'));
    if (d.comment) fb.appendChild(el('div', 'aa-message', d.comment));

    if (d.plan) {
      var pl = append(root, el('section', 'aa-section'));
      pl.appendChild(el('h2', null, 'Plan'));
      facts(pl, [['Status', d.plan.status], ['Summary', d.plan.summary], ['Made', f.time(d.plan.created_at)],
        ['Confirmed', d.plan.confirmed_at ? f.time(d.plan.confirmed_at) : 'not confirmed'],
        ['Finished', d.plan.finished_at ? f.time(d.plan.finished_at) : null]]);
      var ol = append(pl, el('ol', 'aa-plan-steps'));
      (d.plan.steps || []).forEach(function (s) { ol.appendChild(el('li', null, s)); });
    }

    var rp = append(root, el('section', 'aa-section'));
    rp.appendChild(el('h2', null, 'Issue reports'));
    C.table(rp, [
      ['Report', function (r) { return r.url ? link('#' + r.id, r.url) : '#' + r.id; }],
      ['Kind', function (r) { return r.category; }],
      ['Status', function (r) { return r.status; }],
      ['Made', function (r) { return f.time(r.created_at); }],
    ], d.reports, 'No issue report cites this answer.');

    if (t.record) {
      var det = append(append(root, el('section', 'aa-section')), el('details', 'aa-text'));
      det.appendChild(el('summary', null, 'Route record (JSON)'));
      det.appendChild(el('pre', null, JSON.stringify(t.record, null, 2)));
    }
  }

  function pretty(text) {
    var s = String(text).trim();
    if (s[0] === '{' || s[0] === '[') { try { return JSON.stringify(JSON.parse(s), null, 2); } catch (e) { /* not JSON */ } }
    return text;
  }

  function stepMeta(s) {
    var parts = [], model = s.requested_model && s.served_model && s.requested_model !== s.served_model
      ? s.requested_model + ' → ' + s.served_model : s.served_model || s.requested_model;
    if (model) parts.push(model);
    if (s.ibis_chosen || s.ibis_dial) parts.push('ibis picked ' + (s.ibis_chosen || '?') + (s.ibis_dial ? ' (' + s.ibis_dial + ')' : ''));
    if (s.prompt_tokens !== null || s.completion_tokens !== null) parts.push('tokens ' + f.int(s.prompt_tokens) + ' in / ' + f.int(s.completion_tokens) + ' out');
    if (s.cost_usd !== null) parts.push(f.money(s.cost_usd));
    else if (s.kind === 'llm' || s.kind === 'jev') parts.push('cost not reported');
    if (s.attempts !== null) parts.push(s.attempts + (s.attempts === 1 ? ' attempt' : ' attempts'));
    if (s.http_errors && s.http_errors.length) parts.push('HTTP errors ' + s.http_errors.join(', '));
    if (s.row_count !== null) parts.push(f.int(s.row_count) + (s.row_count === 1 ? ' row' : ' rows'));
    return parts.join(' · ');
  }

  function timeline(host, steps, t) {
    if (!steps.length) { host.appendChild(el('p', 'aa-muted', 'This turn recorded no steps (it ended before any route ran).')); return; }
    var bySeq = {}, cursor = 0, guessed = false;
    steps.forEach(function (s) { bySeq[s.seq] = s; });
    var placed = steps.slice().sort(function (a, b) { return a.seq - b.seq; }).map(function (s) {
      var start = s.offset_ms;
      if (start === null || start === undefined) { start = cursor; guessed = true; }
      cursor = Math.max(cursor, start + (s.duration_ms || 0));
      var level = 0;
      for (var p = s.parent_seq; p !== null && p !== undefined && bySeq[p] && level < 8; p = bySeq[p].parent_seq) level++;
      return { s: s, start: start, level: level };
    });
    var span = Math.max(cursor, ms(t.started_at, t.finished_at) || 0, 1);
    host.appendChild(el('p', 'aa-muted', 'Bars are placed on the turn\'s span of ' + f.ms(span) + '.' +
      (guessed ? ' Some steps have no recorded start, so they are laid end to end.' : '')));
    var list = append(host, el('div', 'aa-timeline'));
    placed.forEach(function (p) {
      var s = p.s, failed = s.ok === false, row = append(list, el('div', 'aa-step' + (failed ? ' aa-failed' : '')));
      row.dataset.seq = s.seq;
      var label = append(row, el('div', 'aa-step-label'));
      label.style.paddingLeft = (p.level * 18) + 'px';
      label.appendChild(el('span', 'aa-kind', KINDS[s.kind] || s.kind)).style.borderColor = color.kind(s.kind);
      label.appendChild(document.createTextNode(' ' + (s.kind === 'llm' || s.kind === 'jev' ? stage(s.stage) : s.stage || '') + (s.name ? ' · ' + s.name : '')));
      var track = append(row, el('div', 'aa-track')), bar = append(track, el('div', 'aa-bar'));
      bar.style.left = (p.start / span * 100) + '%';
      bar.style.width = Math.max(0.5, (s.duration_ms || 0) / span * 100) + '%';
      bar.style.background = failed ? '#c62828' : color.kind(s.kind);
      C.hover(bar, '#' + s.seq + ' starts at +' + f.ms(p.start) + ', takes ' + f.ms(s.duration_ms));
      row.appendChild(el('div', 'aa-step-dur', f.ms(s.duration_ms)));
      var meta = append(row, el('div', 'aa-step-meta'));
      meta.style.paddingLeft = (p.level * 18) + 'px';
      meta.appendChild(el('span', failed ? 'aa-badge aa-badge-bad' : 'aa-ok', failed ? 'failed: ' + (s.error_code || 'error') : 'ok'));
      meta.appendChild(document.createTextNode(' ' + stepMeta(s)));
      Object.keys(s.texts || {}).sort(function (a, b) { return order(a) - order(b); }).forEach(function (kind) {
        var text = s.texts[kind], det = append(row, el('details', 'aa-text'));
        det.style.marginLeft = (p.level * 18) + 'px';
        det.appendChild(el('summary', null, kind + (text.cut ? ' (cut)' : '') + ' · ' + f.int((text.text || '').length) + ' characters'));
        det.addEventListener('toggle', function () { if (det.open && !det.querySelector('pre')) det.appendChild(el('pre', null, pretty(text.text || ''))); });
      });
    });
  }

  function order(kind) { var i = TEXT_ORDER.indexOf(kind); return i < 0 ? 99 : i; }

  var analytics = document.getElementById('assistant-analytics'), trace = document.getElementById('assistant-trace');
  if (analytics) analyticsPage(analytics);
  else if (trace) tracePage(trace);
})();
