(function () {
  'use strict';

  var STORAGE_KEY = 'cnc-toc-position';
  var DEFAULT_POSITION = 'left';
  var CLASS_LEFT = 'toc-position-left';
  var CLASS_RIGHT = 'toc-position-right';

  function getPosition() {
    try {
      return localStorage.getItem(STORAGE_KEY) || DEFAULT_POSITION;
    } catch (e) {
      return DEFAULT_POSITION;
    }
  }

  function savePosition(pos) {
    try { localStorage.setItem(STORAGE_KEY, pos); } catch (e) {}
  }

  function makeButton(label, onClick) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'toc-toggle-btn';
    btn.setAttribute('aria-label', label);
    btn.textContent = label;
    btn.addEventListener('click', onClick);
    return btn;
  }

  function clearInjected() {
    var nodes = document.querySelectorAll('.toc-clone, .toc-toggle-btn');
    for (var i = 0; i < nodes.length; i++) nodes[i].remove();
  }

  function renderLeft() {
    var primaryInner = document.querySelector('.md-sidebar--primary .md-sidebar__inner');
    if (!primaryInner) return;

    var wrapper = document.createElement('div');
    wrapper.className = 'toc-clone';
    wrapper.appendChild(makeButton('TOC → top right', function () { setAndApply('right'); }));

    var rightToc = document.querySelector('.md-sidebar--secondary .md-nav--secondary');
    if (rightToc && rightToc.querySelector('a')) {
      var cloned = rightToc.cloneNode(true);
      cloned.classList.add('toc-clone-nav');
      wrapper.appendChild(cloned);
    } else {
      var empty = document.createElement('p');
      empty.className = 'toc-clone-empty';
      empty.textContent = 'No headings on this page.';
      wrapper.appendChild(empty);
    }

    primaryInner.appendChild(wrapper);
  }

  function renderRight() {
    var rightInner = document.querySelector('.md-sidebar--secondary .md-sidebar__inner');
    if (!rightInner) return;
    rightInner.insertBefore(
      makeButton('TOC → bottom left', function () { setAndApply('left'); }),
      rightInner.firstChild
    );
  }

  function apply(position) {
    document.body.classList.toggle(CLASS_LEFT, position === 'left');
    document.body.classList.toggle(CLASS_RIGHT, position === 'right');
    clearInjected();
    if (position === 'left') renderLeft(); else renderRight();
  }

  function setAndApply(position) {
    savePosition(position);
    apply(position);
  }

  function init() {
    apply(getPosition());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Material instant-loading (if ever enabled) re-fires this subject per page.
  if (window.document$ && typeof window.document$.subscribe === 'function') {
    window.document$.subscribe(init);
  }
})();
