(function () {
  'use strict';

  var STORAGE_KEY = 'part-thumb-size-px';
  var MIN_PX = 40;
  var MAX_PX = 320;
  var DEFAULT_PX = 90;

  function clamp(v) {
    var n = Number(v);
    if (!isFinite(n)) return DEFAULT_PX;
    return Math.max(MIN_PX, Math.min(MAX_PX, n));
  }

  function savedSize() {
    try {
      var v = localStorage.getItem(STORAGE_KEY);
      return v ? clamp(v) : DEFAULT_PX;
    } catch (e) { return DEFAULT_PX; }
  }

  function applySize(px) {
    document.documentElement.style.setProperty('--part-thumb-size', px + 'px');
  }

  function init() {
    if (!document.querySelector('.part-thumb')) return;

    var px = savedSize();
    applySize(px);

    var wrap = document.createElement('div');
    wrap.className = 'part-thumb-slider-wrap';

    var label = document.createElement('label');
    label.textContent = 'Thumbnails';
    label.htmlFor = 'part-thumb-size-slider';

    var slider = document.createElement('input');
    slider.type = 'range';
    slider.id = 'part-thumb-size-slider';
    slider.className = 'part-thumb-slider';
    slider.min = String(MIN_PX);
    slider.max = String(MAX_PX);
    slider.step = '10';
    slider.value = String(px);
    slider.setAttribute('aria-label', 'Thumbnail size');

    slider.addEventListener('input', function () {
      applySize(slider.value);
    });
    slider.addEventListener('change', function () {
      var clamped = clamp(slider.value);
      applySize(clamped);
      try { localStorage.setItem(STORAGE_KEY, String(clamped)); } catch (e) {}
    });

    wrap.appendChild(label);
    wrap.appendChild(slider);

    var content = document.querySelector('.md-content__inner');
    if (content) {
      var first = content.firstElementChild;
      if (first) content.insertBefore(wrap, first);
      else content.appendChild(wrap);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
