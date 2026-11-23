
"use strict";

const modulePortal = (() => {
  const active = run => ["queued", "running"].includes(run.state);
  const labels = {
    pole_beton: ["Concrete", "#7139a1", "C"], pole_generic: ["Generic", "#087f66", "G"],
    pole_metal: ["Metal", "#1769a0", "M"], pole_wood: ["Wood", "#87511a", "W"]
  };
  const node = (tag, content) => {
    const item = document.createElement(tag);
    if (content !== undefined) item.textContent = content;
    return item;
  };
  const option = (value, title) => {
    const item = node("option", title);
    item.value = value;
    return item;
  };
  const button = (title, click) => {
    const item = node("button", title);
    item.type = "button";
    item.onclick = click;
    return item;
  };
  const link = (title, href) => {
    const item = node("a", title);
    item.href = href;
    item.download = "";
    return item;
  };
  const errorMessage = (id, callback) => async event => {
    try {
      await callback(event);
    } catch (error) {
      $(id).textContent = error.message;
    }
  };
  const status = callback => errorMessage("module-status", callback);
  const registryStatus = callback => errorMessage("module-manager-status", callback);
  const runPath = id => root + "/module-runs/" + id;
  const temporaryReviews = new Map();
  const manualTemporaryPoles = new Map();
  let models = [], mapPick;

  function updateModelPicker(selected = $("pole-model-choice").value) {
    const choice = $("pole-model-choice");
    choice.replaceChildren(option("", "Bundled model"), ...models.map(model =>
      option(model.id, model.name + " (" + model.sha256.slice(0, 8) + ")")));
    if (models.some(model => model.id === selected)) choice.value = selected;
  }

  $("pole-model-add").onclick = () => $("pole-model-dialog").showModal();
  $("pole-model-upload").onsubmit = errorMessage("pole-model-status", async event => {
    event.preventDefault();
    const submit = event.submitter;
    const file = $("pole-model-file").files[0];
    const labels = $("pole-model-labels").value.trim() || "{}";
    const query = new URLSearchParams({name: file.name, labels});
    submit.disabled = true;
    $("pole-model-status").textContent = "Uploading checkpoint…";
    try {
      const response = await fetch(root + "/pole-models?" + query, {
        method: "POST", headers: {"X-StreetView-Request": "1"}, body: file
      });
      const model = await response.json();
      if (!response.ok) throw Error(typeof model.detail === "string" ? model.detail : "Could not upload checkpoint.");
      models.unshift(model);
      updateModelPicker(model.id);
      $("pole-model-upload").reset();
      $("pole-model-status").textContent = "";
      $("pole-model-dialog").close();
    } finally {
      submit.disabled = false;
    }
  });
  let registry = [], rows = [], result, overlay, rays, handle, context, updateToken = 0;

  async function manage() {
    registry = await api(root + "/modules");
    const entries = registry.map(version => {
      const m = version.manifest;
      const box = node("article");
      box.append(node("h3", m.name + " " + version.version), node("p", m.description));
      const detail = node("details");
      detail.append(node("summary", "Package details"), node("p",
        [m.stage.replaceAll("_", " "), m.runtime, m.inputs.join(", "), m.outputs.join(", "),
          "GPU " + m.gpu, "Up to " + m.timeout_seconds + " seconds"].join(" | ")));
      detail.append(node("p", "Package SHA-256"), node("code", version.sha256));
      if (m.model) detail.append(node("p", "Model " + m.model.path), node("code", m.model.sha256));
      const url = root + "/modules/" + version.module_id + "/versions/" + version.version;
      box.append(detail, node("span", version.enabled ? "Enabled" : "Disabled"),
        button(version.enabled ? "Disable" : "Enable", registryStatus(async () => {
          await api(url, "PATCH", {enabled: !version.enabled});
          await manage();
          await refreshVersions();
        })), button("Remove unused version", registryStatus(async () => {
          await api(url, "DELETE");
          await manage();
          await refreshVersions();
        })));
      return box;
    });
    $("module-versions").replaceChildren(...entries);
    if (!entries.length) $("module-versions").append(node("p", "No modules installed."));
  }

  $("modules-open").onclick = registryStatus(async () => {
    $("module-manager").showModal();
    await manage();
  });
  $("module-install").onsubmit = registryStatus(async event => {
    event.preventDefault();
    const file = $("module-zip").files[0];
    if (!file) return;
    const submit = $("module-install").querySelector("button");
    submit.disabled = true;
    try {
      const response = await fetch(root + "/modules/install", {method: "POST", body: file,
        headers: {"X-StreetView-Request": "1", "Content-Type": "application/zip"}});
      const payload = await response.json();
      if (!response.ok) throw Error(payload.detail || "Installation failed");
      $("module-manager-status").textContent = payload.manifest.name + " " + payload.version + " installed.";
      $("module-install").reset();
      await manage();
      await refreshVersions();
    } finally {
      submit.disabled = false;
    }
  });

  function configure() {
    const item = registry.find(version => key(version) === $("module-choice").value);
    const ordinary = $("module-parameters"), advanced = $("module-advanced");
    ordinary.replaceChildren();
    advanced.replaceChildren();
    $("module-run").disabled = !item;
    $("module-advanced-settings").hidden = true;
    $("pole-model-options").hidden = item?.module_id !== "poles-detection" || !item.manifest.custom_checkpoint;
    $("module-temporary-option").hidden = item?.manifest.stage !== "post_processing" ||
      !item.manifest.outputs.includes("vector");
    if (!item) return;
    for (const [name, spec] of Object.entries(item.manifest.parameters)) {
      const label = node("label");
      label.append(node("span", spec.description || name.replaceAll("_", " ")));
      let field = node("input");
      if (spec.choices) {
        field = node("select");
        field.append(...spec.choices.map(value => option(value, labels[value]?.[0] || (value === "" ? "All classes" : value))));
      } else if (spec.type === "boolean") {
        field.type = "checkbox";
        field.checked = spec.default;
      } else if (spec.type === "integer" || spec.type === "number") {
        field.type = "number";
        field.step = spec.type === "integer" ? "1" : "any";
        if (spec.min !== undefined) field.min = spec.min;
        if (spec.max !== undefined) field.max = spec.max;
        field.required = true;
      }
      field.name = name;
      field.value = spec.default;
      label.append(field);
      const row = node("li");
      row.append(label);
      (spec.advanced ? advanced : ordinary).append(row);
    }
    $("module-advanced-settings").hidden = !advanced.children.length;
  }

  const key = module => module.module_id + "/" + module.version;
  async function refreshVersions() {
    if (!context) return;
    const previous = $("module-choice").value;
    registry = await api(root + "/modules");
    if (registry.some(version => version.enabled && version.manifest.custom_checkpoint)) {
      models = await api(root + "/pole-models");
      updateModelPicker();
    }
    const enabled = registry.filter(version => version.enabled);
    $("module-choice").replaceChildren(...enabled.map(version => option(key(version),
      version.manifest.name + " " + version.version)));
    if (!enabled.length) $("module-choice").append(option("", "No enabled modules"));
    if (enabled.some(version => key(version) === previous)) $("module-choice").value = previous;
    configure();
    if (window.publicationControls) window.publicationControls.modules(registry, rows);
  }
  $("module-choice").onchange = configure;

  $("module-configuration").onsubmit = status(async event => {
    event.preventDefault();
    const item = registry.find(version => key(version) === $("module-choice").value);
    if (!item || !context) return;
    const requested = context, submit = $("module-run");
    const parameters = Object.fromEntries(Object.entries(item.manifest.parameters).map(([name, spec]) => {
      const field = event.target.elements.namedItem(name);
      const value = spec.type === "boolean" ? field.checked :
        ["integer", "number"].includes(spec.type) ? Number(field.value) : field.value;
      return [name, value];
    }));
    submit.disabled = true;
    try {
      await api(requested.path + "/modules/" + item.module_id + "/runs", "POST",
        {version: item.version, parameters,
          temporary: !$("module-temporary-option").hidden && $("module-temporary").checked,
          pole_model: $("pole-model-options").hidden ? null : $("pole-model-choice").value || null,
          request_key: crypto.randomUUID()});
      if (context === requested) {
        $("module-status").textContent = "Module run queued.";
        await refreshRuns();
      }
    } finally {
      submit.disabled = false;
    }
  });

  async function refreshRuns() {
    const requested = context;
    if (!requested) return;
    const query = new URLSearchParams({limit: 200, source_job: requested.job});
    const latest = await api(requested.path + "/module-runs?" + query);
    if (context !== requested) return;
    rows = latest;
    const items = rows.map(run => {
      const item = node("li");
      const name = registry.find(version => key(version) === key(run))?.manifest.name || run.module_id;
      const description = [name, run.version, run.model_name, run.state, new Date(run.created).toLocaleString(),
        run.temporary ? (run.expired ? "Temporary results expired" : "Temporary results") : "",
        run.stale && run.state === "completed" ? "Previous result" : ""].filter(Boolean).join(" | ");
      item.append(node("span", description));
      if (active(run)) {
        const progress = node("progress");
        progress.value = run.progress;
        progress.max = 100;
        progress.setAttribute("aria-label", "Module progress");
        item.append(progress, node("span", run.progress + "%"), button("Cancel", status(async () => {
          await api(runPath(run.id) + "/cancel", "POST");
          await refreshRuns();
        })));
      }
      if (run.error) item.append(node("p", run.error));
      if (run.state === "completed" && !run.expired) item.append(button("Open results", status(() => openResult(run))));
      item.append(button("Logs", status(async () => {
        const logs = await api(runPath(run.id) + "/logs");
        $("module-log").textContent = logs.tail || logs.error || "No log output yet.";
        $("module-log-dialog").showModal();
      })));
      return item;
    });
    $("module-runs").replaceChildren(...items);
    if (window.publicationControls) window.publicationControls.modules(registry, rows);
  }
  $("module-temporary-info").onclick = () => $("module-temporary-help").showModal();
  function goToMap() {
    const map = $("map");
    map.focus({preventScroll: true});
    map.scrollIntoView({block: "start"});
  }
  $("module-go-to-map").onclick = goToMap;
  setInterval(() => {
    if (context && rows.some(active)) status(refreshRuns)();
  }, 1600);

  function clearDetail() {
    handle?.remove();
    handle = undefined;
    $("module-feature").hidden = true;
    $("module-feature").replaceChildren();
  }
  function clearResult() {
    cancelMapPick();
    clearDetail();
    overlay?.remove();
    rays?.remove();
    rays = undefined;
    result = undefined;
    $("module-result").hidden = true;
    $("module-rays").checked = false;
  }

  async function attach(path, job, mapViewer) {
    if (context?.path === path && context?.job === job) return;
    for (const [name, level] of [["module-markers", 620], ["module-edit", 630]]) {
      const pane = mapViewer.map.getPane(name) || mapViewer.map.createPane(name);
      pane.style.zIndex = level;
    }
    context = {path, job, viewer: mapViewer};
    rows = [];
    clearResult();
    $("additional-processing").hidden = false;
    await refreshVersions();
    await refreshRuns();
  }

  function detach() {
    context = undefined;
    rows = [];
    clearResult();
    $("additional-processing").hidden = true;
  }

  function withTemporaryReview(feature) {
    return temporaryReviews.get(feature.id) || feature;
  }

  async function downloadTemporary(selected, layer, approved) {
    const count = selected.run.summary.layers.find(item => item.id === layer).count;
    const features = [];
    const add = feature => {
      if (!approved || feature.properties.review_state === "approved") {
        features.push({type: "Feature", id: feature.id, geometry: feature.geometry, properties: feature.properties});
      }
    };
    for (let offset = 0; offset < count; offset += 1000) {
      const page = await api(runPath(selected.run.id) + "/features?" + new URLSearchParams({layer, limit: 1000, offset}));
      page.features.map(withTemporaryReview).forEach(add);
    }
    getManualPoles(selected, layer).forEach(add);
    const url = URL.createObjectURL(new Blob([JSON.stringify({type: "FeatureCollection", features})],
      {type: "application/geo+json"}));
    const download = link("Download temporary results", url);
    download.download = layer + ".geojson";
    download.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function exportLinks() {
    const layer = $("module-layer").value;
    const approved = $("module-approved-export").checked;
    if (layer && result?.run.temporary) {
      const selected = result;
      $("module-exports").replaceChildren(button("Download GeoJSON", status(async event => {
        const trigger = event.currentTarget;
        trigger.disabled = true;
        try {
          await downloadTemporary(selected, layer, approved);
        } finally {
          trigger.disabled = false;
        }
      })));
      return;
    }
    $("module-exports").replaceChildren(...(layer ? ["geojson", "csv", "gpkg"].map(format =>
      link(format.toUpperCase(), runPath(result.run.id) + "/export?" +
        new URLSearchParams({layer, format, approved}))) : []));
  }

  async function openResult(run) {
    const token = ++updateToken, requested = context;
    const artifacts = await api(runPath(run.id) + "/artifacts");
    if (token !== updateToken || requested !== context) return;
    clearResult();
    result = {run, features: [], artifacts, offset: 0};
    $("module-result").hidden = false;
    $("module-result-title").textContent = registry.find(version => key(version) === key(run))?.manifest.name || run.module_id;
    const statistics = Object.entries(run.summary.statistics || {})
      .filter(([, value]) => typeof value === "number")
      .map(([name, value]) => {
        const label = name.replaceAll("_", " ");
        const row = node("div");
        row.append(node("dt", label.charAt(0).toUpperCase() + label.slice(1)), node("dd", value.toLocaleString()));
        return row;
      });
    $("module-result-summary").replaceChildren(...statistics);
    $("module-warnings").replaceChildren(...(run.summary.warnings || []).filter(message => typeof message === "string")
      .map(message => node("li", message)));
    const renderedLayers = run.summary.layers || [];
    $("module-layer").replaceChildren(...renderedLayers.map(layer => option(layer.id, layer.id === "poles" ? "Electrical Poles" : layer.id)));
    $("module-layer-controls").hidden = !renderedLayers.length;
    $("module-rays-control").hidden = !renderedLayers.length || !artifacts.some(item => item.path === "pole_rays.geojson");
    $("module-artifacts").replaceChildren(...artifacts.map(item =>
      link(item.path, runPath(run.id) + "/artifacts/" + item.path.split("/").map(encodeURIComponent).join("/"))));
    $("module-temporary-notice").hidden = !run.temporary;
    $("module-temporary-notice").textContent = run.temporary ?
      "Temporary results expire " + new Date(run.expires_at).toLocaleString() +
      ". Reviews are kept in this tab. Download GeoJSON to save your edits or analyse the data later." : "";
    $("module-layer-label").textContent = run.temporary ? "Add temporary layer to map" : "Show layer on map";
    $("module-layer-show").checked = !run.temporary;
    if (renderedLayers.length) await loadLayer(false, !run.temporary);
  }

  function plot() {
    overlay?.remove();
    if (!result || !$("module-layer-show").checked) return;
    const category = $("module-class").value, review = $("module-review").value, conf = Number($("module-confidence").value);
    const features = [...result.features, ...getManualPoles(result, $("module-layer").value)];
    overlay = L.geoJSON(features.filter(feature => {
      const p = feature.properties;
      return (!category || category === p.pole_class) && (!review || review === p.review_state) &&
        (!conf || p.origin === "manual" || Number(p.mean_detection_confidence || 0) >= conf);
    }), {
      pointToLayer: (feature, position) => {
        const [title, color, letter] = labels[feature.properties.pole_class] || ["Feature", "#287691", "+"];
        const icon = L.divIcon({className: "module-pin", html: '<span style="background:' + color + '">' + letter + '</span>',
          iconSize: [23, 23], iconAnchor: [11, 11]});
        return L.marker(position, {icon, pane: "module-markers", title: title + " " + feature.properties.source_id, keyboard: true});
      },
      onEachFeature: (feature, marker) => marker.on("click", status(() => inspect(feature)))
    }).addTo(context.viewer.map);
  }

  async function loadLayer(more = false, fit = false) {
    const selected = result, layer = $("module-layer").value, token = ++updateToken;
    if (!selected || !layer) return;
    if (!more) {
      cancelMapPick();
      clearDetail();
      selected.offset = 0;
      selected.features = [];
    }
    const response = await api(runPath(selected.run.id) + "/features?" +
      new URLSearchParams({layer, limit: 1000, offset: selected.offset}));
    if (token !== updateToken || selected !== result) return;
    selected.features.push(...response.features.map(withTemporaryReview));
    selected.offset += response.features.length;
    selected.total = response.total ?? selected.run.summary.layers.find(item => item.id === layer).count;
    updateLayerCount(selected, layer);
    $("module-more").hidden = selected.offset >= selected.total || !response.features.length;
    $("module-pole-filters").hidden = layer !== "poles";
    $("module-legend").hidden = layer !== "poles";
    $("module-add-pole").hidden = layer !== "poles" || selected.run.module_id !== "poles-detection";
    if (layer !== "poles") {
      $("module-confidence").value = 0;
      $("module-class").value = "";
    }
    exportLinks();
    plot();
    if (fit) focusLayer();
  }

  function getManualPoles(selected, layer) {
    return layer === "poles" ? (manualTemporaryPoles.get(selected.run.id) || []).map(withTemporaryReview) : [];
  }

  function updateLayerCount(selected, layer) {
    const manualCount = getManualPoles(selected, layer).length;
    $("module-layer-count").textContent =
      (selected.offset + manualCount) + " of " + (selected.total + manualCount) + " features";
  }

  function cancelMapPick() {
    if (!mapPick) return;
    mapPick.map.off("click", mapPick.click);
    mapPick.map.getContainer().style.cursor = "";
    document.removeEventListener("keydown", mapPick.escape);
    mapPick = undefined;
  }

  function setPoleCoordinates(location) {
    const {lng, lat} = location.wrap();
    $("manual-pole-lon").value = lng.toFixed(7);
    $("manual-pole-lat").value = lat.toFixed(7);
  }

  function openManualPole() {
    cancelMapPick();
    $("manual-pole-form").reset();
    $("manual-pole-status").textContent = "";
    $("manual-pole-form").dataset.poleId = crypto.randomUUID();
    setPoleCoordinates(context.viewer.map.getCenter());
    $("manual-pole-dialog").showModal();
  }
  $("module-add-pole").onclick = openManualPole;

  $("manual-pole-pick").onclick = () => {
    const map = context.viewer.map;
    $("manual-pole-dialog").close();
    const click = event => {
      cancelMapPick();
      setPoleCoordinates(event.latlng);
      $("manual-pole-dialog").showModal();
    };
    const escape = event => {
      if (event.key !== "Escape") return;
      cancelMapPick();
      $("manual-pole-dialog").showModal();
    };
    mapPick = {map, click, escape};
    map.on("click", click);
    map.getContainer().style.cursor = "crosshair";
    document.addEventListener("keydown", escape);
    goToMap();
  };

  $("manual-pole-form").onsubmit = errorMessage("manual-pole-status", async event => {
    event.preventDefault();
    const selected = result, submit = event.submitter;
    const id = event.target.dataset.poleId;
    const lon = Number($("manual-pole-lon").value), lat = Number($("manual-pole-lat").value);
    const pole_class = $("manual-pole-class").value;
    submit.disabled = true;
    try {
      if (selected.run.temporary) {
        const geometry = {type: "Point", coordinates: [lon, lat]};
        const feature = {type: "Feature", id, geometry, evidence: [], properties: {
          pole_class, origin: "manual", source_id: "manual-" + id, layer: "poles", review_state: "approved",
          original_geometry: geometry, estimated_geometry: geometry
        }};
        manualTemporaryPoles.set(selected.run.id, [...getManualPoles(selected, "poles"), feature]);
        updateLayerCount(selected, "poles");
      } else {
        await api(runPath(selected.run.id) + "/poles", "POST", {id, lon, lat, pole_class});
        if (result !== selected) return;
        await loadLayer();
      }
      $("module-layer-show").checked = true;
      plot();
      $("manual-pole-dialog").close();
      $("module-status").textContent = selected.run.temporary ?
        "Pole added in this tab. Download GeoJSON to keep it." : "Approved pole added.";
    } finally {
      submit.disabled = false;
    }
  });

  function focusLayer() {
    if (overlay?.getBounds().isValid() && context?.viewer.map.hasLayer(overlay)) {
      context.viewer.map.fitBounds(overlay.getBounds(), {
        paddingTopLeft: [30, 30], paddingBottomRight: [155, 30], maxZoom: 18
      });
    }
  }

  async function inspect(feature) {
    clearDetail();
    const selected = result, inspector = $("module-feature");
    inspector.hidden = false;
    const p = feature.properties;
    const form = node("form");
    const state = node("select");
    state.setAttribute("aria-label", "Feature review state");
    state.append(...["pending", "approved", "rejected"].map(item => option(item, item)));
    state.value = p.review_state;
    const feedback = node("p");
    feedback.setAttribute("role", "status");
    const heading = node("div");
    heading.className = "module-feature-heading";
    heading.append(node("h4", (labels[p.pole_class]?.[0] || "Feature") + " | " + p.source_id));
    if (selected.run.module_id === "poles-detection" && p.layer === "poles") {
      heading.append(button("Add Pole", openManualPole));
    }
    inspector.append(heading, form, feedback, button("Close details", clearDetail));
    const stats = [];
    for (const [key, title] of Object.entries({
      mean_detection_confidence: "Mean detection confidence", support_frame_count: "Supporting photos",
      distance_to_path_m: "Distance to route (m)", road_side: "Road side", mean_ray_distance_m: "Mean ray residual (m)",
      pair_angular_separation_deg: "Pair separation (degrees)", gps_accuracy_mean_m: "Mean reported GPS accuracy (m)"
    })) {
      if (p[key] !== undefined && p[key] !== null) stats.push(title + " " + p[key]);
    }
    if (p.origin === "manual") inspector.append(node("p", "Manually added pole"));
    if (stats.length) inspector.append(node("p", stats.join(" | ")));
    form.append(state);
    const point = feature.geometry.type === "Point";
    const inputs = {};
    if (point) {
      const [lon, lat] = feature.geometry.coordinates;
      const coordinates = node("div");
      coordinates.className = "pole-coordinates";
      for (const [axis, value, bounds, description] of [
        ["X", lon, 180, "Longitude in degrees"], ["Y", lat, 90, "Latitude in degrees"]
      ]) {
        const label = node("label", axis), field = node("input");
        label.title = description;
        field.type = "number";
        field.min = -bounds;
        field.max = bounds;
        field.step = "any";
        field.value = value;
        field.required = true;
        inputs[axis] = field;
        label.append(field);
        coordinates.append(label);
      }
      form.append(coordinates);
      if (p.origin !== "manual" && p.original_geometry?.coordinates) inspector.append(node("p", "Raw estimate " +
        p.original_geometry.coordinates.map(value => value.toFixed(7)).join(", ")));
      handle = L.marker([lat, lon], {pane: "module-edit", draggable: true, autoPan: true, zIndexOffset: 1000,
        icon: L.divIcon({className: "edit-handle", iconSize: [30, 30], iconAnchor: [15, 15],
          html: '<span aria-hidden="true">+</span>'}), title: "Drag to correct the pole location"}).addTo(context.viewer.map);
      handle.on("drag", () => {
        const location = handle.getLatLng().wrap();
        inputs.Y.value = location.lat.toFixed(7);
        inputs.X.value = location.lng.toFixed(7);
      });
      for (const field of Object.values(inputs)) field.onchange = () => {
        if (form.checkValidity()) handle.setLatLng([Number(inputs.Y.value), Number(inputs.X.value)]);
      };
    }
    const save = node("button", selected.run.temporary ? "Keep review in this tab" : "Save review");
    const submit = async reset => {
      save.disabled = true;
      try {
        const change = {state: state.value, reset};
        if (point && !reset) {
          change.lon = Number(inputs.X.value);
          change.lat = Number(inputs.Y.value);
        }
        if (selected.run.temporary) {
          const geometry = change.reset ? feature.properties.estimated_geometry :
            point ? {type: "Point", coordinates: [change.lon, change.lat]} : feature.geometry;
          const reviewed = {...feature, geometry, properties: {...feature.properties,
            review_state: change.state, updated: new Date().toISOString()}};
          temporaryReviews.set(feature.id, reviewed);
          selected.features = selected.features.map(item => item.id === feature.id ? reviewed : item);
          clearDetail();
          plot();
          $("module-status").textContent = "Review updated in this tab. Download GeoJSON to save it.";
          return;
        }
        await api(root + "/module-features/" + feature.id, "PATCH", change);
        if (selected === result) {
          await loadLayer();
          $("module-status").textContent = "Review saved.";
        }
      } catch (error) {
        feedback.textContent = error.message;
      } finally {
        save.disabled = false;
      }
    };
    form.append(save);
    if (point) form.append(button("Reset location", () => submit(true)));
    form.onsubmit = event => { event.preventDefault(); submit(false); };
    const evidence = selected.run.temporary ? feature.evidence :
      await api(root + "/module-features/" + feature.id + "/evidence");
    if (!feedback.isConnected || !evidence.length) return;
    const gallery = node("div");
    gallery.className = "module-evidence";
    for (const obs of evidence) {
      if (!obs.url) continue;
      const figure = node("figure"), image = node("img"), frame = node("div"), box = node("span");
      image.src = obs.url;
      image.loading = "lazy";
      image.alt = "Source photo " + (obs.sequence + 1);
      frame.className = "module-evidence-frame";
      box.className = "module-bounding-box";
      const [x1, y1, x2, y2] = obs.bbox;
      Object.assign(box.style, {left: x1 * 100 + "%", top: y1 * 100 + "%",
        width: (x2 - x1) * 100 + "%", height: (y2 - y1) * 100 + "%"});
      frame.append(image, box);
      figure.append(frame, node("figcaption", image.alt));
      const index = context.viewer.points.findIndex(photo => photo.properties.frame_index === obs.sequence);
      const navigate = result.run.source_job === context.job && index >= 0;
      figure.append(navigate ? button("Go to survey photo", () => context.viewer.showPhoto(index, true)) :
        link("Download source photo", obs.url));
      gallery.append(figure);
    }
    inspector.append(node("h4", "Source photo evidence"), gallery);
  }

  $("module-layer").onchange = status(() => loadLayer());
  $("module-approved-export").onchange = exportLinks;
  $("module-more").onclick = status(() => loadLayer(true));
  for (const id of ["module-layer-show", "module-class", "module-review", "module-confidence"]) {
    $(id).onchange = () => {
      clearDetail();
      plot();
      if (id === "module-layer-show" && result?.run.temporary) focusLayer();
    };
  }
  $("module-rays").onchange = status(async () => {
    rays?.remove();
    if (!$("module-rays").checked || !result) return;
    const selected = result;
    const item = selected.artifacts.find(file => file.path === "pole_rays.geojson");
    if (item.bytes > 8 * 1024 * 1024) {
      $("module-rays").checked = false;
      throw Error("This ray layer is too large for the map. Download it from Execution files.");
    }
    const layer = await api(runPath(selected.run.id) + "/artifacts/pole_rays.geojson");
    if (result === selected && $("module-rays").checked) {
      rays = L.geoJSON(layer, {style: {color: "#7139a1", weight: 1, interactive: false}}).addTo(context.viewer.map);
    }
  });
  return {attach, detach};
})();
