/* mod_construction.js — drives the part-loop + drag-drop UI.
 *
 * Data shape (see tools/build_mod_construction_data.py):
 *   {
 *     parts: [{ id, group, name, plastic_images[], build_images[],
 *               metal_renders[], drawing, drawing_data }, ...],
 *     fasteners: [{ id, kind, thread, length_mm, label, image }, ...]
 *   }
 *
 * Assignments are persisted to localStorage, keyed by part id.
 */
(function () {
  "use strict";

  const STORAGE_KEY = "mc-assignments-v1";
  const PLASTIC_KEY = "mc-plastic-selections-v1";

  /** Returns the page's relative URL path for site assets. */
  function urlFor(rel) {
    // The data file emits paths relative to docs/ (e.g.
    // "metal_plates_examples/.../foo.png"). The MkDocs page lives at
    // /mod_construction/ so we want the URL to be relative to the site
    // root, not the current page.
    const m = window.location.pathname.match(/^(.*\/)mod_construction\/?$/);
    const base = m ? m[1] : "/";
    return base + rel;
  }

  const app = document.getElementById("mod-construction-app");
  if (!app) return;

  const els = {
    prev: document.getElementById("mc-prev"),
    next: document.getElementById("mc-next"),
    group: document.getElementById("mc-part-group"),
    name: document.getElementById("mc-part-name"),
    counter: document.getElementById("mc-part-counter"),
    zoom: document.getElementById("mc-zoom"),
    zoomVal: document.getElementById("mc-zoom-val"),
    plastic: document.getElementById("mc-plastic"),
    build: document.getElementById("mc-build"),
    renders: document.getElementById("mc-renders"),
    drawing: document.getElementById("mc-drawing"),
    filters: document.getElementById("mc-fastener-filters"),
    fastenerGrid: document.getElementById("mc-fastener-grid"),
    assignmentsBody: document.getElementById("mc-assignments-body"),
    assignmentsSummary: document.getElementById("mc-assignments-summary"),
    clear: document.getElementById("mc-clear-assignments"),
    dataVerts: document.getElementById("mc-data-vertices"),
    dataEdges: document.getElementById("mc-data-edges"),
    dataHoles: document.getElementById("mc-data-holes"),
    dataRaw: document.getElementById("mc-data-raw"),
    addPlastic: document.getElementById("mc-add-plastic"),
    tooltip: document.getElementById("mc-tooltip"),
    picker: document.getElementById("mc-plastic-picker"),
    pickerClose: document.getElementById("mc-picker-close"),
    pickerSave: document.getElementById("mc-picker-save"),
    pickerCategories: document.getElementById("mc-picker-categories"),
    pickerGrid: document.getElementById("mc-picker-grid"),
    pickerSummary: document.getElementById("mc-picker-summary"),
  };

  const state = {
    data: null,
    partIdx: 0,
    fastenerFilter: "all",
    assignments: loadJSON(STORAGE_KEY),
    plasticSelections: loadJSON(PLASTIC_KEY),
    activeFastener: null,
    pickerCategory: "all",
    pickerWorking: null, // Set<string> of plastic library ids, scratch state
  };

  function loadJSON(key) {
    try { return JSON.parse(localStorage.getItem(key) || "{}"); }
    catch (e) { return {}; }
  }
  function saveJSON(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }
  function saveAssignments() { saveJSON(STORAGE_KEY, state.assignments); }
  function savePlastic() { saveJSON(PLASTIC_KEY, state.plasticSelections); }

  function currentPart() {
    return state.data.parts[state.partIdx];
  }

  function partAssignments(partId) {
    if (!state.assignments[partId]) state.assignments[partId] = {};
    return state.assignments[partId];
  }

  // ---------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------
  function renderGallery(container, urls) {
    container.innerHTML = "";
    if (!urls || urls.length === 0) {
      const empty = document.createElement("div");
      empty.className = "mc-empty";
      empty.textContent = "(none)";
      container.appendChild(empty);
      return;
    }
    urls.forEach((u) => {
      const img = document.createElement("img");
      img.src = urlFor(u);
      img.loading = "lazy";
      img.alt = u.split("/").pop();
      container.appendChild(img);
    });
  }

  /** Plastic gallery = built-in plastic_images plus user-attached library ids. */
  function renderPlasticGallery() {
    const part = currentPart();
    const container = els.plastic;
    container.innerHTML = "";
    const builtin = part.plastic_images || [];
    const selectedIds = (state.plasticSelections[part.id] || []);
    const libById = new Map(
      (state.data.plastic_library || []).map((p) => [p.id, p])
    );
    const userImages = selectedIds
      .map((id) => libById.get(id))
      .filter(Boolean);

    if (builtin.length === 0 && userImages.length === 0) {
      const empty = document.createElement("div");
      empty.className = "mc-empty";
      empty.textContent = "(none — use “+ Add” to attach a plastic part)";
      container.appendChild(empty);
      return;
    }
    builtin.forEach((u) => {
      const img = document.createElement("img");
      img.src = urlFor(u);
      img.loading = "lazy";
      img.alt = u.split("/").pop();
      container.appendChild(img);
    });
    userImages.forEach((p) => {
      const wrap = document.createElement("div");
      wrap.className = "mc-user-plastic";
      const img = document.createElement("img");
      img.src = urlFor(p.image);
      img.loading = "lazy";
      img.title = `${p.name} (${p.category})`;
      img.alt = p.name;
      const rm = document.createElement("button");
      rm.className = "mc-remove-pin";
      rm.type = "button";
      rm.textContent = "×";
      rm.title = "Remove";
      rm.addEventListener("click", () => removePlasticSelection(p.id));
      wrap.appendChild(img);
      wrap.appendChild(rm);
      container.appendChild(wrap);
    });
  }

  function removePlasticSelection(libId) {
    const partId = currentPart().id;
    state.plasticSelections[partId] =
      (state.plasticSelections[partId] || []).filter((x) => x !== libId);
    savePlastic();
    renderPlasticGallery();
  }

  function renderDrawing(part) {
    els.drawing.innerHTML = "";
    if (!part.drawing_data) {
      const empty = document.createElement("div");
      empty.className = "mc-empty";
      empty.style.padding = "1rem";
      empty.textContent =
        "(no plastic STL drawing for this part — run annotate_stl.py)";
      els.drawing.appendChild(empty);
      return;
    }
    const dd = part.drawing_data;
    const bbox = dd.bbox;
    // Add ~5% margin around the bbox in user units (mm).
    const mx = (bbox.x_max - bbox.x_min) * 0.06;
    const mz = (bbox.z_max - bbox.z_min) * 0.06;
    const vx0 = bbox.x_min - mx;
    const vz0 = bbox.z_min - mz;
    const vw = (bbox.x_max - bbox.x_min) + 2 * mx;
    const vh = (bbox.z_max - bbox.z_min) + 2 * mz;

    const SVG_NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(SVG_NS, "svg");
    // Use a Z-flipped viewBox so "up" on the plate is up on screen.
    svg.setAttribute("viewBox",
      `${vx0} ${-(vz0 + vh)} ${vw} ${vh}`);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

    // Silhouette polygon (fill + outline)
    const sil = document.createElementNS(SVG_NS, "polygon");
    const pts = dd.vertices_xz_mm
      .map(([x, z]) => `${x},${-z}`)
      .join(" ");
    sil.setAttribute("points", pts);
    sil.setAttribute("class", "mc-silhouette");
    svg.appendChild(sil);

    // Edges (transparent hit-area on top of the silhouette for hover info)
    const nv = dd.vertices_xz_mm.length;
    dd.edges.forEach((e) => {
      const line = document.createElementNS(SVG_NS, "line");
      line.setAttribute("x1", e.from[0]);
      line.setAttribute("y1", -e.from[1]);
      line.setAttribute("x2", e.to[0]);
      line.setAttribute("y2", -e.to[1]);
      line.setAttribute("class", "mc-edge-line");
      line.addEventListener("mouseenter", (evt) => {
        highlightEdgeRow(e.i, true);
        showTooltip(edgeTooltipHtml(e, nv), evt);
      });
      line.addEventListener("mousemove", positionTooltip);
      line.addEventListener("mouseleave", () => {
        highlightEdgeRow(e.i, false);
        hideTooltip();
      });
      svg.appendChild(line);
    });

    // Hole circles
    const partId = part.id;
    const assigns = partAssignments(partId);
    dd.holes.forEach((h) => {
      const c = document.createElementNS(SVG_NS, "circle");
      c.setAttribute("cx", h.cx);
      c.setAttribute("cy", -h.cz);
      c.setAttribute("r", h.d / 2);
      c.setAttribute("class", "mc-hole-target");
      c.dataset.holeIdx = h.i;
      if (assigns[h.i]) c.classList.add("mc-assigned");
      attachDropListeners(c, h.i);
      c.addEventListener("mouseenter", (evt) => {
        highlightHoleRow(h.i, true);
        showTooltip(holeTooltipHtml(h), evt);
      });
      c.addEventListener("mousemove", positionTooltip);
      c.addEventListener("mouseleave", () => {
        highlightHoleRow(h.i, false);
        hideTooltip();
      });
      svg.appendChild(c);

      const label = document.createElementNS(SVG_NS, "text");
      label.setAttribute("x", h.cx);
      label.setAttribute("y", -h.cz - h.d / 2 - 1);
      label.setAttribute("class", "mc-hole-label");
      label.setAttribute("text-anchor", "middle");
      label.textContent = `H${h.i}`;
      svg.appendChild(label);
    });

    els.drawing.appendChild(svg);
  }

  function isAxisAligned(e) {
    const a = Math.abs(e.angle_deg);
    return a < 0.5 || Math.abs(a - 90) < 0.5 || Math.abs(a - 180) < 0.5;
  }

  // ---------------------------------------------------------------------
  // Floating tooltip (follows mouse, rich content)
  // ---------------------------------------------------------------------
  function showTooltip(html, evt) {
    els.tooltip.innerHTML = html;
    positionTooltip(evt);
    els.tooltip.hidden = false;
  }
  function hideTooltip() {
    els.tooltip.hidden = true;
  }
  function positionTooltip(evt) {
    const pad = 14;
    // Flip to the left of the cursor if too close to the right edge.
    const rect = els.tooltip.getBoundingClientRect();
    let x = evt.clientX + pad;
    let y = evt.clientY + pad;
    if (x + rect.width > window.innerWidth - 8) {
      x = evt.clientX - rect.width - pad;
    }
    if (y + rect.height > window.innerHeight - 8) {
      y = evt.clientY - rect.height - pad;
    }
    els.tooltip.style.left = `${Math.max(4, x)}px`;
    els.tooltip.style.top = `${Math.max(4, y)}px`;
  }

  function holeTooltipHtml(h) {
    return (
      `<span class="mc-tooltip-title">H${h.i}</span>` +
      `X = ${h.cx.toFixed(3)} mm\n` +
      `Z = ${h.cz.toFixed(3)} mm\n` +
      `Ø = ${h.d.toFixed(3)} mm  (r ${h.r.toFixed(3)})`
    );
  }
  function edgeTooltipHtml(e, nv) {
    const axisLine = isAxisAligned(e)
      ? "axis-aligned"
      : `∠ ${e.angle_deg.toFixed(2)}°`;
    return (
      `<span class="mc-tooltip-title">E${e.i}  V${e.i} → V${
        (e.i + 1) % nv
      }</span>` +
      `length = ${e.length_mm.toFixed(3)} mm\n` +
      axisLine + "\n" +
      `from = (${e.from[0].toFixed(2)}, ${e.from[1].toFixed(2)})\n` +
      `to   = (${e.to[0].toFixed(2)}, ${e.to[1].toFixed(2)})`
    );
  }

  function highlightHoleRow(idx, on) {
    const row = els.dataHoles.querySelector(`tr[data-hole-idx="${idx}"]`);
    if (row) row.classList.toggle("mc-data-hover", on);
    const c = els.drawing.querySelector(
      `circle.mc-hole-target[data-hole-idx="${idx}"]`
    );
    if (c) c.classList.toggle("mc-svg-hover", on);
  }
  function highlightEdgeRow(idx, on) {
    const row = els.dataEdges.querySelector(`tr[data-edge-idx="${idx}"]`);
    if (row) row.classList.toggle("mc-data-hover", on);
  }

  function renderDataTables(part) {
    const dd = part.drawing_data;
    if (!dd) {
      els.dataVerts.innerHTML = "<tr><td>(no drawing)</td></tr>";
      els.dataEdges.innerHTML = "";
      els.dataHoles.innerHTML = "";
      els.dataRaw.textContent = "";
      return;
    }
    const nv = dd.vertices_xz_mm.length;
    els.dataVerts.innerHTML =
      "<thead><tr><th>id</th><th>X</th><th>Z</th></tr></thead><tbody>" +
      dd.vertices_xz_mm
        .map(([x, z], i) =>
          `<tr><td>V${i}</td><td>${x.toFixed(3)}</td><td>${z.toFixed(3)}</td></tr>`)
        .join("") +
      "</tbody>";
    els.dataEdges.innerHTML =
      "<thead><tr><th>id</th><th>length</th><th>angle</th></tr></thead><tbody>" +
      dd.edges
        .map((e) => {
          const ang = isAxisAligned(e)
            ? "axis-aligned"
            : `${e.angle_deg.toFixed(2)}°`;
          return `<tr data-edge-idx="${e.i}"><td>V${e.i}→V${
            (e.i + 1) % nv
          }</td><td>${e.length_mm.toFixed(3)}</td><td>${ang}</td></tr>`;
        })
        .join("") +
      "</tbody>";
    els.dataHoles.innerHTML =
      "<thead><tr><th>id</th><th>X</th><th>Z</th><th>Ø</th></tr></thead><tbody>" +
      dd.holes
        .map((h) =>
          `<tr data-hole-idx="${h.i}"><td>H${h.i}</td><td>${h.cx.toFixed(3)}</td><td>${h.cz.toFixed(3)}</td><td>${h.d.toFixed(3)}</td></tr>`)
        .join("") +
      "</tbody>";
    els.dataRaw.textContent = JSON.stringify(dd, null, 2);
    // Hover synchronisation: hovering a table row highlights its SVG element.
    els.dataHoles.querySelectorAll("tr[data-hole-idx]").forEach((tr) => {
      const i = Number(tr.dataset.holeIdx);
      tr.addEventListener("mouseenter", () => highlightHoleRow(i, true));
      tr.addEventListener("mouseleave", () => highlightHoleRow(i, false));
    });
  }

  function renderFasteners() {
    const f = state.data.fasteners;
    // Filter chips
    els.filters.innerHTML = "";
    const kinds = ["all", ...new Set(f.map((x) => x.kind))];
    const threads = [...new Set(f.map((x) => x.thread))].sort();
    [...kinds, ...threads].forEach((tag) => {
      const chip = document.createElement("button");
      chip.className =
        "mc-filter-chip" + (state.fastenerFilter === tag ? " active" : "");
      chip.textContent = tag;
      chip.dataset.filter = tag;
      chip.addEventListener("click", () => {
        state.fastenerFilter = tag;
        renderFasteners();
      });
      els.filters.appendChild(chip);
    });

    // Grid
    els.fastenerGrid.innerHTML = "";
    const filter = state.fastenerFilter;
    f.filter((x) => {
      if (filter === "all") return true;
      return x.kind === filter || x.thread === filter;
    }).forEach((x) => {
      const card = document.createElement("div");
      card.className = "mc-fastener-card";
      card.draggable = true;
      card.dataset.fastenerId = x.id;
      card.innerHTML = `
        <img src="${urlFor(x.image)}" alt="${x.label}">
        <span class="mc-fastener-label">${x.label}</span>
      `;
      card.addEventListener("dragstart", (e) => {
        state.activeFastener = x.id;
        e.dataTransfer.setData("text/plain", x.id);
        e.dataTransfer.effectAllowed = "copy";
      });
      card.addEventListener("dragend", () => { state.activeFastener = null; });
      // Mobile/click fallback: tap to select, then tap a hole.
      card.addEventListener("click", () => {
        state.activeFastener = x.id;
        document.querySelectorAll(".mc-fastener-card").forEach((c) =>
          c.style.outline = (c === card ? "2px solid var(--mc-accent)" : ""));
      });
      els.fastenerGrid.appendChild(card);
    });
  }

  function attachDropListeners(circle, holeIdx) {
    circle.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      circle.classList.add("mc-drag-over");
    });
    circle.addEventListener("dragleave", () => {
      circle.classList.remove("mc-drag-over");
    });
    circle.addEventListener("drop", (e) => {
      e.preventDefault();
      circle.classList.remove("mc-drag-over");
      const fastenerId = e.dataTransfer.getData("text/plain")
        || state.activeFastener;
      if (!fastenerId) return;
      setAssignment(holeIdx, fastenerId);
    });
    circle.addEventListener("click", () => {
      if (state.activeFastener) {
        setAssignment(holeIdx, state.activeFastener);
      }
    });
  }

  function setAssignment(holeIdx, fastenerId) {
    const part = currentPart();
    const assigns = partAssignments(part.id);
    assigns[holeIdx] = fastenerId;
    saveAssignments();
    renderDrawing(part);
    renderAssignments();
  }

  function removeAssignment(holeIdx) {
    const part = currentPart();
    const assigns = partAssignments(part.id);
    delete assigns[holeIdx];
    saveAssignments();
    renderDrawing(part);
    renderAssignments();
  }

  function renderAssignments() {
    const part = currentPart();
    els.assignmentsBody.innerHTML = "";
    if (!part.drawing_data) {
      els.assignmentsSummary.textContent = "(no drawing for this part)";
      return;
    }
    const assigns = partAssignments(part.id);
    const fByid = new Map(state.data.fasteners.map((f) => [f.id, f]));
    const holes = part.drawing_data.holes;
    let assignedCount = 0;
    holes.forEach((h) => {
      const fid = assigns[h.i];
      const f = fid ? fByid.get(fid) : null;
      if (f) assignedCount += 1;
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>H${h.i}</td>
        <td>${h.cx.toFixed(2)}</td>
        <td>${h.cz.toFixed(2)}</td>
        <td>${h.d.toFixed(2)}</td>
        <td>${
          f
            ? `<img src="${urlFor(f.image)}" alt="${f.label}">${f.label}`
            : '<span class="mc-empty">— unassigned —</span>'
        }</td>
        <td>${
          f
            ? `<button class="mc-remove-btn" data-hole="${h.i}">remove</button>`
            : ""
        }</td>
      `;
      els.assignmentsBody.appendChild(tr);
    });
    els.assignmentsSummary.textContent =
      `${assignedCount} / ${holes.length} assigned`;
    els.assignmentsBody
      .querySelectorAll(".mc-remove-btn")
      .forEach((btn) => btn.addEventListener("click", () =>
        removeAssignment(Number(btn.dataset.hole))));
  }

  function renderAll() {
    const part = currentPart();
    if (!part) return;
    els.group.textContent = part.group;
    els.name.textContent = part.name;
    els.counter.textContent =
      `Part ${state.partIdx + 1} / ${state.data.parts.length}`;
    els.prev.disabled = state.partIdx <= 0;
    els.next.disabled = state.partIdx >= state.data.parts.length - 1;
    renderPlasticGallery();
    renderGallery(els.build, part.build_images);
    renderGallery(els.renders, part.metal_renders);
    renderDataTables(part);
    renderDrawing(part);
    renderAssignments();
  }

  // ---------------------------------------------------------------------
  // Wire up
  // ---------------------------------------------------------------------
  els.prev.addEventListener("click", () => {
    if (state.partIdx > 0) { state.partIdx -= 1; renderAll(); }
  });
  els.next.addEventListener("click", () => {
    if (state.partIdx < state.data.parts.length - 1) {
      state.partIdx += 1; renderAll();
    }
  });
  els.zoom.addEventListener("input", () => {
    const v = els.zoom.value;
    app.style.setProperty("--mc-zoom", v / 100);
    els.zoomVal.textContent = `${v}%`;
  });
  els.clear.addEventListener("click", () => {
    if (!confirm("Clear all hole assignments for the current part?")) return;
    state.assignments[currentPart().id] = {};
    saveAssignments();
    renderDrawing(currentPart());
    renderAssignments();
  });

  // ---------------------------------------------------------------------
  // Plastic-photo picker
  // ---------------------------------------------------------------------
  function openPicker() {
    const partId = currentPart().id;
    state.pickerWorking = new Set(state.plasticSelections[partId] || []);
    state.pickerCategory = "all";
    renderPickerCategories();
    renderPickerGrid();
    els.picker.hidden = false;
  }
  function closePicker() {
    els.picker.hidden = true;
    state.pickerWorking = null;
  }
  function savePicker() {
    const partId = currentPart().id;
    state.plasticSelections[partId] = [...state.pickerWorking];
    savePlastic();
    closePicker();
    renderPlasticGallery();
  }

  function renderPickerCategories() {
    const lib = state.data.plastic_library || [];
    const cats = ["all", ...new Set(lib.map((p) => p.category))];
    els.pickerCategories.innerHTML = "";
    cats.forEach((c) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className =
        "mc-filter-chip" + (state.pickerCategory === c ? " active" : "");
      chip.textContent = c;
      chip.addEventListener("click", () => {
        state.pickerCategory = c;
        renderPickerCategories();
        renderPickerGrid();
      });
      els.pickerCategories.appendChild(chip);
    });
  }

  function renderPickerGrid() {
    const lib = state.data.plastic_library || [];
    els.pickerGrid.innerHTML = "";
    const filtered = lib.filter((p) =>
      state.pickerCategory === "all" || p.category === state.pickerCategory);
    filtered.forEach((p) => {
      const card = document.createElement("div");
      card.className = "mc-picker-card"
        + (state.pickerWorking.has(p.id) ? " selected" : "");
      card.innerHTML = `
        <img src="${urlFor(p.image)}" alt="${p.name}">
        <div class="mc-picker-name">${p.name}</div>
        <div class="mc-picker-category">${p.category}</div>
      `;
      card.addEventListener("click", () => {
        if (state.pickerWorking.has(p.id)) state.pickerWorking.delete(p.id);
        else state.pickerWorking.add(p.id);
        renderPickerGrid();
        els.pickerSummary.textContent =
          `${state.pickerWorking.size} selected`;
      });
      els.pickerGrid.appendChild(card);
    });
    els.pickerSummary.textContent = `${state.pickerWorking.size} selected`;
  }

  els.addPlastic.addEventListener("click", openPicker);
  els.pickerClose.addEventListener("click", closePicker);
  els.pickerSave.addEventListener("click", savePicker);
  els.picker.addEventListener("click", (e) => {
    if (e.target === els.picker) closePicker(); // backdrop click
  });
  document.addEventListener("keydown", (e) => {
    if (!els.picker.hidden && e.key === "Escape") closePicker();
  });

  // Initial zoom from default
  app.style.setProperty("--mc-zoom", els.zoom.value / 100);
  els.zoomVal.textContent = `${els.zoom.value}%`;

  // Load data
  fetch(urlFor(app.dataset.dataUrl))
    .then((r) => r.json())
    .then((data) => {
      state.data = data;
      if (!data.parts.length) {
        els.name.textContent = "(no parts found)";
        return;
      }
      renderFasteners();
      renderAll();
    })
    .catch((err) => {
      els.name.textContent = "Failed to load parts data";
      console.error(err);
    });
})();
