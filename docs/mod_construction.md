---
title: Mod construction
---

<div id="mod-construction-app" class="mc-app" data-data-url="data/mod_construction_parts.json">
  <header class="mc-header">
    <button id="mc-prev" class="mc-nav-btn" aria-label="Previous part">&lsaquo;</button>
    <div class="mc-title">
      <span id="mc-part-group" class="mc-group"></span>
      <h2 id="mc-part-name">Loading…</h2>
      <span id="mc-part-counter" class="mc-counter"></span>
    </div>
    <button id="mc-next" class="mc-nav-btn" aria-label="Next part">&rsaquo;</button>
    <label class="mc-zoom">
      Zoom
      <input type="range" id="mc-zoom" min="60" max="260" value="120" step="10">
      <span id="mc-zoom-val">120%</span>
    </label>
    <button id="mc-clear-assignments" class="mc-btn-secondary" type="button">
      Clear assignments
    </button>
  </header>

  <section class="mc-panes">
    <div class="mc-pane" data-pane="plastic">
      <h3>
        Plastic — studio photos
        <button id="mc-add-plastic" class="mc-btn-secondary" type="button">
          + Add
        </button>
      </h3>
      <div class="mc-gallery" id="mc-plastic"></div>
    </div>
    <div class="mc-pane" data-pane="build">
      <h3>Build — video screenshots</h3>
      <div class="mc-gallery" id="mc-build"></div>
    </div>
    <div class="mc-pane" data-pane="renders">
      <h3>Metal — renders</h3>
      <div class="mc-gallery" id="mc-renders"></div>
    </div>
    <div class="mc-pane mc-drawing-pane" data-pane="drawing">
      <h3>Plastic — technical drawing (drag fasteners onto holes)</h3>
      <div class="mc-drawing-wrapper" id="mc-drawing"></div>
    </div>
  </section>

  <section class="mc-fasteners">
    <h3>Fasteners palette</h3>
    <div class="mc-fastener-filters" id="mc-fastener-filters"></div>
    <div class="mc-fastener-grid" id="mc-fastener-grid"></div>
  </section>

  <section class="mc-assignments-section">
    <h3>Hole assignments <small id="mc-assignments-summary"></small></h3>
    <div class="mc-assignments-table-wrapper">
      <table class="mc-assignments-table">
        <thead>
          <tr><th>Hole</th><th>X (mm)</th><th>Z (mm)</th><th>Ø (mm)</th><th>Fastener</th><th></th></tr>
        </thead>
        <tbody id="mc-assignments-body"></tbody>
      </table>
    </div>
  </section>

  <details class="mc-data-section" id="mc-data-section">
    <summary>Drawing data (vertices · edges · holes)</summary>
    <div class="mc-data-grids">
      <div class="mc-data-block">
        <h4>Vertices</h4>
        <table class="mc-data-table" id="mc-data-vertices"></table>
      </div>
      <div class="mc-data-block">
        <h4>Edges</h4>
        <table class="mc-data-table" id="mc-data-edges"></table>
      </div>
      <div class="mc-data-block">
        <h4>Holes</h4>
        <table class="mc-data-table" id="mc-data-holes"></table>
      </div>
    </div>
    <details class="mc-raw-json">
      <summary>Raw JSON</summary>
      <pre><code id="mc-data-raw"></code></pre>
    </details>
  </details>

  <!-- Floating tooltip for hover info on holes/edges -->
  <div id="mc-tooltip" class="mc-tooltip" hidden></div>

  <!-- Plastic-photo picker modal -->
  <div id="mc-plastic-picker" class="mc-modal" hidden>
    <div class="mc-modal-content">
      <header>
        <h3>Pick plastic part photos</h3>
        <button id="mc-picker-close" class="mc-btn-secondary" type="button">close</button>
      </header>
      <div id="mc-picker-categories" class="mc-fastener-filters"></div>
      <div id="mc-picker-grid" class="mc-picker-grid"></div>
      <footer>
        <span id="mc-picker-summary" class="mc-counter"></span>
        <button id="mc-picker-save" class="mc-btn-secondary" type="button">save selection</button>
      </footer>
    </div>
  </div>
</div>
