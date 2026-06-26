(function () {
  'use strict';

  var STATE_KEY = 'cnc-shopping-state-v5';
  var LEGACY_STATE_KEYS = ['cnc-shopping-state-v4', 'cnc-shopping-state-v3'];
  var DEFAULT_CONFIG_ID = 'default';
  var CUSTOM_CONFIG_ID  = 'custom';
  var DATA_BASE = null; // resolved at init from current page URL
  var SITE_BASE = null; // DATA_BASE without trailing "data/" — used for image src
  var OVERRIDE_SHOP_ID = '__override';
  var USER_SHOP_PREFIX = '__user_';
  // SL-10.O: prefix for user-added shops attached to an existing item.
  // Kept distinct from USER_SHOP_PREFIX so sync routines don't tread on each other.
  var ADDED_SHOP_PREFIX = '__addedshop_';

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

  // SL-10.a: ordered TOC groups. Categories not enumerated here are appended at
  // the end in their authored order, so adding a new category to items.json
  // still renders without code changes.
  var CATEGORY_GROUPS = [
    { id: 'electronics', label: 'Electronics',                  categories: ['electronics'] },
    { id: 'other',       label: 'Other',                        categories: ['other'] },
    { id: 'rods',        label: 'Threaded rods',                categories: ['rods'] },
    { id: 'fasteners',   label: 'Screws, bolts, washers, nuts', categories: ['screws', 'nuts', 'washers'] },
    { id: 'printed',     label: '3D-printed parts',             categories: ['printed'] }
  ];

  // SL-9.e: per-observation fetching technique. Human-readable labels for the UI.
  var TECHNIQUE_LABELS = {
    jsonld: 'JSON-LD',
    opengraph: 'Open Graph',
    'affiliate-api': 'Affiliate API',
    manual: 'Manual'
  };

  // SL-9.d: local helper for the per-bot "Refresh now" toolbar. The page polls
  // GET /api/health once; if the helper is up, a third toolbar row appears with
  // one button per refreshable shop. If not, a quiet "↻ Refresh prices…" chip
  // in the meta row reveals the start command on click.
  var REFRESH_HELPER_URL = 'http://127.0.0.1:8765';
  var REFRESH_HEALTH_TIMEOUT_MS = 1500;
  var REFRESH_COMMAND = 'python3 tools/refresh_server.py';
  var refreshHelper = {
    state: 'unknown',   // 'unknown' | 'online' | 'offline'
    bots: [],
    cooldownUntil: {},  // bot_id → epoch ms when local cooldown expires
    inFlight: {}        // bot_id → true while POST is in flight
  };
  var refreshTickHandle = null;

  function loadState() {
    var fallback = {
      version: 5,
      country: 'NL',
      selected: {},
      shopOverride: {},
      itemOverride: {},
      defaultsApplied: false,
      thumbRem: THUMB_DEFAULT_REM,
      activeConfig: DEFAULT_CONFIG_ID,
      customUses: {},
      savedConfigurations: [],
      userAlternatives: {},
      // SL-8.i: per-observation validations live in app state since the static
      // site has no backend to mutate prices.json. Keyed "<item>::<shop>::<ts>".
      validations: {},
      // SL-8.h: transient prefill for the override form, populated by clicking
      // "Complete this" on a partial observation. Keyed by effective item code.
      itemOverridePrefill: {},
      // SL-10.a: TOC fold state — group id → true if collapsed. Default unfolded.
      collapsedCategories: {},
      // SL-10.N + SL-10.O: per-item add-form state, parent code → 'alt' | 'shop'
      // (or absent when no form is open). At most one form is open per row.
      openAdd: {},
      // Deprecated, kept for one-shot migration to state.openAdd on load.
      expandedItems: {},
      // SL-10.K: per-user manual price observations keyed by "<item>::<shop>".
      // Each value is { price, currency, eta_days, ts } and gets injected as
      // a manual observation into data.prices so the existing pricing,
      // picker, and history machinery picks it up.
      userPriceObservations: {},
      // SL-10.O: user-added shops for an existing item — { itemCode: [shop, ...] }.
      // Each shop object includes a synthesized id (ADDED_SHOP_PREFIX + …) and
      // becomes a real shop entry in data.shops + data.prices via sync.
      userShops: {},
      // SL-10.P: per-user EAN per (item, shop) — keyed "<item>::<shop>".
      // Overlaid on entry.ean after every render cycle (seed is restored first).
      userEans: {}
    };
    try {
      var raw = localStorage.getItem(STATE_KEY);
      if (raw) return Object.assign({}, fallback, JSON.parse(raw));
      // One-shot migration from the previous key on first load — keeps the user's
      // selections, thumb size, saved configs, and user-added alternatives intact.
      for (var i = 0; i < LEGACY_STATE_KEYS.length; i++) {
        var legacy = localStorage.getItem(LEGACY_STATE_KEYS[i]);
        if (!legacy) continue;
        var prev = JSON.parse(legacy);
        var merged = Object.assign({}, fallback, prev, { version: 5 });
        merged.userAlternatives = merged.userAlternatives || {};
        merged.validations = merged.validations || {};
        merged.itemOverridePrefill = merged.itemOverridePrefill || {};
        merged.collapsedCategories = merged.collapsedCategories || {};
        merged.openAdd = merged.openAdd || {};
        merged.expandedItems = merged.expandedItems || {};
        merged.userPriceObservations = merged.userPriceObservations || {};
        merged.userShops = merged.userShops || {};
        merged.userEans = merged.userEans || {};
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
      fetchJSON(DATA_BASE + 'prices.json'),
      pollRefreshHelper()  // never rejects; populates refreshHelper.state
    ]).then(function (results) {
      // Close any open EAN popover when the user clicks outside it.
      // Popover-internal clicks stopPropagation so this only fires for outside clicks.
      document.addEventListener('click', function () {
        document.querySelectorAll('.shopping-item__ean-wrap.is-open').forEach(function (w) {
          w.classList.remove('is-open');
        });
      });
      ingest(results[0], results[1], results[2]);
      syncUserAlternativesIntoData();
      syncUserShopsIntoData();
      // SL-10.L: legacy state.itemOverride data is preserved as manual
      // user-price observations against the first scoped shop, then cleared.
      migrateItemOverridesToUserPrices();
      // Migrate state.expandedItems (boolean) → state.openAdd[code]='alt'.
      migrateExpandedItemsToOpenAdd();
      syncUserPriceObservationsIntoData();
      applyUserEansToData();
      applyDefaultSelection();
      snapActiveConfigFromCustom();
      ensureTocBodyObserver();
      render();
      ensureRefreshTick();
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
      // SL-10.P: snapshot the seeded EAN so we can restore-then-overlay
      // state.userEans on each render cycle without losing the original.
      entry._seedEan = entry.ean != null ? entry.ean : null;
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

  // SL-10.K: weave manual user-set prices into data.prices so the existing
  // pricing/picker/history machinery sees them as real observations. Marked
  // with a non-schema `_userAdded` flag so re-running the sync can clear
  // prior synthetic observations cleanly.
  function syncUserPriceObservationsIntoData() {
    Object.keys(data.prices).forEach(function (itemCode) {
      data.prices[itemCode].forEach(function (entry) {
        entry.observations = (entry.observations || []).filter(function (o) {
          return !o._userAdded;
        });
      });
    });
    var ups = state.userPriceObservations || {};
    Object.keys(ups).forEach(function (key) {
      var sep = key.indexOf('::');
      if (sep < 0) return;
      var itemCode = key.slice(0, sep);
      var shopId = key.slice(sep + 2);
      var ob = ups[key];
      if (!ob) return;
      if (!data.prices[itemCode]) data.prices[itemCode] = [];
      var entry = data.prices[itemCode].find(function (e) { return e.shop === shopId; });
      if (!entry) {
        // User typed a price into a shop row that didn't have an entry yet
        // (could happen for a synthetic case). Create the entry on the fly.
        entry = { item_code: itemCode, shop: shopId, url: null, observations: [] };
        data.prices[itemCode].push(entry);
      }
      entry.observations.push({
        ts: ob.ts || new Date().toISOString(),
        price: typeof ob.price === 'number' ? ob.price : null,
        currency: ob.currency || 'EUR',
        in_stock: ob.in_stock != null ? ob.in_stock : true,
        eta_days: typeof ob.eta_days === 'number' ? ob.eta_days : null,
        technique: 'manual',
        _userAdded: true
      });
    });
  }

  // SL-10.K: write or clear a manual user-price observation for an (item, shop)
  // pair. Pass price=null to remove the user's manual price for that pair.
  function recordUserPrice(itemCode, shopId, price, opts) {
    if (!state.userPriceObservations) state.userPriceObservations = {};
    var key = itemCode + '::' + shopId;
    if (price == null) {
      delete state.userPriceObservations[key];
    } else {
      var prev = state.userPriceObservations[key] || {};
      state.userPriceObservations[key] = {
        price: price,
        currency: (opts && opts.currency) || prev.currency || 'EUR',
        eta_days: (opts && typeof opts.eta_days === 'number') ? opts.eta_days
                  : (typeof prev.eta_days === 'number' ? prev.eta_days : null),
        in_stock: true,
        ts: new Date().toISOString()
      };
    }
    syncUserPriceObservationsIntoData();
    saveState();
    render();
  }

  function migrateExpandedItemsToOpenAdd() {
    if (!state.expandedItems || Object.keys(state.expandedItems).length === 0) return;
    if (!state.openAdd) state.openAdd = {};
    var moved = false;
    Object.keys(state.expandedItems).forEach(function (code) {
      if (state.expandedItems[code] && !state.openAdd[code]) {
        state.openAdd[code] = 'alt';
        moved = true;
      }
    });
    state.expandedItems = {};
    if (moved) saveState();
  }

  // SL-10.O: weave user-added shops into data.shops + data.prices so they
  // show up in the shop dropdown alongside seeded shops. Each user shop
  // becomes a synthetic shop entry (ADDED_SHOP_PREFIX + …) and a price
  // entry with one manual observation.
  function syncUserShopsIntoData() {
    data.shops = data.shops.filter(function (s) {
      return s.id.indexOf(ADDED_SHOP_PREFIX) !== 0;
    });
    Object.keys(data.shopsById).forEach(function (id) {
      if (id.indexOf(ADDED_SHOP_PREFIX) === 0) delete data.shopsById[id];
    });
    Object.keys(data.prices).forEach(function (itemCode) {
      data.prices[itemCode] = data.prices[itemCode].filter(function (e) {
        return e.shop.indexOf(ADDED_SHOP_PREFIX) !== 0;
      });
    });
    var nowIso = new Date().toISOString();
    Object.keys(state.userShops || {}).forEach(function (itemCode) {
      (state.userShops[itemCode] || []).forEach(function (us) {
        var synth = {
          id: us.id,
          name: us.shop_label || 'Custom shop',
          country: state.country,
          currency: us.currency || 'EUR',
          home_url: us.url || '#',
          shipping: {
            standard_cost: typeof us.shipping_cost === 'number' ? us.shipping_cost : 0,
            default_eta_days: typeof us.eta_days === 'number' ? us.eta_days : null
          },
          userAdded: true
        };
        data.shops.push(synth);
        data.shopsById[us.id] = synth;
        if (!data.prices[itemCode]) data.prices[itemCode] = [];
        data.prices[itemCode].push({
          item_code: itemCode,
          shop: us.id,
          url: us.url || null,
          observations: [{
            ts: us.ts || nowIso,
            price: typeof us.price === 'number' ? us.price : null,
            currency: us.currency || 'EUR',
            in_stock: us.in_stock != null ? us.in_stock : true,
            eta_days: typeof us.eta_days === 'number' ? us.eta_days : null,
            technique: 'manual'
          }]
        });
      });
    });
  }

  // SL-10.P: restore each entry to its seeded EAN, then overlay user EANs from
  // state.userEans on top. Called after every state.userEans mutation and on
  // initial load (after the user-shop sync so __addedshop_ entries exist).
  function applyUserEansToData() {
    Object.keys(data.prices).forEach(function (itemCode) {
      data.prices[itemCode].forEach(function (entry) {
        if (Object.prototype.hasOwnProperty.call(entry, '_seedEan')) {
          entry.ean = entry._seedEan;
        }
      });
    });
    var ues = state.userEans || {};
    Object.keys(ues).forEach(function (key) {
      var sep = key.indexOf('::');
      if (sep < 0) return;
      var itemCode = key.slice(0, sep);
      var shopId = key.slice(sep + 2);
      var entry = (data.prices[itemCode] || []).find(function (e) { return e.shop === shopId; });
      if (entry) entry.ean = ues[key];
    });
  }

  function setUserEan(itemCode, shopId, ean) {
    if (!state.userEans) state.userEans = {};
    var key = itemCode + '::' + shopId;
    if (!ean) delete state.userEans[key];
    else state.userEans[key] = ean;
    applyUserEansToData();
    saveState();
    render();
  }

  function generateAddedShopId(itemCode) {
    var bytes = new Uint8Array(2);
    var src = window.crypto || window.msCrypto;
    if (src && src.getRandomValues) src.getRandomValues(bytes);
    else { bytes[0] = Math.floor(Math.random() * 256); bytes[1] = Math.floor(Math.random() * 256); }
    var hex = ('0' + bytes[0].toString(16)).slice(-2) + ('0' + bytes[1].toString(16)).slice(-2);
    var id = ADDED_SHOP_PREFIX + itemCode + '_' + hex;
    if (data.shopsById[id]) return generateAddedShopId(itemCode);  // collision retry
    return id;
  }

  function addUserShop(itemCode, vals) {
    if (!state.userShops) state.userShops = {};
    if (!state.userShops[itemCode]) state.userShops[itemCode] = [];
    var id = generateAddedShopId(itemCode);
    state.userShops[itemCode].push({
      id: id,
      shop_label: vals.shop_label,
      url: vals.url,
      price: vals.price,
      currency: vals.currency || 'EUR',
      eta_days: typeof vals.eta_days === 'number' ? vals.eta_days : null,
      shipping_cost: typeof vals.shipping_cost === 'number' ? vals.shipping_cost : null,
      in_stock: true,
      ts: new Date().toISOString()
    });
    syncUserShopsIntoData();
    // Select the newly-added shop so the user immediately sees their price on the row.
    state.shopOverride[itemCode] = id;
    if (state.openAdd) delete state.openAdd[itemCode];
    saveState();
    render();
  }

  function migrateItemOverridesToUserPrices() {
    if (!state.itemOverride) { state.itemOverride = {}; return; }
    var codes = Object.keys(state.itemOverride);
    if (codes.length === 0) return;
    var moved = false;
    codes.forEach(function (code) {
      var ov = state.itemOverride[code];
      if (!ov || typeof ov.price !== 'number') return;
      var entries = entriesForItem(code);
      if (entries.length === 0) return;
      var shopId = entries[0].shop;
      if (!state.userPriceObservations) state.userPriceObservations = {};
      var key = code + '::' + shopId;
      if (state.userPriceObservations[key]) return;
      state.userPriceObservations[key] = {
        price: ov.price,
        currency: ov.currency || 'EUR',
        eta_days: typeof ov.eta_days === 'number' ? ov.eta_days : null,
        in_stock: true,
        ts: new Date().toISOString()
      };
      moved = true;
    });
    if (moved) {
      state.itemOverride = {};
      saveState();
    }
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

  // SL-10.L: no more separate "Your override" entity. Whichever shop the
  // user picks in the dropdown wins; otherwise we default to the cheapest
  // in-stock pick. Per-shop manual prices live in state.userPriceObservations.
  function chosenShopForItem(itemCode) {
    if (state.shopOverride[itemCode]) return state.shopOverride[itemCode];
    return bestShopForItem(itemCode);
  }

  function unitPriceFor(itemCode, shopId) {
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
    // SL-10.F: TOC lives in Material's TOC sidebar (bottom-left by default,
    // top-right when toc-toggle.js has switched position). Not in the page body.
    placeShoppingTocInSidebar();
  }

  // SL-10.F: shopping-page TOC injected into Material's TOC sidebar so it
  // shares the layout slot with the rest of the site's TOCs.
  var SHOPPING_TOC_SIDEBAR_CLASS = 'shopping-toc-sidebar';
  function placeShoppingTocInSidebar() {
    // Remove any prior injection (idempotent across renders).
    document.querySelectorAll('.' + SHOPPING_TOC_SIDEBAR_CLASS).forEach(function (n) { n.remove(); });
    var toc = renderToc();
    toc.classList.add(SHOPPING_TOC_SIDEBAR_CLASS);

    var inLeftMode = !document.body.classList.contains('toc-position-right');
    if (inLeftMode) {
      // toc-toggle.js renders a `.toc-clone` wrapper in the primary sidebar
      // with a "TOC → top right" toggle button and (on pages without ## headings)
      // a "No headings on this page." paragraph. We replace that paragraph with
      // our TOC, or append if it's missing.
      var clone = document.querySelector('.md-sidebar--primary .toc-clone');
      if (clone) {
        var empty = clone.querySelector('.toc-clone-empty');
        if (empty) empty.replaceWith(toc);
        else clone.appendChild(toc);
        return;
      }
      var primary = document.querySelector('.md-sidebar--primary .md-sidebar__inner');
      if (primary) primary.appendChild(toc);
    } else {
      var secondary = document.querySelector('.md-sidebar--secondary .md-sidebar__inner');
      if (secondary) secondary.appendChild(toc);
    }
  }

  // Re-place the TOC whenever toc-toggle.js flips the position class on body.
  var tocBodyObserver = null;
  function ensureTocBodyObserver() {
    if (tocBodyObserver || typeof MutationObserver === 'undefined') return;
    tocBodyObserver = new MutationObserver(function (mutations) {
      var classChanged = mutations.some(function (m) { return m.attributeName === 'class'; });
      if (!classChanged) return;
      if (!document.getElementById('shopping-app')) return;
      placeShoppingTocInSidebar();
    });
    tocBodyObserver.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  }

  // SL-10.a: resolve the ordered list of TOC groups to render. Authored
  // CATEGORY_GROUPS first, then any items.json categories not covered by a
  // group are appended as single-category groups (in items.json order).
  function activeGroups() {
    var seen = {};
    CATEGORY_GROUPS.forEach(function (g) { g.categories.forEach(function (c) { seen[c] = true; }); });
    var groups = CATEGORY_GROUPS.slice();
    (data.categories || []).forEach(function (cat) {
      if (seen[cat.id]) return;
      groups.push({ id: cat.id, label: cat.label, categories: [cat.id] });
    });
    return groups;
  }

  function itemsInGroup(group) {
    var inSet = {};
    group.categories.forEach(function (c) { inSet[c] = true; });
    return data.items.filter(function (i) { return inSet[i.category]; });
  }

  function isCategoryCollapsed(groupId) {
    return !!(state.collapsedCategories && state.collapsedCategories[groupId]);
  }

  function setCategoryCollapsed(groupId, collapsed) {
    if (!state.collapsedCategories) state.collapsedCategories = {};
    if (collapsed) state.collapsedCategories[groupId] = true;
    else delete state.collapsedCategories[groupId];
    saveState();
  }

  function toggleCategoryCollapsed(groupId) {
    setCategoryCollapsed(groupId, !isCategoryCollapsed(groupId));
    render();
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

    // SL-9.d: when the local helper isn't running, expose the start command
    // here as a small details/summary chip rather than a dead disabled row.
    var offlineChip = renderRefreshOfflineChip();
    if (offlineChip) right.appendChild(offlineChip);

    bottomRow.appendChild(right);

    // SL-9.d: third row — per-bot "Refresh now" buttons. Returns null and
    // the row is omitted entirely when the helper isn't running.
    var refreshRow = renderRefreshRow();
    if (refreshRow) header.appendChild(refreshRow);

    return header;
  }

  // SL-9.d: local helper integration ----------------------------------------

  function pollRefreshHelper() {
    var ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, REFRESH_HEALTH_TIMEOUT_MS);
    var opts = { cache: 'no-store' };
    if (ctrl) opts.signal = ctrl.signal;
    return fetch(REFRESH_HELPER_URL + '/api/health', opts).then(function (r) {
      clearTimeout(timer);
      if (!r.ok) throw new Error('helper status ' + r.status);
      return r.json();
    }).then(function (json) {
      refreshHelper.state = 'online';
      refreshHelper.bots = json.bots || [];
    }).catch(function () {
      clearTimeout(timer);
      refreshHelper.state = 'offline';
      refreshHelper.bots = [];
    });
  }

  function renderRefreshRow() {
    if (refreshHelper.state !== 'online') return null;
    var bots = refreshHelper.bots || [];
    if (bots.length === 0) return null;
    var row = el('div', 'shopping-header__row shopping-refresh');
    var label = el('span', 'shopping-label', 'Refresh now');
    row.appendChild(label);
    var btns = el('div', 'shopping-refresh__buttons');
    bots.forEach(function (bot) { btns.appendChild(renderRefreshButton(bot)); });
    row.appendChild(btns);
    return row;
  }

  function renderRefreshButton(bot) {
    var btn = el('button', 'shopping-refresh__btn');
    btn.type = 'button';
    btn.setAttribute('data-bot-id', bot.id);
    btn.setAttribute('data-cooldown-s', String(bot.cooldown_s || 30));
    btn.setAttribute('data-last-run-at', bot.last_run_at || '');
    updateRefreshButton(btn);
    btn.addEventListener('click', function () { triggerRefresh(bot.id); });
    return btn;
  }

  function updateRefreshButton(btn) {
    var botId = btn.getAttribute('data-bot-id');
    var cooldownUntil = refreshHelper.cooldownUntil[botId] || 0;
    var remaining = Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000));
    var inFlight = !!refreshHelper.inFlight[botId];

    btn.innerHTML = '';
    btn.appendChild(el('span', 'shopping-refresh__icon', inFlight ? '⏳' : '↻'));
    btn.appendChild(el('span', 'shopping-refresh__name', botId));
    var status = el('span', 'shopping-refresh__status');
    if (inFlight) {
      status.textContent = 'refreshing…';
      btn.disabled = true;
    } else if (remaining > 0) {
      status.textContent = 'wait ' + remaining + 's';
      btn.disabled = true;
    } else {
      var lastRunAt = btn.getAttribute('data-last-run-at');
      status.textContent = lastRunAt ? ('last ' + relativeAgeShort(lastRunAt)) : 'never run';
      btn.disabled = false;
    }
    btn.appendChild(status);
  }

  function relativeAgeShort(iso) {
    var then = Date.parse(iso);
    if (isNaN(then)) return 'unknown';
    var deltaSec = Math.max(0, (Date.now() - then) / 1000);
    if (deltaSec < 60)    return Math.round(deltaSec) + 's ago';
    if (deltaSec < 3600)  return Math.round(deltaSec / 60) + 'm ago';
    if (deltaSec < 86400) return Math.round(deltaSec / 3600) + 'h ago';
    return Math.round(deltaSec / 86400) + 'd ago';
  }

  function ensureRefreshTick() {
    if (refreshTickHandle) return;
    refreshTickHandle = setInterval(function () {
      var btns = document.querySelectorAll('.shopping-refresh__btn');
      if (btns.length === 0) return;
      btns.forEach(updateRefreshButton);
    }, 1000);
  }

  function triggerRefresh(botId) {
    if (refreshHelper.inFlight[botId]) return;
    refreshHelper.inFlight[botId] = true;
    document.querySelectorAll('.shopping-refresh__btn').forEach(updateRefreshButton);

    var url = REFRESH_HELPER_URL + '/api/refresh?bot=' + encodeURIComponent(botId);
    fetch(url, { method: 'POST', cache: 'no-store' }).then(function (r) {
      if (r.status === 429) {
        var ra = parseInt(r.headers.get('Retry-After') || '0', 10);
        refreshHelper.cooldownUntil[botId] = Date.now() + Math.max(1, ra) * 1000;
        return null;
      }
      if (!r.ok) {
        return r.json().catch(function () { return null; }).then(function (body) {
          flashRefreshError(botId, (body && body.detail) || ('helper error ' + r.status));
          return null;
        });
      }
      return r.json();
    }).then(function (body) {
      var cooldownS = cooldownForBot(botId);
      // On success and on 4xx error alike, hold the button for the cooldown so
      // the user doesn't hammer it.
      if (!refreshHelper.cooldownUntil[botId] || refreshHelper.cooldownUntil[botId] < Date.now()) {
        refreshHelper.cooldownUntil[botId] = Date.now() + cooldownS * 1000;
      }
      if (body && body.appended != null) {
        return pollRefreshHelper().then(reloadPrices);
      }
    }).catch(function (err) {
      flashRefreshError(botId, (err && err.message) ? err.message : 'request failed');
    }).then(function () {
      refreshHelper.inFlight[botId] = false;
      render();
    });
  }

  function cooldownForBot(botId) {
    var bots = refreshHelper.bots || [];
    for (var i = 0; i < bots.length; i++) {
      if (bots[i].id === botId) return bots[i].cooldown_s || 30;
    }
    return 30;
  }

  function reloadPrices() {
    return fetchJSON(DATA_BASE + 'prices.json').then(function (pricesFile) {
      data.prices = {};
      (pricesFile.entries || []).forEach(function (entry) {
        if (!data.prices[entry.item_code]) data.prices[entry.item_code] = [];
        data.prices[entry.item_code].push(entry);
      });
      data.lastUpdatedAt = pricesFile.last_updated_at || data.lastUpdatedAt;
    }).catch(function () {});
  }

  function flashRefreshError(botId, msg) {
    if (window.console && console.error) console.error('refresh ' + botId + ':', msg);
    var btn = document.querySelector('.shopping-refresh__btn[data-bot-id="' + botId + '"]');
    if (!btn) return;
    btn.setAttribute('data-error', msg);
    setTimeout(function () { if (btn) btn.removeAttribute('data-error'); }, 4000);
  }

  function renderRefreshOfflineChip() {
    if (refreshHelper.state !== 'offline') return null;
    // Plain button + sibling body — avoids <details>/<summary> getting picked
    // up by Material's admonition styling.
    var wrap = el('div', 'shopping-refresh-offline');
    var toggle = el('button', 'shopping-refresh-offline__toggle');
    toggle.type = 'button';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.title = 'Local refresh helper isn’t running.';
    toggle.appendChild(el('span', 'shopping-refresh-offline__icon', '↻'));
    toggle.appendChild(el('span', null, 'Refresh prices…'));
    wrap.appendChild(toggle);

    var body = el('div', 'shopping-refresh-offline__body');
    body.appendChild(el('p', 'shopping-refresh-offline__hint',
      'Start the helper alongside your local mkdocs server to refresh prices from this page:'));
    var cmdRow = el('div', 'shopping-refresh-offline__cmd-row');
    cmdRow.appendChild(el('code', 'shopping-refresh-offline__cmd', REFRESH_COMMAND));
    var copy = el('button', 'shopping-link shopping-refresh-offline__copy', 'Copy');
    copy.type = 'button';
    copy.addEventListener('click', function () {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(REFRESH_COMMAND).then(function () {
          copy.textContent = 'Copied!';
          setTimeout(function () { copy.textContent = 'Copy'; }, 1500);
        });
      }
    });
    cmdRow.appendChild(copy);
    body.appendChild(cmdRow);
    wrap.appendChild(body);

    toggle.addEventListener('click', function () {
      var open = wrap.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    return wrap;
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

  // SL-10.a: Table of contents at the top of the page. Each entry shows the
  // group label and a count, and acts as a fold/unfold toggle that mirrors
  // the same toggle on the section header. Clicking the label scrolls to it.
  function renderToc() {
    var wrap = el('nav', 'shopping-toc');
    wrap.setAttribute('aria-label', 'Categories');
    var title = el('h2', 'shopping-toc__title', 'Categories');
    wrap.appendChild(title);
    var list = el('ul', 'shopping-toc__list');

    activeGroups().forEach(function (group) {
      var items = itemsInGroup(group);
      if (items.length === 0) return;
      var collapsed = isCategoryCollapsed(group.id);
      var li = el('li', 'shopping-toc__item');

      var foldBtn = el('button', 'shopping-toc__fold');
      foldBtn.type = 'button';
      foldBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      foldBtn.setAttribute('aria-label', (collapsed ? 'Expand ' : 'Collapse ') + group.label);
      foldBtn.appendChild(el('span', 'shopping-toc__chevron', collapsed ? '▸' : '▾'));
      foldBtn.addEventListener('click', function () { toggleCategoryCollapsed(group.id); });
      li.appendChild(foldBtn);

      var jump = el('a', 'shopping-toc__link', group.label);
      jump.href = '#shopping-group-' + group.id;
      jump.addEventListener('click', function (e) {
        // If collapsed, expand on jump so the user lands on visible content.
        if (collapsed) {
          e.preventDefault();
          setCategoryCollapsed(group.id, false);
          render();
          requestAnimationFrame(function () {
            var target = document.getElementById('shopping-group-' + group.id);
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          });
        }
      });
      li.appendChild(jump);

      var count = el('span', 'shopping-toc__count', String(items.length));
      li.appendChild(count);

      list.appendChild(li);
    });
    wrap.appendChild(list);
    return wrap;
  }

  function renderItemSections() {
    var wrap = el('div', 'shopping-items');
    activeGroups().forEach(function (group) {
      var itemsInCat = itemsInGroup(group);
      if (itemsInCat.length === 0) return;
      var collapsed = isCategoryCollapsed(group.id);
      var section = el('section', 'shopping-category' + (collapsed ? ' is-collapsed' : ''));
      section.id = 'shopping-group-' + group.id;

      var headerRow = el('div', 'shopping-category__head');

      // SL-10.a: clickable title doubles as fold/unfold so the user can toggle
      // from the section header too. The title and chevron form the toggle;
      // the per-section "Select all" button stays separate.
      var titleBtn = el('button', 'shopping-category__toggle');
      titleBtn.type = 'button';
      titleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      titleBtn.setAttribute('aria-controls', 'shopping-group-body-' + group.id);
      titleBtn.appendChild(el('span', 'shopping-category__chevron', collapsed ? '▸' : '▾'));
      titleBtn.appendChild(el('h2', 'shopping-category__title', group.label));
      titleBtn.appendChild(el('span', 'shopping-category__count', '(' + itemsInCat.length + ')'));
      titleBtn.addEventListener('click', function () { toggleCategoryCollapsed(group.id); });
      headerRow.appendChild(titleBtn);

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

      if (!collapsed) {
        var body = el('div', 'shopping-category__body');
        body.id = 'shopping-group-body-' + group.id;
        itemsInCat.forEach(function (item) { body.appendChild(renderItemRow(item)); });
        body.appendChild(renderCategoryFooter(itemsInCat));
        section.appendChild(body);
      }

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

  // SL-10.E + SL-10.M: per-item row is a single line at most thumbnail-tall.
  // SL-10.N + SL-10.O: at most one of the add-alt / add-shop forms may appear
  // directly below the row, gated by state.openAdd[parentCode].
  function renderItemRow(parentItem) {
    var effectiveCode = effectiveCodeFor(parentItem.code);
    var effective = itemByAnyCode(effectiveCode) || parentItem;
    var isAlt = effectiveCode !== parentItem.code;
    var isSelected = !!state.selected[parentItem.code];
    var openKind = state.openAdd && state.openAdd[parentItem.code]; // 'alt' | 'shop' | undefined

    var row = el('div', 'shopping-item');
    if (isSelected) row.classList.add('is-selected');
    if (isAlt) row.classList.add('is-alternative');
    if (openKind === 'alt') row.classList.add('is-add-alt-open');
    if (openKind === 'shop') row.classList.add('is-add-shop-open');

    row.appendChild(renderItemHead(parentItem, effective, effectiveCode, isAlt, isSelected, openKind));

    if (openKind === 'alt') {
      var altBody = el('div', 'shopping-item__body shopping-item__body--alt');
      altBody.appendChild(renderAddAlternativeForm(parentItem));
      row.appendChild(altBody);
    } else if (openKind === 'shop') {
      var shopBody = el('div', 'shopping-item__body shopping-item__body--shop');
      shopBody.appendChild(renderAddShopForm(parentItem, effective));
      row.appendChild(shopBody);
    }
    return row;
  }

  function renderItemHead(parentItem, effective, effectiveCode, isAlt, isSelected, openKind) {
    var head = el('div', 'shopping-item__head');

    var cbLabel = el('label', 'shopping-item__check');
    cbLabel.htmlFor = 'sel-' + parentItem.code;
    cbLabel.setAttribute('aria-label', 'Include ' + parentItem.name + ' in the order');
    var cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.id = 'sel-' + parentItem.code;
    cb.className = 'shopping-item__checkbox';
    cb.checked = isSelected;
    cb.addEventListener('change', function () {
      state.selected[parentItem.code] = cb.checked;
      saveState();
      render();
    });
    cbLabel.appendChild(cb);
    head.appendChild(cbLabel);

    head.appendChild(renderItemThumb(effective));

    // SL-10.Q: the alts dropdown IS the item-name display now — no separate
    // name span, no "Alt" badge. The dropdown's selected option text shows
    // the current product's name (parent or alt).
    // SL-10.S: the code badge doubles as a click-to-copy button that copies
    // the dropdown's currently-selected product name to the clipboard.
    var titleWrap = el('div', 'shopping-item__title');
    titleWrap.appendChild(renderItemCodeButton(parentItem));
    titleWrap.appendChild(renderAltsDropdown(parentItem, effectiveCode));
    var qtyText = '×' + (effective.qty != null ? effective.qty : '?');
    titleWrap.appendChild(el('span', 'shopping-item__qty', qtyText));
    head.appendChild(titleWrap);

    head.appendChild(renderShopSummary(effective));
    // SL-10.R: a single "Visit" link whose target depends on which item AND
    // shop the user has picked. Sits beside the shop summary since it's
    // entirely shop-scoped.
    var visitEl = renderVisitLink(effective);
    if (visitEl) head.appendChild(visitEl);
    // SL-10.P: EAN affordance for the currently-selected shop, immediately
    // beside the shop summary so the user reads "this is THIS shop's EAN".
    var eanEl = renderEanControl(effective);
    if (eanEl) head.appendChild(eanEl);
    // History popover for the currently-selected shop (SL-8.f/g preservation).
    var historyEl = renderHeadHistoryControl(effective);
    if (historyEl) head.appendChild(historyEl);
    head.appendChild(renderAddAltButton(parentItem, openKind === 'alt'));
    head.appendChild(renderAddShopButton(parentItem, effective, openKind === 'shop'));
    // SL-10.G: price lives at the rightmost edge of the row, "—" when missing.
    head.appendChild(renderItemPrice(effective));

    return head;
  }

  // SL-10.N: "+ Alt" icon — toggles the add-alternative form below the row.
  function renderAddAltButton(parentItem, isOpen) {
    var btn = el('button', 'shopping-item__add shopping-item__add--alt' + (isOpen ? ' is-open' : ''));
    btn.type = 'button';
    btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    btn.setAttribute('aria-controls', 'add-alt-body-' + parentItem.code);
    var label = isOpen
      ? 'Close add-alternative form for ' + parentItem.name
      : 'Add an alternative product for ' + parentItem.name + ' (EAN / product link / price)';
    btn.setAttribute('aria-label', label);
    btn.title = label;
    btn.appendChild(el('span', 'shopping-item__add-icon', isOpen ? '×' : '+'));
    btn.appendChild(el('span', 'shopping-item__add-text', 'Alt'));
    btn.addEventListener('click', function () { toggleOpenAdd(parentItem.code, 'alt'); });
    return btn;
  }

  // SL-10.O: "+ Shop" icon — toggles the add-shop form below the row. Distinct
  // styling from "+ Alt" so the user sees which they're adding.
  function renderAddShopButton(parentItem, effective, isOpen) {
    var btn = el('button', 'shopping-item__add shopping-item__add--shop' + (isOpen ? ' is-open' : ''));
    btn.type = 'button';
    btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    btn.setAttribute('aria-controls', 'add-shop-body-' + parentItem.code);
    var label = isOpen
      ? 'Close add-shop form for ' + parentItem.name
      : 'Add a shop for ' + parentItem.name + ' (URL / shop name / price)';
    btn.setAttribute('aria-label', label);
    btn.title = label;
    btn.appendChild(el('span', 'shopping-item__add-icon', isOpen ? '×' : '+'));
    btn.appendChild(el('span', 'shopping-item__add-text', 'Shop'));
    btn.addEventListener('click', function () { toggleOpenAdd(parentItem.code, 'shop'); });
    return btn;
  }

  function toggleOpenAdd(code, kind) {
    if (!state.openAdd) state.openAdd = {};
    if (state.openAdd[code] === kind) delete state.openAdd[code];
    else state.openAdd[code] = kind;
    saveState();
    render();
    requestAnimationFrame(function () {
      var firstFieldId = kind === 'alt'
        ? 'add-alt-' + code + '-name'
        : 'add-shop-' + code + '-shop_label';
      var f = document.getElementById(firstFieldId);
      if (f) f.focus();
    });
  }

  // SL-10.R: a single "Visit" link per item row, target tied to whichever
  // item (parent or alt via the alts dropdown) and shop (via the shop
  // dropdown) the user has picked. Falls back to the shop's home_url when
  // the entry itself has no url; omitted when no URL is available anywhere.
  function renderVisitLink(effective) {
    var entries = entriesForItem(effective.code);
    if (entries.length === 0) return null;
    var chosenId = chosenShopForItem(effective.code);
    var shopId = chosenId || entries[0].shop;
    var entry = (data.prices[effective.code] || []).find(function (e) { return e.shop === shopId; });
    var shop = data.shopsById[shopId];
    var url = (entry && entry.url) || (shop && shop.home_url) || null;
    if (!url) return null;
    var shopName = (shop && shop.name) || shopId;
    var a = document.createElement('a');
    a.className = 'shopping-item__visit';
    a.href = url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.title = 'Visit ' + shopName + ' product page';
    a.setAttribute('aria-label', a.title);
    a.appendChild(el('span', 'shopping-item__visit-icon', '↗'));
    a.appendChild(el('span', 'shopping-item__visit-text', 'Visit'));
    return a;
  }

  // SL-10.P: EAN button + popover for the currently-selected shop. Edit/Save
  // writes state.userEans[item::shop]; Copy puts the EAN on the clipboard;
  // Clear removes the user EAN (revealing any seeded EAN underneath).
  function renderEanControl(effective) {
    var entries = entriesForItem(effective.code);
    if (entries.length === 0) return null;
    var chosenId = chosenShopForItem(effective.code);
    var shopId = chosenId || entries[0].shop;
    var entry = (data.prices[effective.code] || []).find(function (e) { return e.shop === shopId; });
    if (!entry) return null;
    var shop = data.shopsById[shopId];
    var shopName = (shop && shop.name) || shopId;
    var ean = entry.ean || '';

    var wrap = el('span', 'shopping-item__ean-wrap');
    var btn = el('button', 'shopping-item__ean-btn' + (ean ? ' has-ean' : ''));
    btn.type = 'button';
    btn.setAttribute('aria-haspopup', 'true');
    btn.setAttribute('aria-expanded', 'false');
    btn.title = ean
      ? 'EAN ' + ean + ' (' + shopName + ') — click to edit or copy'
      : 'Set EAN for ' + shopName;
    btn.appendChild(el('span', 'shopping-item__ean-label', 'EAN'));
    if (ean) btn.appendChild(el('span', 'shopping-item__ean-dot', '●'));

    var pop = el('div', 'shopping-item__ean-pop');
    pop.appendChild(el('span', 'shopping-item__ean-pop-title', 'EAN · ' + shopName));

    var input = document.createElement('input');
    input.type = 'text';
    input.inputMode = 'numeric';
    input.className = 'shopping-item__ean-input';
    input.placeholder = 'EAN / barcode';
    input.value = ean;
    input.setAttribute('aria-label', 'EAN for ' + shopName);
    pop.appendChild(input);

    var actions = el('div', 'shopping-item__ean-actions');
    var copyBtn = el('button', 'shopping-btn shopping-item__ean-copy', 'Copy');
    copyBtn.type = 'button';
    copyBtn.disabled = !ean;
    copyBtn.title = 'Copy EAN to clipboard';
    copyBtn.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      var val = (input.value || '').trim() || ean;
      if (!val) return;
      copyTextWithFlash(val, copyBtn);
      copyBtn.textContent = 'Copied!';
      setTimeout(function () { copyBtn.textContent = 'Copy'; }, 1500);
    });
    actions.appendChild(copyBtn);

    var saveBtn = el('button', 'shopping-btn shopping-btn--primary', 'Save');
    saveBtn.type = 'button';
    saveBtn.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      var val = (input.value || '').trim();
      setUserEan(effective.code, shopId, val || null);
    });
    actions.appendChild(saveBtn);

    if (ean) {
      var clearBtn = el('button', 'shopping-btn shopping-item__ean-clear', 'Clear');
      clearBtn.type = 'button';
      clearBtn.title = 'Remove the EAN you set for this shop';
      clearBtn.addEventListener('click', function (e) {
        e.preventDefault(); e.stopPropagation();
        setUserEan(effective.code, shopId, null);
      });
      actions.appendChild(clearBtn);
    }
    pop.appendChild(actions);

    btn.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      // Close any other open EAN popovers so only one is visible at a time.
      document.querySelectorAll('.shopping-item__ean-wrap.is-open').forEach(function (w) {
        if (w !== wrap) w.classList.remove('is-open');
      });
      var open = wrap.classList.toggle('is-open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) requestAnimationFrame(function () { input.focus(); input.select(); });
    });
    // Stop popover-internal clicks from closing it via the document-level handler.
    pop.addEventListener('click', function (e) { e.stopPropagation(); });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); saveBtn.click(); }
      else if (e.key === 'Escape') { e.preventDefault(); wrap.classList.remove('is-open'); }
    });

    wrap.appendChild(btn);
    wrap.appendChild(pop);
    return wrap;
  }

  function fallbackCopy(text) {
    try {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    } catch (e) { /* swallow */ }
  }

  // SL-10.S: write text to the clipboard and pop a transient "Copied!" badge
  // next to the anchor element so the user sees the action took effect. Used
  // by the dblclick-to-copy on the alts dropdown.
  function copyTextWithFlash(text, anchorEl) {
    if (!text) return;
    var done = function () { flashCopiedNear(anchorEl); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () {
        fallbackCopy(text); done();
      });
    } else {
      fallbackCopy(text); done();
    }
  }

  function flashCopiedNear(anchorEl) {
    if (!anchorEl) return;
    var rect = anchorEl.getBoundingClientRect();
    var flash = document.createElement('span');
    flash.className = 'shopping-copy-flash';
    flash.textContent = 'Copied!';
    flash.style.left = (rect.left + 6) + 'px';
    flash.style.top = (rect.top - 24) + 'px';
    document.body.appendChild(flash);
    requestAnimationFrame(function () { flash.classList.add('is-active'); });
    setTimeout(function () { flash.classList.add('is-fading'); }, 900);
    setTimeout(function () { if (flash.parentNode) flash.parentNode.removeChild(flash); }, 1400);
  }

  // SL-8.f / SL-8.g preserved on the slim head row: a small sparkline-or-glyph
  // button that opens the price history popover for the currently-selected
  // shop. Returns null when there's no entry to summarize.
  function renderHeadHistoryControl(effective) {
    var entries = entriesForItem(effective.code);
    if (entries.length === 0) return null;
    var chosenId = chosenShopForItem(effective.code);
    var shopId = chosenId || entries[0].shop;
    var entry = (data.prices[effective.code] || []).find(function (e) { return e.shop === shopId; });
    if (!entry || !entry.observations || entry.observations.length === 0) return null;
    return renderHistoryControl(entry, effective);
  }

  // SL-10.S: item-code badge as a click-to-copy button. Clicking reads the
  // sibling alts dropdown's selected option text and copies that product
  // name to the clipboard with a transient "Copied!" flash.
  function renderItemCodeButton(parentItem) {
    var btn = el('button', 'shopping-item__code');
    btn.type = 'button';
    btn.textContent = parentItem.code;
    btn.title = 'Copy product name to clipboard';
    btn.setAttribute('aria-label',
      'Copy currently-selected product name for ' + parentItem.code);
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      var titleEl = btn.closest('.shopping-item__title');
      var sel = titleEl && titleEl.querySelector('.shopping-item__alts-select');
      if (!sel) return;
      var opt = sel.options[sel.selectedIndex];
      var name = opt && opt.text;
      if (!name) return;
      copyTextWithFlash(name, btn);
    });
    return btn;
  }

  // SL-10.C: alternatives picker as a real <select> on the item's head row.
  // The trailing "+ Add alternative…" option opens the expanded body so the
  // user can fill in name + shop details inline.
  function renderAltsDropdown(parentItem, effectiveCode) {
    var alts = data.alternativesByParent[parentItem.code] || [];
    var wrap = el('div', 'shopping-item__alts');

    var sel = document.createElement('select');
    sel.className = 'shopping-select shopping-item__alts-select';
    sel.id = 'alt-pick-' + parentItem.code;
    sel.setAttribute('aria-label', 'Choose an alternative product for ' + parentItem.name);
    sel.title = 'Pick the variant of ' + parentItem.name + ' you want';

    // SL-10.Q: default option text IS the parent name (no "Default · " prefix),
    // so when the user picks the default the dropdown shows the actual product
    // name on the row.
    var defaultOpt = document.createElement('option');
    defaultOpt.value = '';
    defaultOpt.textContent = parentItem.name;
    if (effectiveCode === parentItem.code) defaultOpt.selected = true;
    sel.appendChild(defaultOpt);

    alts.forEach(function (a) {
      var o = document.createElement('option');
      o.value = a.code;
      o.textContent = a.name + (a.userAdded ? ' · you' : '');
      if (effectiveCode === a.code) o.selected = true;
      sel.appendChild(o);
    });

    var addOpt = document.createElement('option');
    addOpt.value = '__add__';
    addOpt.textContent = '+ Add alternative…';
    sel.appendChild(addOpt);

    sel.addEventListener('change', function () {
      if (sel.value === '__add__') {
        // Bounce the select back to the current effective code so the
        // marker option isn't left selected, and open the expanded body
        // where the add-alt form lives.
        sel.value = effectiveCode === parentItem.code ? '' : effectiveCode;
        if (!state.expandedItems) state.expandedItems = {};
        state.expandedItems[parentItem.code] = true;
        saveState();
        render();
        requestAnimationFrame(function () {
          var f = document.getElementById('add-alt-' + parentItem.code + '-name');
          if (f) f.focus();
        });
        return;
      }
      setEffectiveAlternative(parentItem.code, sel.value || null);
    });
    wrap.appendChild(sel);

    // Remove control surfaces only when the current pick is a user-added alt.
    var current = data.altByCode[effectiveCode];
    if (current && current.userAdded) {
      var rm = el('button', 'shopping-item__alts-remove', '✕');
      rm.type = 'button';
      rm.title = 'Remove this user-added alternative';
      rm.setAttribute('aria-label', 'Remove user-added alternative ' + current.name);
      rm.addEventListener('click', function (e) {
        e.preventDefault(); e.stopPropagation();
        if (window.confirm('Remove "' + current.name + '" from this item’s alternatives?')) {
          removeUserAlternative(parentItem.code, effectiveCode);
        }
      });
      wrap.appendChild(rm);
    }
    return wrap;
  }

  // SL-10.M + SL-10.H: one-line shop picker. The shop dropdown is the only
  // way to cycle through shops for an item — picking another shop swaps the
  // row's price/stock/ETA/shipping data slot-machine style. When no shops
  // are listed at all, render a single ⚠ icon hinting at the + Add button.
  function renderShopSummary(effective) {
    var wrap = el('div', 'shopping-item__shop-summary');
    var entries = entriesForItem(effective.code);

    if (entries.length === 0) {
      var emptyIcon = el('span', 'shopping-item__noshop', '⚠');
      emptyIcon.title = 'No shops listed yet for ' + effective.code +
        '. Use the + Add button to add one.';
      emptyIcon.setAttribute('aria-label',
        'No shops listed yet for ' + effective.code);
      wrap.appendChild(emptyIcon);
      return wrap;
    }

    var chosenId = chosenShopForItem(effective.code);
    var effectiveShopId = chosenId || entries[0].shop;
    var sel = document.createElement('select');
    sel.className = 'shopping-select shopping-item__shop-select';
    sel.id = 'shop-pick-' + effective.code;
    sel.setAttribute('aria-label', 'Choose a shop for ' + effective.code);

    entries.forEach(function (entry) {
      var shop = data.shopsById[entry.shop];
      if (!shop) return;
      var opt = document.createElement('option');
      opt.value = entry.shop;
      opt.textContent = shop.name;
      if (effectiveShopId === entry.shop) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.addEventListener('change', function () {
      state.shopOverride[effective.code] = sel.value;
      saveState();
      render();
    });
    wrap.appendChild(sel);

    wrap.appendChild(renderShopMetaForSelected(effective, effectiveShopId, entries));
    return wrap;
  }

  // Stock dot · ETA · shipping cost beside the shop dropdown for whichever
  // shop is currently chosen. Falls back to the first scoped entry when no
  // shop has an in-stock price (chosenShopForItem may return null).
  function renderShopMetaForSelected(effective, chosenId, entries) {
    var meta = el('span', 'shopping-item__shop-meta');
    var shopId = chosenId || (entries[0] && entries[0].shop);
    var entry = shopId ? (data.prices[effective.code] || []).find(function (e) { return e.shop === shopId; }) : null;
    var obs = entry ? latestObservation(entry) : null;
    var shop = shopId ? data.shopsById[shopId] : null;
    if (!shop) return meta;

    var inStock = !!(obs && obs.in_stock);
    meta.appendChild(makeStockDot(inStock));
    var etaDays = obs && typeof obs.eta_days === 'number'
      ? obs.eta_days
      : (shop.shipping && shop.shipping.default_eta_days);
    if (etaDays != null) {
      meta.appendChild(el('span', 'shopping-item__shop-eta', etaDays + 'd'));
    }
    var shipLabel = shopShippingLabelShort(shop);
    if (shipLabel) {
      meta.appendChild(el('span', 'shopping-item__shop-ship', shipLabel));
    }
    return meta;
  }

  function makeStockDot(inStock) {
    var d = el('span', 'shopping-dot');
    d.classList.add(inStock ? 'shopping-dot--in' : 'shopping-dot--out');
    return d;
  }

  function shopShippingLabelShort(shop) {
    if (!shop || !shop.shipping) return null;
    var c = shop.shipping.standard_cost;
    if (typeof c !== 'number') return null;
    if (c === 0) return 'free ship';
    return 'ship €' + c.toFixed(2);
  }

  function shopShippingLabelLong(shop) {
    if (!shop || !shop.shipping) return null;
    var c = shop.shipping.standard_cost;
    if (typeof c !== 'number') return null;
    if (c === 0) return 'Free shipping';
    var base = 'Shipping €' + c.toFixed(2);
    if (typeof shop.shipping.free_above === 'number' && shop.shipping.free_above > 0) {
      base += ' · free over €' + shop.shipping.free_above.toFixed(2);
    }
    return base;
  }

  // SL-10.G: rightmost price on every item's head. Renders the chosen shop's
  // unit price, or "—" when no price has been found yet (no shops, no
  // override, or shop entries with null prices). SL-10.K: double-clicking
  // opens an inline editor for the currently-chosen shop.
  function renderItemPrice(effective) {
    var wrap = el('div', 'shopping-item__price');
    var entries = entriesForItem(effective.code);
    // SL-10.M: the dropdown defaults to the first entry when no explicit
    // pick exists, so the head price must target the same shop.
    var chosenId = chosenShopForItem(effective.code);
    var effectiveShopId = chosenId || (entries[0] && entries[0].shop) || null;
    var price = null, currency = 'EUR';
    if (effectiveShopId) {
      var entry = (data.prices[effective.code] || []).find(function (e) { return e.shop === effectiveShopId; });
      var obs = entry ? latestObservation(entry) : null;
      if (obs && typeof obs.price === 'number') {
        price = obs.price;
        var shop = data.shopsById[effectiveShopId];
        currency = obs.currency || (shop && shop.currency) || 'EUR';
      }
    }
    wrap.textContent = price != null ? formatMoney(price, currency) : '—';
    if (price == null) wrap.classList.add('is-missing');

    // SL-10.L + SL-10.K: double-click the head price → edit the selected
    // shop's price inline. No separate "Your override" surface.
    if (effectiveShopId) {
      makeEditablePrice(wrap, {
        currentPrice: price,
        currency: currency,
        onSave: function (v) { recordUserPrice(effective.code, effectiveShopId, v); }
      });
    }
    return wrap;
  }

  // SL-10.K: make a price element double-click-editable. The element's text
  // is swapped for an <input type=number>; Enter or blur commits via
  // opts.onSave(newPrice|null), Escape cancels.
  function makeEditablePrice(elNode, opts) {
    elNode.classList.add('is-editable');
    var existingTitle = elNode.getAttribute('title');
    elNode.setAttribute('title',
      (existingTitle ? existingTitle + ' · ' : '') + 'Double-click to set price');
    elNode.addEventListener('dblclick', function (e) {
      e.preventDefault();
      e.stopPropagation();
      openInlinePriceEditor(elNode, opts);
    });
  }

  function openInlinePriceEditor(elNode, opts) {
    if (elNode.classList.contains('is-editing')) return;
    var original = elNode.textContent;
    var originalClasses = elNode.className;
    elNode.classList.add('is-editing');
    elNode.textContent = '';
    var input = document.createElement('input');
    input.type = 'number';
    input.step = '0.01';
    input.min = '0';
    input.className = 'shopping-price-editor';
    input.placeholder = '€';
    if (typeof opts.currentPrice === 'number') input.value = String(opts.currentPrice);
    input.setAttribute('aria-label', 'Set price in ' + (opts.currency || 'EUR'));
    elNode.appendChild(input);
    input.focus();
    input.select();

    var done = false;
    function finish(newPrice) {
      if (done) return;
      done = true;
      elNode.className = originalClasses;
      opts.onSave(newPrice);
    }
    function commit() {
      if (done) return;
      var raw = input.value.trim();
      if (raw === '') { finish(null); return; }
      var v = parseFloat(raw);
      if (!isFinite(v) || v < 0) { cancel(); return; }
      finish(v);
    }
    function cancel() {
      if (done) return;
      done = true;
      elNode.className = originalClasses;
      elNode.textContent = original;
    }
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); commit(); }
      else if (e.key === 'Escape') { e.preventDefault(); cancel(); }
    });
    input.addEventListener('blur', commit);
    // Stop double-click on the input itself from bubbling and reopening.
    input.addEventListener('dblclick', function (e) { e.stopPropagation(); });
  }

  // SL-10.O: dedicated add-shop form — only 5 fields, distinct from add-alt.
  function renderAddShopForm(parentItem, effective) {
    var wrap = el('div', 'shopping-add-shop');
    wrap.id = 'add-shop-body-' + parentItem.code;
    wrap.appendChild(el('h4', 'shopping-add-shop__title',
      'Add a shop for ' + parentItem.name));
    wrap.appendChild(renderInlineShopForm({
      idPrefix: 'add-shop-' + parentItem.code,
      onSave: function (vals) { addUserShop(effective.code, vals); }
    }));
    return wrap;
  }

  function renderInlineShopForm(opts) {
    var fields = [
      { key: 'shop_label',    label: 'Shop name *',    type: 'text',   placeholder: 'Shop *',       size: 'shop',  required: true },
      { key: 'url',           label: 'Product link *', type: 'url',    placeholder: 'https://… *',  size: 'url',   required: true },
      { key: 'price',         label: 'Price (EUR) *',  type: 'number', step: '0.01', placeholder: '€ *', size: 'price', required: true },
      { key: 'eta_days',      label: 'Available in (days)', type: 'number', step: '1', placeholder: 'days', size: 'eta' },
      { key: 'shipping_cost', label: 'Shipping cost',  type: 'number', step: '0.01', placeholder: 'ship €', size: 'price' }
    ];
    var values = opts.values || {};
    var form = el('div', 'shopping-inline-form shopping-inline-form--shop');
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
      if (f.required) inp.required = true;
      inputs[f.key] = inp;
      field.appendChild(inp);
      form.appendChild(field);
    });

    var actions = el('div', 'shopping-inline-form__actions');
    var saveBtn = el('button', 'shopping-btn shopping-btn--primary', opts.submitLabel || 'Add shop');
    saveBtn.type = 'button';
    saveBtn.addEventListener('click', function () {
      var shop_label = (inputs.shop_label.value || '').trim();
      var url = (inputs.url.value || '').trim();
      var price = parseFloat(inputs.price.value);
      if (!shop_label) { alert('Shop name is required.'); inputs.shop_label.focus(); return; }
      if (!url) { alert('Product URL is required.'); inputs.url.focus(); return; }
      if (!isFinite(price) || price < 0) { alert('Price is required (a non-negative number).'); inputs.price.focus(); return; }
      var eta = parseInt(inputs.eta_days.value, 10);
      var ship = parseFloat(inputs.shipping_cost.value);
      opts.onSave({
        shop_label: shop_label,
        url: url,
        price: price,
        currency: 'EUR',
        eta_days: isFinite(eta) ? eta : null,
        shipping_cost: isFinite(ship) ? ship : null
      });
    });
    actions.appendChild(saveBtn);
    form.appendChild(actions);
    return form;
  }

  function renderAddAlternativeForm(parentItem) {
    var wrap = el('div', 'shopping-add-alt');
    wrap.id = 'add-alt-body-' + parentItem.code;
    wrap.appendChild(el('h4', 'shopping-add-alt__title', 'Add an alternative for ' + parentItem.name));
    wrap.appendChild(renderInlineProductForm({
      idPrefix: 'add-alt-' + parentItem.code,
      includeName: true,
      submitLabel: 'Add alternative',
      onSave: function (vals) { addUserAlternative(parentItem.code, vals); }
    }));
    return wrap;
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

  function observationKey(item, entry, obs) {
    return item.code + '::' + entry.shop + '::' + obs.ts;
  }

  function isObservationValidated(item, entry, obs) {
    if (!item || !obs || !entry) return false;
    var v = state.validations || {};
    return !!v[observationKey(item, entry, obs)];
  }

  function toggleObservationValidation(item, entry, obs) {
    if (!state.validations) state.validations = {};
    var key = observationKey(item, entry, obs);
    if (state.validations[key]) delete state.validations[key];
    else state.validations[key] = new Date().toISOString();
    saveState();
    render();
  }

  function renderHistoryControl(entry, item) {
    var observations = (entry.observations || []).slice();
    // Sparkline uses only price-bearing points; popover lists every observation
    // so partial / null-price entries are still visible in history.
    var sortedAsc = observations.slice().sort(function (a, b) {
      return new Date(a.ts) - new Date(b.ts);
    });
    var pricePoints = sortedAsc.filter(function (o) { return typeof o.price === 'number'; });

    var wrap = el('span', 'shopping-shop__history-wrap');
    var btn = el('button', 'shopping-shop__history');
    btn.type = 'button';
    btn.setAttribute('aria-label', 'Show price history');
    if (pricePoints.length >= 2) {
      btn.appendChild(buildSparklineSvg(pricePoints));
    } else {
      // Fallback glyph for entries that have multiple observations but only
      // one price point (e.g. a partial observation alongside a real one).
      btn.appendChild(el('span', 'shopping-shop__history-glyph', '⋯'));
    }
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      wrap.classList.toggle('is-open');
    });
    wrap.appendChild(btn);
    wrap.appendChild(buildHistoryPopover(sortedAsc, entry, item));
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

  function buildHistoryPopover(sortedAsc, entry, item) {
    var pop = el('span', 'shopping-shop__history-pop');
    pop.appendChild(el('span', 'shopping-shop__history-title', 'Price history'));

    // SL-8.g: disagreement callout — when the latest observation per technique
    // varies in price between techniques, surface that disagreement explicitly.
    var disagreement = detectTechniqueDisagreement(sortedAsc);
    if (disagreement) pop.appendChild(renderDisagreementCallout(disagreement));

    var list = el('ul', 'shopping-shop__history-list');
    sortedAsc.slice().reverse().forEach(function (o) {
      var li = el('li', 'shopping-shop__history-item');
      if (o.partial) li.classList.add('is-partial');
      if (isObservationValidated(item, entry, o)) li.classList.add('is-validated');
      li.appendChild(el('span', 'shopping-shop__history-date', formatDate(o.ts)));
      var priceText = typeof o.price === 'number'
        ? formatMoney(o.price, o.currency || 'EUR')
        : (o.partial ? 'Price missing' : '—');
      li.appendChild(el('span', 'shopping-shop__history-price', priceText));
      li.appendChild(el('span', 'shopping-shop__history-technique',
        TECHNIQUE_LABELS[o.technique || 'manual']));
      // Validate button per observation. Manual entries don't need validation —
      // they were already user-authored — but bot entries do (SL-8.i).
      if ((o.technique || 'manual') !== 'manual') {
        var validated = isObservationValidated(item, entry, o);
        var btn = el('button',
          'shopping-shop__validate' + (validated ? ' is-active' : ''),
          validated ? '✓ Validated' : 'Validate');
        btn.type = 'button';
        btn.setAttribute('aria-pressed', validated ? 'true' : 'false');
        btn.title = validated
          ? 'Click to remove your validation.'
          : 'Mark this observation as verified by you.';
        btn.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
          toggleObservationValidation(item, entry, o);
        });
        li.appendChild(btn);
      }
      list.appendChild(li);
    });
    pop.appendChild(list);
    return pop;
  }

  // SL-8.g: detect a per-technique disagreement on the same shop. Returns a
  // { byTechnique: { tech: latestObs } } summary when ≥2 techniques disagree
  // on price, otherwise null.
  function detectTechniqueDisagreement(sortedAsc) {
    var byTechnique = {};
    sortedAsc.forEach(function (o) {
      if (typeof o.price !== 'number') return;
      var t = o.technique || 'manual';
      // Keep the latest observation per technique (sortedAsc → overwrite wins).
      byTechnique[t] = o;
    });
    var techs = Object.keys(byTechnique);
    if (techs.length < 2) return null;
    var prices = techs.map(function (t) { return byTechnique[t].price; });
    var min = Math.min.apply(null, prices), max = Math.max.apply(null, prices);
    if (min === max) return null;
    return { byTechnique: byTechnique, techs: techs };
  }

  function renderDisagreementCallout(d) {
    var box = el('div', 'shopping-shop__disagreement');
    box.appendChild(el('strong', null, 'Sources disagree:'));
    var list = el('ul', 'shopping-shop__disagreement-list');
    d.techs.forEach(function (t) {
      var o = d.byTechnique[t];
      var row = el('li', null);
      row.appendChild(el('span', 'shopping-shop__history-technique',
        TECHNIQUE_LABELS[t] || t));
      row.appendChild(document.createTextNode(' '));
      row.appendChild(el('span', 'shopping-shop__history-price',
        formatMoney(o.price, o.currency || 'EUR')));
      list.appendChild(row);
    });
    box.appendChild(list);
    return box;
  }

  // SL-8.e: single-line form reused by SL-8.d's "add alternative product" flow.
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
    var displayName = shop ? shop.name : g.shopId;
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
