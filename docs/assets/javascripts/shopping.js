(function () {
  'use strict';

  var STATE_KEY = 'cnc-shopping-state-v4';
  var LEGACY_STATE_KEYS = ['cnc-shopping-state-v3'];
  var DEFAULT_CONFIG_ID = 'default';
  var CUSTOM_CONFIG_ID  = 'custom';
  var DATA_BASE = null; // resolved at init from current page URL
  var SITE_BASE = null; // DATA_BASE without trailing "data/" — used for image src
  var OVERRIDE_SHOP_ID = '__override';
  var USER_SHOP_PREFIX = '__user_';

  var data = {
    shops: [], shopsById: {}, countries: [],
    items: [], itemsByCode: {},
    // alternatives keyed by parent (canonical) code → array of alternative item objects.
    // Each alternative carries its own unique `code` used as the key in prices.json.
    alternativesByParent: {},
    parentOfAlt: {},        // alternative code → parent code
    altByCode: {},          // alternative code → alternative object (with .parent set)
    configurations: [],     // built-in configurations from items.json
    prices: {},
    lastUpdatedAt: null
  };
  var state = loadState();

  var THUMB_MIN_REM = 2;
  var THUMB_MAX_REM = 24;
  var THUMB_DEFAULT_REM = 3;

  // SL-9.e: per-observation fetching technique. Human-readable labels for the UI.
  var TECHNIQUE_LABELS = {
    jsonld: 'JSON-LD',
    opengraph: 'Open Graph',
    'affiliate-api': 'Affiliate API',
    manual: 'Manual'
  };

  function loadState() {
    var fallback = {
      version: 4,
      country: 'NL',
      selected: {},
      shopOverride: {},
      itemOverride: {},
      defaultsApplied: false,
      thumbRem: THUMB_DEFAULT_REM,
      activeConfig: DEFAULT_CONFIG_ID,
      customUses: {},
      savedConfigurations: [],
      userAlternatives: {}
    };
    try {
      var raw = localStorage.getItem(STATE_KEY);
      if (raw) return Object.assign({}, fallback, JSON.parse(raw));
      // One-shot migration from the previous key on first load of v4 —
      // keeps the user's selections, thumb size, and saved configs intact.
      for (var i = 0; i < LEGACY_STATE_KEYS.length; i++) {
        var legacy = localStorage.getItem(LEGACY_STATE_KEYS[i]);
        if (!legacy) continue;
        var prev = JSON.parse(legacy);
        var merged = Object.assign({}, fallback, prev, { version: 4 });
        merged.userAlternatives = merged.userAlternatives || {};
        return merged;
      }
      return fallback;
    } catch (e) { return fallback; }
  }

  // SL-8.b: every non-3D-printed item starts selected; 3D-printed parts start
  // deselected. Runs once per user (gated by state.defaultsApplied) so the
  // user's later deselections aren't reset on every load.
  function applyDefaultSelection() {
    if (state.defaultsApplied) return;
    data.items.forEach(function (item) {
      if (item.category !== 'printed') state.selected[item.code] = true;
    });
    state.defaultsApplied = true;
    saveState();
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
      syncUserAlternativesIntoData();
      applyDefaultSelection();
      snapActiveConfigFromCustom();
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
    data.configurations = itemsFile.configurations || [];
    data.itemsByCode = {};
    data.alternativesByParent = {};
    data.parentOfAlt = {};
    data.altByCode = {};
    data.items.forEach(function (i) {
      data.itemsByCode[i.code] = i;
      var alts = i.alternatives || [];
      if (alts.length === 0) return;
      data.alternativesByParent[i.code] = alts.map(function (a) {
        var enriched = Object.assign({
          // Inherit display defaults from the parent when the alternative omits them.
          category: i.category,
          qty: i.qty,
          image: a.image != null ? a.image : i.image,
          parent: i.code
        }, a);
        enriched.parent = i.code;
        data.parentOfAlt[enriched.code] = i.code;
        data.altByCode[enriched.code] = enriched;
        return enriched;
      });
    });

    data.prices = {};
    (pricesFile.entries || []).forEach(function (entry) {
      if (!data.prices[entry.item_code]) data.prices[entry.item_code] = [];
      data.prices[entry.item_code].push(entry);
    });
    data.lastUpdatedAt = pricesFile.last_updated_at || null;
  }

  // -- User-added alternatives ------------------------------------------

  // Merge state.userAlternatives into the data indices so they participate in
  // pricing, picking, and effective-code resolution just like authored ones.
  // Idempotent — clears previously-synthesized user entries before re-merging.
  function syncUserAlternativesIntoData() {
    Object.keys(data.altByCode).forEach(function (code) {
      if (!data.altByCode[code].userAdded) return;
      var parent = data.altByCode[code].parent;
      delete data.altByCode[code];
      delete data.parentOfAlt[code];
      if (data.alternativesByParent[parent]) {
        data.alternativesByParent[parent] = data.alternativesByParent[parent].filter(function (a) {
          return !a.userAdded;
        });
        if (data.alternativesByParent[parent].length === 0) delete data.alternativesByParent[parent];
      }
      delete data.prices[code];
    });
    data.shops = data.shops.filter(function (s) { return s.id.indexOf(USER_SHOP_PREFIX) !== 0; });
    Object.keys(data.shopsById).forEach(function (id) {
      if (id.indexOf(USER_SHOP_PREFIX) === 0) delete data.shopsById[id];
    });

    var nowIso = new Date().toISOString();
    Object.keys(state.userAlternatives || {}).forEach(function (parentCode) {
      var parent = data.itemsByCode[parentCode];
      if (!parent) return;
      (state.userAlternatives[parentCode] || []).forEach(function (ua) {
        var enriched = {
          code: ua.code,
          name: ua.name,
          ean: ua.ean || null,
          category: parent.category,
          qty: parent.qty,
          image: ua.image != null ? ua.image : parent.image,
          parent: parentCode,
          userAdded: true
        };
        if (!data.alternativesByParent[parentCode]) data.alternativesByParent[parentCode] = [];
        data.alternativesByParent[parentCode].push(enriched);
        data.altByCode[ua.code] = enriched;
        data.parentOfAlt[ua.code] = parentCode;

        if (!ua.shop) return;
        var shopId = USER_SHOP_PREFIX + ua.code;
        var synthShop = {
          id: shopId,
          name: ua.shop.shop_label || 'Custom shop',
          country: state.country,
          currency: ua.shop.currency || 'EUR',
          home_url: ua.shop.url || '#',
          shipping: { standard_cost: 0, default_eta_days: ua.shop.eta_days != null ? ua.shop.eta_days : null }
        };
        data.shops.push(synthShop);
        data.shopsById[shopId] = synthShop;

        data.prices[ua.code] = [{
          item_code: ua.code,
          shop: shopId,
          url: ua.shop.url || null,
          observations: [{
            ts: nowIso,
            price: typeof ua.shop.price === 'number' ? ua.shop.price : null,
            currency: ua.shop.currency || 'EUR',
            eta_days: ua.shop.eta_days != null ? ua.shop.eta_days : null,
            in_stock: true,
            technique: 'manual'
          }]
        }];
      });
    });
  }

  function generateUserAltCode(parentCode) {
    var bytes = new Uint8Array(2);
    var src = window.crypto || window.msCrypto;
    if (src && src.getRandomValues) {
      src.getRandomValues(bytes);
    } else {
      bytes[0] = Math.floor(Math.random() * 256);
      bytes[1] = Math.floor(Math.random() * 256);
    }
    var hex = ('0' + bytes[0].toString(16)).slice(-2) + ('0' + bytes[1].toString(16)).slice(-2);
    var code = parentCode + '-user-' + hex;
    // Defensive: regenerate on the astronomically improbable collision.
    if (data.itemsByCode[code] || data.altByCode[code]) return generateUserAltCode(parentCode);
    return code;
  }

  function addUserAlternative(parentCode, vals) {
    var name = (vals.name || '').trim();
    if (!name) { alert('Give the alternative product a name.'); return; }
    if (!state.userAlternatives[parentCode]) state.userAlternatives[parentCode] = [];
    var code = generateUserAltCode(parentCode);
    state.userAlternatives[parentCode].push({
      code: code,
      name: name,
      ean: vals.ean || null,
      shop: {
        shop_label: vals.shop_label || 'Custom shop',
        url: vals.url || null,
        price: typeof vals.price === 'number' ? vals.price : null,
        currency: vals.currency || 'EUR',
        eta_days: typeof vals.eta_days === 'number' ? vals.eta_days : null
      }
    });
    syncUserAlternativesIntoData();
    setEffectiveAlternative(parentCode, code);
  }

  function removeUserAlternative(parentCode, altCode) {
    var arr = (state.userAlternatives[parentCode] || []).filter(function (ua) {
      return ua.code !== altCode;
    });
    if (arr.length === 0) delete state.userAlternatives[parentCode];
    else state.userAlternatives[parentCode] = arr;

    if (state.customUses && state.customUses[parentCode] === altCode) {
      delete state.customUses[parentCode];
    }
    // Drop a saved configuration's reference too, since the alt no longer exists.
    (state.savedConfigurations || []).forEach(function (cfg) {
      if (cfg.uses && cfg.uses[parentCode] === altCode) delete cfg.uses[parentCode];
    });
    syncUserAlternativesIntoData();
    snapActiveConfigFromCustom();
    saveState();
    render();
  }

  // -- Configurations & alternatives -------------------------------------

  function copyUses(o) {
    var c = {};
    Object.keys(o || {}).forEach(function (k) { c[k] = o[k]; });
    return c;
  }

  function deepEqualUses(a, b) {
    var ak = Object.keys(a || {});
    var bk = Object.keys(b || {});
    if (ak.length !== bk.length) return false;
    for (var i = 0; i < ak.length; i++) {
      var k = ak[i];
      if (a[k] !== b[k]) return false;
    }
    return true;
  }

  function matchConfigByUses(uses) {
    var all = allKnownConfigs();
    for (var i = 0; i < all.length; i++) {
      if (deepEqualUses(all[i].uses || {}, uses || {})) return all[i];
    }
    return null;
  }

  // Whenever state.customUses changes, decide whether activeConfig should snap
  // to a known config id (default, built-in, or saved) instead of "custom".
  // An empty customUses always snaps to default; an exact match to any saved
  // bundle reuses that bundle's id so the dropdown reflects reality.
  function snapActiveConfigFromCustom() {
    var match = matchConfigByUses(state.customUses || {});
    state.activeConfig = match ? match.id : CUSTOM_CONFIG_ID;
  }

  function builtInConfigs() {
    var defaults = [{ id: DEFAULT_CONFIG_ID, label: 'Default (stock build)', uses: {} }];
    return defaults.concat(data.configurations || []);
  }

  function allKnownConfigs() {
    return builtInConfigs().concat(state.savedConfigurations || []);
  }

  function configById(id) {
    var all = allKnownConfigs();
    for (var i = 0; i < all.length; i++) if (all[i].id === id) return all[i];
    return null;
  }

  // Map { parentCode → effectiveCode } describing the currently active substitutions.
  function activeUses() {
    if (state.activeConfig === CUSTOM_CONFIG_ID) return state.customUses || {};
    var cfg = configById(state.activeConfig);
    return cfg && cfg.uses ? cfg.uses : {};
  }

  // Given a canonical (parent) code, return the code that should currently be
  // displayed and priced in that slot — either the parent or one of its alternatives.
  function effectiveCodeFor(parentCode) {
    var uses = activeUses();
    var sub = uses[parentCode];
    if (sub && (data.altByCode[sub] || data.itemsByCode[sub])) return sub;
    return parentCode;
  }

  // Resolve a code (parent or alternative) to its renderable item object.
  function itemByAnyCode(code) {
    return data.itemsByCode[code] || data.altByCode[code] || null;
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
    // User-added shops always pass scope: they exist only because the user
    // explicitly added them, so country filtering would just hide them.
    return (data.prices[itemCode] || []).filter(function (e) {
      return scopeIds[e.shop] || e.shop.indexOf(USER_SHOP_PREFIX) === 0;
    });
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

    Object.keys(state.selected).forEach(function (parentCode) {
      if (!state.selected[parentCode]) return;
      var parent = data.itemsByCode[parentCode];
      if (!parent) return;
      var effCode = effectiveCodeFor(parentCode);
      var eff = itemByAnyCode(effCode) || parent;
      var shopId = chosenShopForItem(effCode);
      if (!shopId) { unassigned.push(eff); return; }

      if (!perShop[shopId]) perShop[shopId] = { shopId: shopId, lines: [], subtotal: 0, missingPrice: false };
      var qty = eff.qty || 1;
      var unit = unitPriceFor(effCode, shopId);
      var line = { item: eff, unitPrice: unit, qty: qty, lineTotal: (unit != null ? unit * qty : null) };
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
    applyThumbSize(root);
    root.appendChild(renderHeader());
    root.appendChild(renderItemSections());
    root.appendChild(renderOrderSummary());
  }

  function applyThumbSize(root) {
    var rem = clampThumbRem(state.thumbRem);
    root.style.setProperty('--shopping-thumb-size', rem + 'rem');
  }

  function clampThumbRem(v) {
    var n = Number(v);
    if (!isFinite(n)) return THUMB_DEFAULT_REM;
    if (n < THUMB_MIN_REM) return THUMB_MIN_REM;
    if (n > THUMB_MAX_REM) return THUMB_MAX_REM;
    return n;
  }

  function renderHeader() {
    var header = el('div', 'shopping-header');
    header.appendChild(renderConfigRow());

    var bottomRow = el('div', 'shopping-header__row');
    header.appendChild(bottomRow);

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

    left.appendChild(renderThumbSizeControl());

    bottomRow.appendChild(left);

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

    bottomRow.appendChild(right);
    return header;
  }

  function renderConfigRow() {
    var row = el('div', 'shopping-config-row');
    var label = el('label', 'shopping-label', 'Configuration');
    label.htmlFor = 'shopping-config';
    var sel = el('select', 'shopping-select shopping-config__select');
    sel.id = 'shopping-config';

    var configs = allKnownConfigs();
    configs.forEach(function (cfg) {
      var opt = document.createElement('option');
      opt.value = cfg.id;
      opt.textContent = cfg.label;
      if (cfg.id === state.activeConfig) opt.selected = true;
      sel.appendChild(opt);
    });
    // The "Custom" entry only appears when the user has made an ad-hoc swap that
    // doesn't match any saved configuration. It can't be selected via the dropdown
    // because picking an alternative is what creates it.
    if (state.activeConfig === CUSTOM_CONFIG_ID) {
      var opt = document.createElement('option');
      opt.value = CUSTOM_CONFIG_ID;
      opt.textContent = 'Custom (unsaved)';
      opt.selected = true;
      sel.appendChild(opt);
    }
    sel.addEventListener('change', function () {
      state.activeConfig = sel.value;
      saveState();
      render();
    });

    row.appendChild(label);
    row.appendChild(sel);

    // When in Custom state, expose a button to discard the swaps and return to Default,
    // plus a button to persist the current swaps as a named saved configuration.
    if (state.activeConfig === CUSTOM_CONFIG_ID) {
      var resetBtn = el('button', 'shopping-link', 'Reset to default');
      resetBtn.type = 'button';
      resetBtn.addEventListener('click', function () {
        state.customUses = {};
        state.activeConfig = DEFAULT_CONFIG_ID;
        saveState();
        render();
      });
      row.appendChild(resetBtn);

      var saveCfgBtn = el('button', 'shopping-link', 'Save as configuration…');
      saveCfgBtn.type = 'button';
      saveCfgBtn.addEventListener('click', saveCurrentAsConfiguration);
      row.appendChild(saveCfgBtn);
    }

    return row;
  }

  function saveCurrentAsConfiguration() {
    var label = (window.prompt('Name this configuration:') || '').trim();
    if (!label) return;
    var baseId = label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    if (!baseId) baseId = 'config';
    var id = baseId, n = 2;
    while (configById(id)) { id = baseId + '-' + (n++); }
    if (!state.savedConfigurations) state.savedConfigurations = [];
    state.savedConfigurations.push({ id: id, label: label, uses: copyUses(state.customUses) });
    state.activeConfig = id;
    saveState();
    render();
  }

  function renderThumbSizeControl() {
    var wrap = el('div', 'shopping-thumb-control');
    var label = el('label', 'shopping-label', 'Thumbnails');
    label.htmlFor = 'shopping-thumb-size';
    var slider = document.createElement('input');
    slider.type = 'range';
    slider.id = 'shopping-thumb-size';
    slider.className = 'shopping-thumb-slider';
    slider.min = String(THUMB_MIN_REM);
    slider.max = String(THUMB_MAX_REM);
    slider.step = '0.25';
    slider.value = String(clampThumbRem(state.thumbRem));
    slider.setAttribute('aria-label', 'Thumbnail size');
    // Live-update the CSS custom property during the drag for a smooth scrub,
    // and only persist on commit (`change`) so we don't thrash localStorage.
    slider.addEventListener('input', function () {
      var root = document.getElementById('shopping-app');
      if (root) root.style.setProperty('--shopping-thumb-size', slider.value + 'rem');
    });
    slider.addEventListener('change', function () {
      state.thumbRem = clampThumbRem(slider.value);
      saveState();
    });
    wrap.appendChild(label);
    wrap.appendChild(slider);
    return wrap;
  }

  function renderItemSections() {
    var wrap = el('div', 'shopping-items');
    // SL-8.b: 3D-printed parts render at the bottom; all other categories keep their authored order.
    var orderedCategories = data.categories.slice().sort(function (a, b) {
      var aPrinted = a.id === 'printed' ? 1 : 0;
      var bPrinted = b.id === 'printed' ? 1 : 0;
      return aPrinted - bPrinted;
    });
    orderedCategories.forEach(function (cat) {
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
      section.appendChild(renderCategoryFooter(itemsInCat));
      wrap.appendChild(section);
    });
    return wrap;
  }

  function renderCategoryFooter(itemsInCat) {
    var summary = buildSectionSummary(itemsInCat);
    var foot = el('div', 'shopping-category__footer');
    foot.appendChild(el('span', null,
      summary.selectedCount + ' of ' + summary.totalCount + ' selected'));
    if (summary.unsourced > 0) {
      foot.appendChild(el('span', 'shopping-category__footer-warn',
        summary.unsourced + ' unsourced'));
    }
    var totalLabel = summary.selectedCount === 0 ? '—' : formatMoney(summary.subtotal, 'EUR');
    var totalEl = el('span', 'shopping-category__footer-total',
      'Subtotal ' + totalLabel);
    foot.appendChild(totalEl);
    return foot;
  }

  function buildSectionSummary(itemsInCat) {
    var selectedCount = 0;
    var subtotal = 0;
    var unsourced = 0;
    itemsInCat.forEach(function (parent) {
      if (!state.selected[parent.code]) return;
      selectedCount++;
      var effCode = effectiveCodeFor(parent.code);
      var eff = itemByAnyCode(effCode) || parent;
      var shopId = chosenShopForItem(effCode);
      var unit = shopId ? unitPriceFor(effCode, shopId) : null;
      if (unit == null) { unsourced++; return; }
      subtotal += unit * (eff.qty || 1);
    });
    return {
      selectedCount: selectedCount,
      totalCount: itemsInCat.length,
      subtotal: subtotal,
      unsourced: unsourced
    };
  }

  function selectAllLabel(itemsInCat) {
    var allOn = itemsInCat.length > 0 && itemsInCat.every(function (i) { return state.selected[i.code]; });
    return allOn ? 'Deselect all' : 'Select all';
  }

  function renderItemRow(parentItem) {
    var effectiveCode = effectiveCodeFor(parentItem.code);
    var effective = itemByAnyCode(effectiveCode) || parentItem;
    var isAlt = effectiveCode !== parentItem.code;

    var row = el('div', 'shopping-item');
    if (state.selected[parentItem.code]) row.classList.add('is-selected');
    if (isAlt) row.classList.add('is-alternative');

    var head = el('label', 'shopping-item__head');
    head.htmlFor = 'sel-' + parentItem.code;
    var cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.id = 'sel-' + parentItem.code;
    cb.className = 'shopping-item__checkbox';
    cb.checked = !!state.selected[parentItem.code];
    cb.addEventListener('change', function () {
      state.selected[parentItem.code] = cb.checked;
      saveState();
      render();
    });
    head.appendChild(cb);

    head.appendChild(renderItemThumb(effective));

    var titleWrap = el('div', 'shopping-item__title');
    titleWrap.appendChild(el('span', 'shopping-item__code', parentItem.code));
    titleWrap.appendChild(el('span', 'shopping-item__name', effective.name));
    if (isAlt) {
      titleWrap.appendChild(el('span', 'shopping-item__alt-badge', 'Alternative'));
    }
    var qtyText = 'Qty ' + (effective.qty != null ? effective.qty : '?') +
      (effective.qty_note ? ' (' + effective.qty_note + ')' : '');
    titleWrap.appendChild(el('span', 'shopping-item__qty', qtyText));
    head.appendChild(titleWrap);

    row.appendChild(head);

    if (state.selected[parentItem.code]) {
      row.appendChild(renderAlternativesPicker(parentItem, effectiveCode));
      row.appendChild(renderShopOptions(effective));
      row.appendChild(renderItemOverride(effective));
    }
    return row;
  }

  function renderAlternativesPicker(parentItem, effectiveCode) {
    var alts = data.alternativesByParent[parentItem.code] || [];

    var wrap = el('details', 'shopping-alts');
    // Auto-open when an alternative is currently active OR when there are user-added
    // alts (so the "added by you" entries are visible without an extra click).
    var hasUserAlts = alts.some(function (a) { return a.userAdded; });
    wrap.open = effectiveCode !== parentItem.code || hasUserAlts;

    var summaryLabel = alts.length === 0 ? 'Alternatives' : 'Alternatives (' + alts.length + ')';
    var summary = el('summary', 'shopping-alts__summary', summaryLabel);
    wrap.appendChild(summary);

    var list = el('div', 'shopping-alts__list');
    var groupName = 'alt-pick-' + parentItem.code;

    // The first row is the canonical (parent) item as the "default" choice.
    list.appendChild(renderAltChoice({
      name: groupName,
      id: 'alt-' + parentItem.code + '-default',
      label: parentItem.name + ' (default)',
      isChecked: effectiveCode === parentItem.code,
      onPick: function () { setEffectiveAlternative(parentItem.code, null); }
    }));

    alts.forEach(function (a) {
      list.appendChild(renderAltChoice({
        name: groupName,
        id: 'alt-' + parentItem.code + '-' + a.code,
        label: a.name,
        sublabel: a.userAdded ? 'added by you' : null,
        isChecked: effectiveCode === a.code,
        onPick: function () { setEffectiveAlternative(parentItem.code, a.code); },
        onRemove: a.userAdded ? function () { removeUserAlternative(parentItem.code, a.code); } : null
      }));
    });
    wrap.appendChild(list);

    // SL-8.d follow-up: inline form to add a brand-new alternative product.
    // Reuses renderInlineProductForm with an extra "name" field on the front.
    var add = el('details', 'shopping-alts__add');
    var addSummary = el('summary', 'shopping-alts__add-summary', '+ Add alternative product');
    add.appendChild(addSummary);
    add.appendChild(renderInlineProductForm({
      idPrefix: 'add-alt-' + parentItem.code,
      includeName: true,
      submitLabel: 'Add alternative',
      onSave: function (vals) { addUserAlternative(parentItem.code, vals); }
    }));
    wrap.appendChild(add);

    return wrap;
  }

  function renderAltChoice(opts) {
    var row = el('label', 'shopping-alts__choice');
    row.htmlFor = opts.id;
    if (opts.isChecked) row.classList.add('is-chosen');
    if (typeof opts.onRemove === 'function') row.classList.add('shopping-alts__choice--removable');

    var radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = opts.name;
    radio.id = opts.id;
    radio.checked = opts.isChecked;
    radio.addEventListener('change', function () { opts.onPick(); });
    row.appendChild(radio);

    var labelWrap = el('span', 'shopping-alts__choice-label');
    labelWrap.appendChild(document.createTextNode(opts.label));
    if (opts.sublabel) {
      labelWrap.appendChild(el('span', 'shopping-alts__choice-sub', opts.sublabel));
    }
    row.appendChild(labelWrap);

    if (typeof opts.onRemove === 'function') {
      var rm = el('button', 'shopping-alts__choice-remove', 'Remove');
      rm.type = 'button';
      rm.setAttribute('aria-label', 'Remove ' + opts.label);
      // Stop the click from also toggling the radio via the wrapping <label>.
      rm.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (window.confirm('Remove "' + opts.label + '" from this item’s alternatives?')) opts.onRemove();
      });
      row.appendChild(rm);
    }
    return row;
  }

  // Picking an alternative (or the default) updates state.customUses and snaps
  // activeConfig: if the resulting customUses exactly matches a known config
  // (default/built-in/saved), use that id; otherwise mark it "custom".
  function setEffectiveAlternative(parentCode, altCode) {
    // Seed customUses from the currently active config so swaps compose on top
    // of a saved bundle instead of throwing the bundle's other swaps away.
    if (state.activeConfig !== CUSTOM_CONFIG_ID) {
      state.customUses = copyUses(activeUses());
    } else if (!state.customUses) {
      state.customUses = {};
    }
    if (altCode == null) delete state.customUses[parentCode];
    else state.customUses[parentCode] = altCode;
    snapActiveConfigFromCustom();
    saveState();
    render();
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
    var nameTop = el('span', 'shopping-shop__name-top');
    var nameInner = el('a', 'shopping-shop__name-link', shop.name);
    nameInner.href = entry.url || shop.home_url;
    nameInner.target = '_blank';
    nameInner.rel = 'noopener noreferrer';
    nameTop.appendChild(nameInner);
    if (isBest) nameTop.appendChild(el('span', 'shopping-badge', 'Cheapest'));
    name.appendChild(nameTop);
    // SL-8.f: provenance label ("JSON-LD · 5d ago") + sparkline pop-over.
    var meta = renderShopProvenance(entry, obs);
    if (meta) name.appendChild(meta);
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

  // SL-8.f: provenance label + sparkline pop-over.
  // The technique badge (and "5d ago") tells the user how the latest price was
  // captured; the sparkline hovers/clicks into a popover with the full history.
  function renderShopProvenance(entry, obs) {
    if (!obs) return null;
    var meta = el('span', 'shopping-shop__meta');
    var technique = obs.technique || 'manual';
    meta.appendChild(el('span',
      'shopping-shop__technique shopping-shop__technique--' + technique,
      TECHNIQUE_LABELS[technique] || technique));
    var ageDays = observationAgeDays(obs);
    if (ageDays != null) {
      meta.appendChild(el('span', 'shopping-shop__captured',
        '· ' + (ageDays === 0 ? 'today' : (ageDays + 'd ago'))));
    }
    var pricePoints = (entry.observations || []).filter(function (o) {
      return typeof o.price === 'number';
    });
    if (pricePoints.length >= 2) meta.appendChild(renderHistoryControl(pricePoints));
    return meta;
  }

  function renderHistoryControl(pricePoints) {
    var sorted = pricePoints.slice().sort(function (a, b) {
      return new Date(a.ts) - new Date(b.ts);
    });
    var wrap = el('span', 'shopping-shop__history-wrap');
    var btn = el('button', 'shopping-shop__history');
    btn.type = 'button';
    btn.setAttribute('aria-label', 'Show price history');
    btn.appendChild(buildSparklineSvg(sorted));
    // Click toggles a sticky-open mode so keyboard users can review the popover;
    // hover/focus-within also opens it via CSS. Stop the click from selecting the radio.
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      wrap.classList.toggle('is-open');
    });
    wrap.appendChild(btn);
    wrap.appendChild(buildHistoryPopover(sorted));
    return wrap;
  }

  function buildSparklineSvg(sorted) {
    var w = 56, h = 14;
    var prices = sorted.map(function (o) { return o.price; });
    var min = Math.min.apply(null, prices);
    var max = Math.max.apply(null, prices);
    var range = (max - min) || 1;
    var step = prices.length === 1 ? 0 : w / (prices.length - 1);
    var d = prices.map(function (p, i) {
      var x = i * step;
      var y = h - ((p - min) / range) * (h - 2) - 1;
      return (i === 0 ? 'M' : 'L') + x.toFixed(1) + ',' + y.toFixed(1);
    }).join(' ');
    var svgNS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('class', 'shopping-sparkline');
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    svg.setAttribute('width', String(w));
    svg.setAttribute('height', String(h));
    svg.setAttribute('aria-hidden', 'true');
    var path = document.createElementNS(svgNS, 'path');
    path.setAttribute('d', d);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', 'currentColor');
    path.setAttribute('stroke-width', '1.4');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    svg.appendChild(path);
    // Mark the most-recent point so the eye lands on the current price.
    var lastX = (prices.length - 1) * step;
    var lastY = h - ((prices[prices.length - 1] - min) / range) * (h - 2) - 1;
    var dot = document.createElementNS(svgNS, 'circle');
    dot.setAttribute('cx', lastX.toFixed(1));
    dot.setAttribute('cy', lastY.toFixed(1));
    dot.setAttribute('r', '1.4');
    dot.setAttribute('fill', 'currentColor');
    svg.appendChild(dot);
    return svg;
  }

  function buildHistoryPopover(sorted) {
    var pop = el('span', 'shopping-shop__history-pop');
    pop.appendChild(el('span', 'shopping-shop__history-title', 'Price history'));
    var list = el('ul', 'shopping-shop__history-list');
    sorted.slice().reverse().forEach(function (o) {
      var li = el('li', 'shopping-shop__history-item');
      li.appendChild(el('span', 'shopping-shop__history-date', formatDate(o.ts)));
      li.appendChild(el('span', 'shopping-shop__history-price',
        o.price != null ? formatMoney(o.price, o.currency || 'EUR') : '—'));
      li.appendChild(el('span', 'shopping-shop__history-technique',
        TECHNIQUE_LABELS[o.technique || 'manual']));
      list.appendChild(li);
    });
    pop.appendChild(list);
    return pop;
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

  // SL-8.e: single-line form reused for the per-item override and SL-8.d's
  // "add alternative product" flow. The latter prepends a product-name field
  // via opts.includeName; otherwise the form collects the same five shop fields.
  function renderInlineProductForm(opts) {
    var values = opts.values || {};
    var fields = [];
    if (opts.includeName) {
      fields.push({ key: 'name', label: 'Product name', type: 'text', placeholder: 'Product name', size: 'name' });
    }
    fields.push(
      { key: 'shop_label', label: 'Shop name / label', type: 'text',   placeholder: 'Shop',          size: 'shop'  },
      { key: 'url',        label: 'Product link',      type: 'url',    placeholder: 'https://…',     size: 'url'   },
      { key: 'ean',        label: 'EAN (optional)',    type: 'text',   placeholder: 'EAN',           size: 'ean'   },
      { key: 'price',      label: 'Price (EUR)',       type: 'number', step: '0.01', placeholder: '€',   size: 'price' },
      { key: 'eta_days',   label: 'ETA (days)',        type: 'number', step: '1',    placeholder: 'days',size: 'eta'   }
    );

    var form = el('div', 'shopping-inline-form');
    var inputs = {};
    fields.forEach(function (f) {
      var fieldId = opts.idPrefix + '-' + f.key;
      var field = el('label', 'shopping-inline-form__field shopping-inline-form__field--' + f.size);
      field.htmlFor = fieldId;
      field.appendChild(el('span', 'shopping-inline-form__label', f.label));
      var inp = document.createElement('input');
      inp.type = f.type;
      inp.id = fieldId;
      inp.className = 'shopping-inline-form__input';
      if (f.step) inp.step = f.step;
      if (f.placeholder) inp.placeholder = f.placeholder;
      if (values[f.key] != null && values[f.key] !== '') inp.value = values[f.key];
      inp.setAttribute('aria-label', f.label);
      inputs[f.key] = inp;
      field.appendChild(inp);
      form.appendChild(field);
    });

    var actions = el('div', 'shopping-inline-form__actions');
    var saveBtn = el('button', 'shopping-btn shopping-btn--primary', opts.submitLabel || 'Save');
    saveBtn.type = 'button';
    saveBtn.addEventListener('click', function () {
      var url = inputs.url.value.trim();
      var ean = inputs.ean.value.trim();
      var name = opts.includeName ? (inputs.name.value || '').trim() : null;
      if (opts.includeName && !name) {
        alert('Give the alternative product a name.');
        return;
      }
      if (!url && !ean) {
        alert('Provide at least a product link or EAN.');
        return;
      }
      var price = parseFloat(inputs.price.value);
      var eta = parseInt(inputs.eta_days.value, 10);
      var payload = {
        shop_label: inputs.shop_label.value.trim() || null,
        url: url,
        ean: ean || null,
        price: isFinite(price) ? price : null,
        currency: 'EUR',
        eta_days: isFinite(eta) ? eta : null
      };
      if (opts.includeName) payload.name = name;
      opts.onSave(payload);
    });
    actions.appendChild(saveBtn);

    if (typeof opts.onRemove === 'function') {
      var clear = el('button', 'shopping-btn', opts.removeLabel || 'Remove');
      clear.type = 'button';
      clear.addEventListener('click', function () { opts.onRemove(); });
      actions.appendChild(clear);
    }
    form.appendChild(actions);
    return form;
  }

  function renderItemOverride(item) {
    var wrap = el('details', 'shopping-override');
    var hasOverride = !!state.itemOverride[item.code];
    var summary = el('summary', 'shopping-override__summary',
      hasOverride ? 'Edit override' : 'Add your own (EAN / product link)');
    wrap.appendChild(summary);

    wrap.appendChild(renderInlineProductForm({
      idPrefix: 'ov-' + item.code,
      values: state.itemOverride[item.code] || {},
      submitLabel: 'Save override',
      removeLabel: 'Remove override',
      onSave: function (vals) {
        state.itemOverride[item.code] = {
          shop_label: vals.shop_label || 'Custom shop',
          url: vals.url,
          ean: vals.ean,
          price: vals.price,
          currency: vals.currency,
          eta_days: vals.eta_days,
          in_stock: true
        };
        delete state.shopOverride[item.code];
        saveState();
        render();
      },
      onRemove: hasOverride ? function () {
        delete state.itemOverride[item.code];
        saveState();
        render();
      } : null
    }));

    if (hasOverride) wrap.open = true;
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
