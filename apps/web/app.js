"use strict";
const $ = id => document.getElementById(id);
let survey, current, shownRun, viewer, selectedRecording = "primary";
let validationPending;
const accuracy = () => $("accuracy").value === "" ? null : Number($("accuracy").value);
const root = "/api/v2";
const base = () => root + "/surveys/" + survey;

async function api(path, method = "GET", data) {
  const response = await fetch(path, {method, headers: {"X-StreetView-Request":"1", "Content-Type":"application/json"},
    body: data === undefined ? undefined : JSON.stringify(data)});
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw Error(typeof error.detail === "string" ? error.detail : "Request failed (" + response.status + ")");
  }
  return response.json();
}
function action(fn) {
  return async event => {
    event?.preventDefault();
    try { await fn(); }
    catch (error) { $("message").textContent = error.message; }
  };
}
function validationMessage(message) {
  const labels = {
    GPS_LOW_ACCURACY: "Low GPS accuracy",
    GPS_POSITION_JUMP: "Possible GPS jump",
    CLOCK_OFFSET_WARNING: "Possible clock mismatch",
    TRACK_ENDS_EARLY: "GPS track ends early",
    TRACK_BEYOND_VIDEO_DURATION: "GPS track runs beyond the video",
    LOG_ELAPSED_NOT_STRICTLY_INCREASING: "GPS timestamps must be in increasing order",
    NON_ANDROID_FILENAME: "Nonstandard filename",
    ZIP_VIDEO_LOG_STEMS_DIFFER: "The video and GPS log in the ZIP must have matching names",
    VIDEO_LOG_STEMS_DIFFER: "The video and GPS log must have matching names",
    PAIR_INCOMPLETE: "Recording incomplete",
    PAIR_AMBIGUOUS: "Recording is ambiguous"
  };
  const prefix = message.match(/^Recording [0-9]+: /)?.[0] || "";
  const text = message.slice(prefix.length);
  const match = text.match(/^([A-Z][A-Z0-9_]+)(?::\s*(.*))?$/);
  if (!match) return message;
  const words = match[1].toLowerCase().replaceAll("_", " ");
  const label = labels[match[1]] || words[0].toUpperCase() + words.slice(1);
  return prefix + label + (match[2] ? ": " + match[2] : "");
}
function updatePublicationDot(button, state) {
  const indicator = button.querySelector(".publication-dot");
  indicator.hidden = state === "unpublished";
  indicator.dataset.state = state;
  const details = {current: "Published", outdated: "Changes pending publication"};
  if (details[state]) {
    indicator.title = details[state];
    indicator.setAttribute("aria-label", details[state]);
  } else {
    indicator.removeAttribute("title");
    indicator.removeAttribute("aria-label");
  }
}
async function catalog() {
  const items = await api(root + "/surveys");
  $("catalog").replaceChildren(...items.map(item => {
    const li = document.createElement("li"), button = document.createElement("button");
    const name = document.createElement("span"), indicator = document.createElement("span");
    name.className = "survey-name";
    name.textContent = item.label;
    indicator.className = "publication-dot";
    indicator.setAttribute("role", "img");
    button.append(name, indicator);
    button.dataset.survey = item.id;
    updatePublicationDot(button, item.publication_state);
    button.setAttribute("aria-current", item.id === survey);
    button.onclick = action(async () => select(item.id));
    li.append(button);
    return li;
  }));
}
async function select(id) {
  survey = id;
  shownRun = null;
  selectedRecording = "primary";
  if (viewer) viewer.map.closePopup();
  $("sampling").value = "gps_fix";
  $("interval").value = 1;
  $("accuracy").value = "";
  $("rotation").value = 0;
  $("survey").hidden = false;
  $("results").hidden = true;
  $("files").value = "";
  await refresh();
  await catalog();
}
async function refresh() {
  if (!survey) return;
  const requested = survey;
  const row = await api(base());
  if (requested !== survey) return;
  current = row;
  const catalogEntry = $("catalog").querySelector('[data-survey="' + requested + '"]');
  if (catalogEntry) updatePublicationDot(catalogEntry, row.publication_state);
  $("title").textContent = row.label;
  const recordings = new Map();
  for (const source of row.sources) {
    if (!recordings.has(source.recording)) recordings.set(source.recording, []);
    recordings.get(source.recording).push(source);
  }
  const selected = recordings.get(selectedRecording) || [];
  const kinds = selected.map(source => source.kind);
  const pairReady = kinds.includes("zip") || (kinds.includes("video") && kinds.includes("track"));
  const choices = [...recordings.keys()];
  if (!choices.includes(selectedRecording)) choices.push(selectedRecording);
  $("recording-select").replaceChildren(...choices.map((key, index) => {
    const option = document.createElement("option");
    option.value = key;
    const name = recordings.get(key)?.[0]?.filename;
    option.textContent = name ? "Recording " + (index + 1) + " | " + name : "New recording";
    return option;
  }));
  $("recording-select").value = selectedRecording;
  $("recording-select-label").hidden = choices.length < 2;
  $("recording-tools").hidden = !row.jobs.some(job => job.state === "completed") && choices.length < 2;
  $("assets").textContent = selected.map(source => source.filename).join(", ") || "No source files uploaded.";
  $("message").textContent = pairReady ? "Sources staged" :
    kinds.includes("video") ? "Waiting for matching GPS log" :
    kinds.includes("track") ? "Waiting for matching video" : "Choose a ZIP or matching files";
  const validation = row.validation;
  $("validation").replaceChildren(...[
    ...(validation?.can_process ? ["Validated"] : []),
    ...(validation?.errors || []), ...(validation?.warnings || [])
  ].map(message => {
    const li = document.createElement("li"); li.textContent = validationMessage(message); return li;
  }));
  const latest = row.jobs[0];
  const active = latest && ["queued","running"].includes(latest.state);
  const ready = row.jobs.find(job => job.state === "completed");
  const included = selectedRecording === "primary" ||
    ready?.metadata?.recordings?.some(item => item.recording === selectedRecording);
  $("upload").hidden = !!ready && !!included;
  $("add-recording").disabled = !!active || !recordings.has(selectedRecording);
  $("discard-recording").hidden = selectedRecording === "primary" || !!included;
  $("discard-recording").disabled = !!active;
  const stateLabels = {
    queued: latest?.is_edit ? "Point edit queued" : "Processing queued",
    running: latest?.is_edit ? "Saving point edit" : "Processing survey",
    completed: latest?.is_edit ? "Point edit saved" : "Processing complete",
    failed: latest?.is_edit ? "Point edit failed" : "Processing failed",
    cancelled: "Processing cancelled"
  };
  $("start").hidden = !!active;
  $("start").disabled = !validation?.can_process || validationPending === requested;
  $("cancel").hidden = !active;
  $("processing-progress").hidden = !active;
  $("job-progress").value = latest?.progress || 0;
  $("job-percent").textContent = (latest?.progress || 0) + "%";
  $("job").hidden = !latest;
  $("job").textContent = latest ? [stateLabels[latest.state], latest.error].filter(Boolean).join(": ") : "";
  $("delete").disabled = !!active;
  $("layers-control").hidden = !ready;
  $("basemap-control").hidden = !ready;
  $("availability-control").hidden = !ready;
  $("publication").hidden = !ready;
  $("publication").disabled = !row.published && !row.can_publish;
  $("save-publication").disabled = !row.can_publish;
  $("save-publication").title = row.can_publish ? "" : "Process the current survey sources before publishing";
  $("save-publication").textContent = row.publication_state === "outdated" ? "Republish map" : "Update published map";
  $("published-link").hidden = !row.published;
  $("published-link").href = "/" + encodeURIComponent(row.slug);
  $("save-publication").hidden = !row.published;
  if ($("publish-layers").dataset.survey !== requested) {
    $("publish-layers").value = row.map_layers;
    $("publish-basemap").value = row.default_basemap;
    $("publish-public").checked = row.publicly_available;
    $("publish-layers").dataset.survey = requested;
  }
  $("publication").textContent = row.published ? "Unpublish locally" : "Publish locally";
  if (ready && ready.id !== shownRun) await showRun(ready.id, requested, ready.is_edit);
  updateValidationActions();
}
function upload(file, target, recording) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", target + "/assets/" + encodeURIComponent(file.name) +
      (recording === "primary" ? "" : "?recording=" + recording));
    xhr.setRequestHeader("X-StreetView-Request","1");
    xhr.upload.onprogress = e => { if (e.lengthComputable) $("upload-progress").value = 100 * e.loaded / e.total; };
    xhr.onload = () => xhr.status < 300 ? resolve() : reject(Error(JSON.parse(xhr.responseText || "{}").detail || "Upload failed"));
    xhr.onerror = () => reject(Error("Upload connection failed"));
    xhr.send(file);
  });
}
$("create").onsubmit = action(async () => {
  const made = await api(root + "/surveys", "POST", {label:$("label").value});
  $("label").value = "";
  await select(made.id);
});
$("upload").onsubmit = action(async () => {
  const files = Array.from($("files").files);
  const target = base(), recording = selectedRecording;
  $("upload-progress").hidden = false;
  try { for (const file of files) await upload(file, target, recording); }
  finally { $("upload-progress").hidden = true; await refresh(); }
});
$("add-recording").onclick = action(async () => {
  selectedRecording = crypto.randomUUID();
  $("files").value = "";
  await refresh();
  $("files").focus();
});
$("recording-select").onchange = action(async () => {
  selectedRecording = $("recording-select").value;
  $("files").value = "";
  await refresh();
});
$("discard-recording").onclick = action(async () => {
  if (current.sources.some(source => source.recording === selectedRecording))
    await api(base() + "/recordings/" + selectedRecording, "DELETE");
  selectedRecording = "primary";
  await refresh();
});
function updateValidationActions() {
  const busy = validationPending === survey;
  const ready = current?.validation?.can_process;
  const sameAccuracy = (current?.validation?.accuracy_limit ?? null) === accuracy();
  $("validate").hidden = !!ready && sameAccuracy && !busy;
  const active = current?.jobs.some(job => ["queued", "running"].includes(job.state));
  $("validate").disabled = busy || !current?.sources.length || active;
  for (const id of ["sampling", "interval", "accuracy", "rotation"]) $(id).disabled = busy || !!active;
  $("validate").textContent = ready ? "Refresh validation" : "Validate sources";
  $("validation-report").hidden = busy || !current?.validation;
  $("validation-report").href = base() + "/validation-report";
  $("validation-busy").hidden = !busy;
  $("start").disabled = busy || !ready;
}
$("accuracy").oninput = updateValidationActions;
$("validate").onclick = action(async () => {
  if (!$("process").reportValidity()) return;
  const target = survey;
  validationPending = target;
  updateValidationActions();
  try {
    await api(base() + "/validate", "POST", {max_accuracy: accuracy()});
  } finally {
    if (validationPending === target) validationPending = null;
    if (survey === target) await refresh();
  }
});
$("process").onsubmit = action(async () => {
  await api(base() + "/process","POST", {
    sampling:$("sampling").value, interval:Number($("interval").value),
    max_accuracy:accuracy(),
    rotation: Number($("rotation").value),
    manual_points: current.jobs.find(job => job.state === "completed")?.settings.manual_points || []
  });
  await refresh();
});
$("cancel").onclick = action(async () => { await api(root + "/jobs/" + current.jobs[0].id + "/cancel","POST"); await refresh(); });
$("upload-info").onclick = () => $("upload-help").showModal();
let deleteTarget;
$("delete").onclick = () => {
  deleteTarget = survey;
  $("delete-confirmation-error").hidden = true;
  $("delete-confirmation-text").textContent =
    'Delete "' + current.label + '" from the catalog? Any locally published map for this survey will become unavailable.';
  $("delete-confirmation").showModal();
};
$("confirm-delete").onclick = async () => {
  const button = $("confirm-delete");
  button.disabled = true;
  try {
    await api(root + "/surveys/" + deleteTarget, "DELETE");
    $("delete-confirmation").close();
    if (survey === deleteTarget) {
      survey = null;
      current = null;
      $("survey").hidden = true;
      $("message").textContent = "Survey deleted.";
    }
    await catalog();
  } catch (error) {
    $("delete-confirmation-error").textContent = error.message;
    $("delete-confirmation-error").hidden = false;
  } finally {
    button.disabled = false;
  }
};
function publicationSettings() {
  return {
    layers: $("publish-layers").value,
    default_basemap: $("publish-basemap").value,
    publicly_available: $("publish-public").checked
  };
}
$("publication").onclick = action(async () => {
  await api(base() + "/publication/" + (current.published ? "unpublish" : "publish"), "POST",
    current.published ? undefined : publicationSettings());
  await refresh(); await catalog();
});
$("save-publication").onclick = action(async () => {
  await api(base() + "/publication/publish", "POST", publicationSettings());
  await refresh(); await catalog();
  $("message").textContent = "Published map updated.";
});
$("about-open").onclick = () => $("about").showModal();
action(async () => {
  const info = await api(root + "/version");
  $("about-open").textContent = "Version " + info.version;
  $("about-version").textContent = "Private alpha | " + info.version;
})();
const artifact = (job, name) => base() + "/runs/" + job + "/" + name;
async function showRun(job, requested, isEdit) {
  const [data, route] = await Promise.all([api(artifact(job,"points.geojson")), api(artifact(job,"route.geojson"))]);
  if (requested !== survey) return;
  const firstView = !shownRun;
  shownRun = job;
  $("results").hidden = false;
  if (!viewer) viewer = new SurveyViewer({
    telemetry: sequence => api(artifact(shownRun, "points/" + sequence)),
    canEdit: () => !current.jobs.some(job => ["queued", "running"].includes(job.state)),
    saveEdit: async (sequence, coordinates) => {
      await api(artifact(shownRun, "points/" + sequence), "PATCH", coordinates);
      await refresh();
    },
    deletePoint: async sequence => {
      await api(artifact(shownRun, "points/" + sequence), "DELETE");
      await refresh();
    }
  });
  viewer.load(data, route, name => artifact(job, name), isEdit && viewer.survey === requested);
  viewer.survey = requested;
  const settings = current.jobs.find(item => item.id === job)?.settings;
  if (settings && firstView) {
    $("sampling").value = settings.sampling;
    $("interval").value = settings.interval;
    $("accuracy").value = settings.max_accuracy ?? "";
    $("rotation").value = settings.rotation || 0;
  }
  $("downloads").replaceChildren(...["survey.zip","points.gpkg","points.geojson","points.csv","route.geojson","qa_report.json"].map(name => {
    const a = document.createElement("a"); a.textContent = name; a.href = artifact(job,name); a.download = name; return a;
  }));
}
setInterval(() => {
  if (current?.jobs.some(job => ["queued","running"].includes(job.state))) action(refresh)();
},1500);
action(catalog)();
