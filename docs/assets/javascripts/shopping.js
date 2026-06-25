(function () {
  'use strict';

  var STATE_KEY = 'cnc-shopping-state-v1';
  var DATA_BASE = null; // resolved at init from current page URL
  var SITE_BASE = null; // DATA_BASE without trailing "data/" — used for image src
  var OVERRIDE_SHOP_ID = '__override';

  var data = { shops: [], shopsById: {}, countries: [], items: [], itemsByCode: {}, prices: {}, lastUpdatedAt: null };
  var state = loadState();

  function loadState() {
    var fallback = { version: 1, country: 'NL', selected: {}, shopOverride: {}, itemOverride: {} };
    try {
      var raw = localStorage.getItem(STATE_KEY);
      if (!raw) return fallback;
      var parsed = JSON.parse(raw);
      return Object.assign(fallback, parsed);
    } catch (e) { return fallback; }
  }

  function saveState() {
    try { localStorage.setItem(STATE_KEY, JSON.stringify(state)); } catch (e) {}
  }

  function fetchJSON(path) {
    return fetch(path, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error('Failed to load ' + path + ' (' + r.status + ')');
      return r.json();
    });
  }

  // Resolve the data/ directory relative to the shopping page so the URLs work
  // both at site root and under a subpath (e.g. GitHub Pages project site).
  function resolveDataBase() {
    var path = window.location.pathname;
    // strip trailing "shopping/" or "shopping.html"
    path = path.replace(/shopping\/?$/, '').replace(/shopping\.html$/, '');
    if (!path.endsWith('/')) path += '/';
    return path + 'data/';
  }

  function init() {
    var root = document.getElementById('shopping-app');
    if (!root) return;
    DATA_BASE = resolveDataBase();
    SITE_BASE = DATA_BASE.replace(/data\/$/, '');
    Promise.all([
      fetchJSON(DATA_BASE + 'shops.json'),
      fetchJSON(DATA_BASE + 'items.json'),
      fetchJSON(DATA_BASE + 'prices.json')
    ]).then(function (results) {
      ingest(results[0], results[1], results[2]);
      render();
    }).catch(function (err) {
      root.innerHTML = '<p class="shopping-error">Could not load shopping data: ' +
        escapeHtml(err.message) + '</p>';
    });
  }

  function ingest(shopsFile, itemsFile, pricesFile) {
    data.shops = shopsFile.shops || [];
    data.countries = shopsFile.countries || [];
    data.shopsById = {};
    data.shops.forEach(function (s) { data.shopsById[s.id] = s; });

    data.items = itemsFile.items || [];
    data.categories = itemsFile.categories || [];
    data.itemsByCode = {};
    data.items.forEach(function (i) { data.itemsByCode[i.code] = i; });

    data.prices = {};
    (pricesFile.entries || []).forEach(function (entry) {
      if (!data.prices[entry.item_code]) data.prices[entry.item_code] = [];
      data.prices[entry.item_code].push(entry);
    });
    data.lastUpdatedAt = pricesFile.last_updated_at || null;
  }

  // -- Pricing helpers ---------------------------------------------------

  function latestObservation(entry) {
    if (!entry.observations || entry.observations.length === 0) return null;
    // Find observation with the most recent ts.
    var newest = entry.observations[0];
    for (var i = 1; i < entry.observations.length; i++) {
      if (new Date(entry.observations[i].ts) > new Date(newest.ts)) newest = entry.observations[i];
    }
    return newest;
  }

  function shopsInScope() {
    if (state.country === 'ALL') return data.shops.slice();
    return data.shops.filter(function (s) { return s.country === state.country; });
  }

  function entriesForItem(itemCode) {
    var scope = shopsInScope();
    var scopeIds = {};
    scope.forEach(function (s) { scopeIds[s.id] = true; });
    return (data.prices[itemCode] || []).filter(function (e) { return scopeIds[e.shop]; });
  }

  function bestShopForItem(itemCode) {
    var rows = entriesForItem(itemCode).map(function (entry) {
      var obs = latestObservation(entry);
      return { shopId: entry.shop, obs: obs };
    }).filter(function (r) {
      return r.obs && r.obs.in_stock && typeof r.obs.price === 'number';
    });
    if (rows.length === 0) return null;
    rows.sort(function (a, b) { return a.obs.price - b.obs.price; });
    return rows[0].shopId;
  }

  function chosenShopForItem(itemCode) {
    if (state.itemOverride[itemCode]) return OVERRIDE_SHOP_ID;
    if (state.shopOverride[itemCode]) return state.shopOverride[itemCode];
    return bestShopForItem(itemCode);
  }

  function unitPriceFor(itemCode, shopId) {
    if (shopId === OVERRIDE_SHOP_ID) {
      var ov = state.itemOverride[itemCode];
      return ov && typeof ov.price === 'number' ? ov.price : null;
    }
    var entry = (data.prices[itemCode] || []).find(function (e) { return e.shop === shopId; });
    if (!entry) return null;
    var obs = latestObservation(entry);
    return obs && typeof obs.price === 'number' ? obs.price : null;
  }

  // -- Totals ------------------------------------------------------------

  function buildOrder() {
    var perShop = {};
    var unassigned = [];

    Object.keys(state.selected).forEach(function (code) {
      if (!state.selected[code]) return;
      var item = data.itemsByCode[code];
      if (!item) return;
      var shopId = chosenShopForItem(code);
      if (!shopId) { unassigned.push(item); return; }

      if (!perShop[shopId]) perShop[shopId] = { shopId: shopId, lines: [], subtotal: 0, missingPrice: false };
      var qty = item.qty || 1;
      var unit = unitPriceFor(code, shopId);
      var line = { item: item, unitPrice: unit, qty: qty, lineTotal: (unit != null ? unit * qty : null) };
      perShop[shopId].lines.push(line);
      if (unit == null) perShop[shopId].missingPrice = true;
      else perShop[shopId].subtotal += line.lineTotal;
    });

    var groups = Object.keys(perShop).map(function (id) {
      var g = perShop[id];
      g.shipping = computeShipping(id, g.subtotal);
      g.total = g.subtotal + g.shipping.cost;
      return g;
    });

    var grandTotal = groups.reduce(function (sum, g) { return sum + g.total; }, 0);

    return { groups: groups, unassigned: unassigned, grandTotal: grandTotal };
  }

  function computeShipping(shopId, subtotal) {
    if (shopId === OVERRIDE_SHOP_ID) {
      // Custom overrides ship independently; cost unknown unless user supplied it.
      return { cost: 0, label: 'Set by buyer', free: false };
    }
    var shop = data.shopsById[shopId];
    if (!shop || !shop.shipping) return { cost: 0, label: '—', free: false };
    var s = shop.shipping;
    if (typeof s.free_above === 'number' && s.free_above > 0 && subtotal >= s.free_above) {
      return { cost: 0, label: 'Free (over ' + formatMoney(s.free_above, shop.currency) + ')', free: true };
    }
    var cost = typeof s.standard_cost === 'number' ? s.standard_cost : 0;
    var label = cost === 0 ? 'Free' : formatMoney(cost, shop.currency);
    if (typeof s.free_above === 'number' && s.free_above > 0) {
      var diff = s.free_above - subtotal;
      if (diff > 0) label += ' (€' + diff.toFixed(2) + ' to free)';
    }
    return { cost: cost, label: label, free: cost === 0 };
  }

  // -- Render ------------------------------------------------------------

  function render() {
    var root = document.getElementById('shopping-app');
    root.removeAttribute('data-empty');
    root.innerHTML = '';
    root.appendChild(renderHeader());
    root.appendChild(renderItemSections());
    root.appendChild(renderOrderSummary());
  }

  function renderHeader() {
    var header = el('div', 'shopping-header');

    var left = el('div', 'shopping-header__controls');
    var label = el('label', 'shopping-label', 'Ship to');
    label.htmlFor = 'shopping-country';
    var sel = el('select', 'shopping-select');
    sel.id = 'shopping-country';
    data.countries.forEach(function (c) {
      var opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.label;
      if (c.id === state.country) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.addEventListener('change', function () {
      state.country = sel.value;
      saveState();
      render();
    });
    left.appendChild(label);
    left.appendChild(sel);
    header.appendChild(left);

    var right = el('div', 'shopping-header__meta');
    if (data.lastUpdatedAt) {
      var freshness = el('span', 'shopping-meta', 'Prices captured ' + formatDate(data.lastUpdatedAt));
      right.appendChild(freshness);
    }
    var selectedCount = countSelected();
    var counter = el('span', 'shopping-meta', selectedCount + ' selected');
    right.appendChild(counter);

    var clearBtn = el('button', 'shopping-link', 'Clear selection');
    clearBtn.type = 'button';
    clearBtn.addEventListener('click', function () {
      state.selected = {};
      state.shopOverride = {};
      state.itemOverride = {};
      saveState();
      render();
    });
    right.appendChild(clearBtn);

    header.appendChild(right);
    return header;
  }

  function renderItemSections() {
    var wrap = el('div', 'shopping-items');
    data.categories.forEach(function (cat) {
      var itemsInCat = data.items.filter(function (i) { return i.category === cat.id; });
      if (itemsInCat.length === 0) return;
      var section = el('section', 'shopping-category');
      var headerRow = el('div', 'shopping-category__head');
      headerRow.appendChild(el('h2', 'shopping-category__title', cat.label));
      var allBtn = el('button', 'shopping-link', selectAllLabel(itemsInCat));
      allBtn.type = 'button';
      allBtn.addEventListener('click', function () {
        var allOn = itemsInCat.every(function (i) { return state.selected[i.code]; });
        itemsInCat.forEach(function (i) { state.selected[i.code] = !allOn; });
        saveState();
        render();
      });
      headerRow.appendChild(allBtn);
      section.appendChild(headerRow);

      itemsInCat.forEach(function (item) { section.appendChild(renderItemRow(item)); });
      wrap.appendChild(section);
    });
    return wrap;
  }

  function selectAllLabel(itemsInCat) {
    var allOn = itemsInCat.length > 0 && itemsInCat.every(function (i) { return state.selected[i.code]; });
    return allOn ? 'Deselect all' : 'Select all';
  }

  function renderItemRow(item) {
    var row = el('div', 'shopping-item');
    if (state.selected[item.code]) row.classList.add('is-selected');

    var head = el('label', 'shopping-item__head');
    head.htmlFor = 'sel-' + item.code;
    var cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.id = 'sel-' + item.code;
    cb.className = 'shopping-item__checkbox';
    cb.checked = !!state.selected[item.code];
    cb.addEventListener('change', function () {
      state.selected[item.code] = cb.checked;
      saveState();
      render();
    });
    head.appendChild(cb);

    head.appendChild(renderItemThumb(item));

    var titleWrap = el('div', 'shopping-item__title');
    titleWrap.appendChild(el('span', 'shopping-item__code', item.code));
    titleWrap.appendChild(el('span', 'shopping-item__name', item.name));
    var qtyText = 'Qty ' + (item.qty != null ? item.qty : '?') + (item.qty_note ? ' (' + item.qty_note + ')' : '');
    titleWrap.appendChild(el('span', 'shopping-item__qty', qtyText));
    head.appendChild(titleWrap);

    row.appendChild(head);

    if (state.selected[item.code]) {
      row.appendChild(renderShopOptions(item));
      row.appendChild(renderItemOverride(item));
    }
    return row;
  }

  function renderItemThumb(item) {
    var wrap = el('span', 'shopping-item__thumb');
    if (item.image) {
      var img = document.createElement('img');
      img.src = SITE_BASE + item.image;
      img.alt = item.name;
      img.loading = 'lazy';
      img.decoding = 'async';
      img.addEventListener('error', function () {
        wrap.classList.add('shopping-item__thumb--missing');
        wrap.textContent = item.code;
      });
      wrap.appendChild(img);
    } else {
      wrap.classList.add('shopping-item__thumb--missing');
      wrap.textContent = item.code;
    }
    return wrap;
  }

  function renderShopOptions(item) {
    var entries = entriesForItem(item.code);
    var wrap = el('div', 'shopping-shops');

    var best = bestShopForItem(item.code);
    var chosen = chosenShopForItem(item.code);

    if (entries.length === 0 && !state.itemOverride[item.code]) {
      wrap.appendChild(el('p', 'shopping-shops__empty',
        'No shops listed yet for ' + item.code + '. Use “Add your own” below.'));
      return wrap;
    }

    entries.forEach(function (entry) {
      var shop = data.shopsById[entry.shop];
      if (!shop) return;
      var obs = latestObservation(entry);
      wrap.appendChild(renderShopRow(item, shop, entry, obs, chosen === entry.shop, best === entry.shop));
    });

    if (state.itemOverride[item.code]) {
      wrap.appendChild(renderOverrideRow(item, chosen === OVERRIDE_SHOP_ID));
    }

    return wrap;
  }

  function observationAgeDays(obs) {
    if (!obs || !obs.ts) return null;
    var t = Date.parse(obs.ts);
    if (isNaN(t)) return null;
    return Math.floor((Date.now() - t) / 86400000);
  }

  function renderShopRow(item, shop, entry, obs, isChosen, isBest) {
    var row = el('label', 'shopping-shop');
    row.htmlFor = 'shop-' + item.code + '-' + shop.id;
    if (isChosen) row.classList.add('is-chosen');
    if (isBest) row.classList.add('is-best');
    var ageDays = observationAgeDays(obs);
    if (ageDays != null && ageDays > 30) row.classList.add('is-stale');

    var radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'shop-pick-' + item.code;
    radio.id = 'shop-' + item.code + '-' + shop.id;
    radio.className = 'shopping-shop__radio';
    radio.checked = isChosen;
    radio.addEventListener('change', function () {
      state.shopOverride[item.code] = shop.id;
      // Picking a real shop deactivates a custom override for this item,
      // but we keep its data around so the user can re-enable it.
      saveState();
      render();
    });
    row.appendChild(radio);

    var name = el('span', 'shopping-shop__name');
    var nameInner = el('a', 'shopping-shop__name-link', shop.name);
    nameInner.href = entry.url || shop.home_url;
    nameInner.target = '_blank';
    nameInner.rel = 'noopener noreferrer';
    name.appendChild(nameInner);
    if (isBest) name.appendChild(el('span', 'shopping-badge', 'Cheapest'));
    row.appendChild(name);

    var priceText = obs && typeof obs.price === 'number'
      ? formatMoney(obs.price, obs.currency || shop.currency)
      : 'Quote';
    var priceEl = el('span', 'shopping-shop__price', priceText);
    if (ageDays != null) {
      priceEl.title = 'Captured ' + ageDays + ' day' + (ageDays === 1 ? '' : 's') + ' ago';
    }
    row.appendChild(priceEl);

    var stockDot = el('span', 'shopping-dot');
    var inStock = obs && obs.in_stock;
    stockDot.classList.add(inStock ? 'shopping-dot--in' : 'shopping-dot--out');
    var stockWrap = el('span', 'shopping-shop__stock');
    stockWrap.appendChild(stockDot);
    var etaDays = obs && typeof obs.eta_days === 'number' ? obs.eta_days : shop.shipping && shop.shipping.default_eta_days;
    var stockLabel = inStock
      ? (etaDays != null ? etaDays + (etaDays === 1 ? ' day' : ' days') : 'In stock')
      : 'Out of stock';
    stockWrap.appendChild(document.createTextNode(stockLabel));
    row.appendChild(stockWrap);

    if (obs && obs.note) {
      var note = el('span', 'shopping-shop__note', obs.note);
      row.appendChild(note);
    }

    return row;
  }

  function renderOverrideRow(item, isChosen) {
    var ov = state.itemOverride[item.code];
    var row = el('label', 'shopping-shop shopping-shop--override');
    row.htmlFor = 'shop-' + item.code + '-override';
    if (isChosen) row.classList.add('is-chosen');

    var radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'shop-pick-' + item.code;
    radio.id = 'shop-' + item.code + '-override';
    radio.className = 'shopping-shop__radio';
    radio.checked = isChosen;
    radio.addEventListener('change', function () {
      delete state.shopOverride[item.code]; // override wins via the itemOverride map
      // Ensure itemOverride remains; nothing else to do but re-render.
      saveState();
      render();
    });
    row.appendChild(radio);

    var name = el('span', 'shopping-shop__name');
    var nameLink = el('a', 'shopping-shop__name-link', ov.shop_label || 'Custom shop');
    nameLink.href = ov.url || '#';
    nameLink.target = '_blank';
    nameLink.rel = 'noopener noreferrer';
    name.appendChild(nameLink);
    name.appendChild(el('span', 'shopping-badge shopping-badge--override', 'Your override'));
    row.appendChild(name);

    var priceText = typeof ov.price === 'number' ? formatMoney(ov.price, ov.currency || 'EUR') : '—';
    row.appendChild(el('span', 'shopping-shop__price', priceText));

    var stockWrap = el('span', 'shopping-shop__stock');
    var dot = el('span', 'shopping-dot shopping-dot--in');
    stockWrap.appendChild(dot);
    stockWrap.appendChild(document.createTextNode(
      ov.eta_days != null ? ov.eta_days + (ov.eta_days === 1 ? ' day' : ' days') : 'Custom ETA'));
    row.appendChild(stockWrap);

    return row;
  }

  function renderItemOverride(item) {
    var wrap = el('details', 'shopping-override');
    var summary = el('summary', 'shopping-override__summary',
      state.itemOverride[item.code] ? 'Edit override' : 'Add your own (EAN / product link)');
    wrap.appendChild(summary);

    var ov = state.itemOverride[item.code] || {};
    var form = el('div', 'shopping-override__form');

    var fields = [
      { key: 'shop_label', label: 'Shop name / label', type: 'text', placeholder: 'e.g. Local hardware store' },
      { key: 'url',        label: 'Product link',     type: 'url',  placeholder: 'https://…' },
      { key: 'ean',        label: 'EAN (optional)',   type: 'text', placeholder: 'e.g. 8718469556175' },
      { key: 'price',      label: 'Price (EUR)',      type: 'number', step: '0.01', placeholder: '0.00' },
      { key: 'eta_days',   label: 'ETA (days)',       type: 'number', step: '1',    placeholder: 'e.g. 3' }
    ];

    var inputs = {};
    fields.forEach(function (f) {
      var row = el('div', 'shopping-override__field');
      var lbl = el('label', null, f.label);
      var inp = document.createElement('input');
      inp.type = f.type;
      if (f.step) inp.step = f.step;
      if (f.placeholder) inp.placeholder = f.placeholder;
      if (ov[f.key] != null) inp.value = ov[f.key];
      lbl.htmlFor = 'ov-' + item.code + '-' + f.key;
      inp.id = 'ov-' + item.code + '-' + f.key;
      inputs[f.key] = inp;
      row.appendChild(lbl);
      row.appendChild(inp);
      form.appendChild(row);
    });

    var actions = el('div', 'shopping-override__actions');
    var saveBtn = el('button', 'shopping-btn shopping-btn--primary', 'Save override');
    saveBtn.type = 'button';
    saveBtn.addEventListener('click', function () {
      var url = inputs.url.value.trim();
      var ean = inputs.ean.value.trim();
      if (!url && !ean) {
        alert('Provide at least a product link or EAN.');
        return;
      }
      var price = parseFloat(inputs.price.value);
      var eta = parseInt(inputs.eta_days.value, 10);
      state.itemOverride[item.code] = {
        shop_label: inputs.shop_label.value.trim() || 'Custom shop',
        url: url,
        ean: ean || null,
        price: isFinite(price) ? price : null,
        currency: 'EUR',
        eta_days: isFinite(eta) ? eta : null,
        in_stock: true
      };
      // Make the override the active pick for this item.
      delete state.shopOverride[item.code];
      saveState();
      render();
    });
    actions.appendChild(saveBtn);

    if (state.itemOverride[item.code]) {
      var clear = el('button', 'shopping-btn', 'Remove override');
      clear.type = 'button';
      clear.addEventListener('click', function () {
        delete state.itemOverride[item.code];
        saveState();
        render();
      });
      actions.appendChild(clear);
    }
    form.appendChild(actions);
    wrap.appendChild(form);

    if (state.itemOverride[item.code]) wrap.open = true;
    return wrap;
  }

  function renderOrderSummary() {
    var order = buildOrder();
    var box = el('aside', 'shopping-summary');
    box.appendChild(el('h2', 'shopping-summary__title', 'Combined order'));

    if (countSelected() === 0) {
      box.appendChild(el('p', 'shopping-summary__empty', 'Select components above to build your order.'));
      return box;
    }

    if (order.unassigned.length > 0) {
      var warn = el('div', 'shopping-summary__warn');
      warn.appendChild(el('strong', null, 'Not yet sourced: '));
      warn.appendChild(document.createTextNode(
        order.unassigned.map(function (i) { return i.code; }).join(', ') +
        '. Add a shop or your own override.'));
      box.appendChild(warn);
    }

    var list = el('div', 'shopping-summary__groups');
    order.groups.forEach(function (g) { list.appendChild(renderGroup(g)); });
    box.appendChild(list);

    var totalRow = el('div', 'shopping-summary__total');
    totalRow.appendChild(el('span', null, 'Grand total'));
    totalRow.appendChild(el('span', 'shopping-money', formatMoney(order.grandTotal, 'EUR')));
    box.appendChild(totalRow);

    return box;
  }

  function renderGroup(g) {
    var shop = data.shopsById[g.shopId];
    var displayName = shop ? shop.name : (g.shopId === OVERRIDE_SHOP_ID ? 'Your overrides' : g.shopId);
    var card = el('div', 'shopping-summary__group');

    var head = el('div', 'shopping-summary__group-head');
    head.appendChild(el('span', 'shopping-summary__group-name', displayName));
    head.appendChild(el('span', 'shopping-money', formatMoney(g.total, 'EUR')));
    card.appendChild(head);

    var meta = el('div', 'shopping-summary__group-meta');
    meta.appendChild(el('span', null, g.lines.length + ' item' + (g.lines.length === 1 ? '' : 's')));
    meta.appendChild(el('span', null, 'Subtotal ' + formatMoney(g.subtotal, 'EUR')));
    meta.appendChild(el('span', null, 'Shipping ' + g.shipping.label));
    card.appendChild(meta);

    if (g.missingPrice) {
      card.appendChild(el('div', 'shopping-summary__group-warn',
        'Some lines have no price; total may be incomplete.'));
    }
    return card;
  }

  // -- Utilities ---------------------------------------------------------

  function countSelected() {
    return Object.keys(state.selected).filter(function (k) { return state.selected[k]; }).length;
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  var moneyFmts = {};
  function formatMoney(value, currency) {
    var cur = currency || 'EUR';
    if (!moneyFmts[cur]) {
      try {
        moneyFmts[cur] = new Intl.NumberFormat('nl-NL', { style: 'currency', currency: cur });
      } catch (e) {
        moneyFmts[cur] = { format: function (v) { return cur + ' ' + v.toFixed(2); } };
      }
    }
    return moneyFmts[cur].format(value || 0);
  }

  function formatDate(iso) {
    try {
      var d = new Date(iso);
      return d.toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch (e) { return iso; }
  }

  // -- Boot --------------------------------------------------------------

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  if (window.document$ && typeof window.document$.subscribe === 'function') {
    window.document$.subscribe(init);
  }
})();
