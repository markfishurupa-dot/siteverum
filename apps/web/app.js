"use strict";
const $ = id => document.getElementById(id);
let survey, current, shownRun, viewer;
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
async function catalog() {
  const items = await api(root + "/surveys");
  $("catalog").replaceChildren(...items.map(item => {
    const li = document.createElement("li"), button = document.createElement("button");
    button.textContent = item.label + (item.published ? " В· Published locally" : "");
    button.setAttribute("aria-current", item.id === survey);
    button.onclick = action(async () => select(item.id));
    li.append(button);
    return li;
  }));
}
async function select(id) {
  survey = id;
  shownRun = null;
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
  $("title").textContent = row.label;
  const kinds = row.sources.map(x => x.kind);
  const pairReady = kinds.includes("zip") || (kinds.includes("video") && kinds.includes("track"));
  $("assets").textContent = row.sources.map(x => x.filename).join(", ") ||
    "No source files uploaded.";
  $("message").textContent = pairReady ? "Sources staged" :
    kinds.includes("video") ? "Waiting for matching GPS log" :
    kinds.includes("track") ? "Waiting for matching video" : "Choose a ZIP or matching files";
  const validation = row.validation;
  $("validation").replaceChildren(...[
    ...(validation?.can_process ? ["Validated"] : []),
    ...(validation?.errors || []), ...(validation?.warnings || [])
  ].map(message => {
    const li = document.createElement("li"); li.textContent = message; return li;
  }));
  const latest = row.jobs[0];
  const active = latest && ["queued","running"].includes(latest.state);
  $("start").disabled = !validation?.can_process || !!active;
  $("job").textContent = latest ? [latest.state, latest.progress + "%", latest.error].filter(Boolean).join(" В· ") : "";
  $("cancel").hidden = !active;
  $("published-link").hidden = !row.published;
  $("published-link").href = "/" + encodeURIComponent(row.slug);
  $("add-point-button").disabled = !!active || !validation?.can_process;
  $("publication").textContent = row.published ? "Unpublish locally" : "Publish locally";
  const ready = row.jobs.find(job => job.state === "completed");
  if (ready && ready.id !== shownRun) await showRun(ready.id, requested);
}
function upload(file) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", base() + "/assets/" + encodeURIComponent(file.name));
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
  $("upload-progress").hidden = false;
  try { for (const file of files) await upload(file); }
  finally { $("upload-progress").hidden = true; await refresh(); }
});
$("validate").onclick = action(async () => {
  $("message").textContent = "Validating and decoding videoвЂ¦";
  await api(base() + "/validate", "POST");
  await refresh();
});
$("process").onsubmit = action(async () => {
  await api(base() + "/process","POST", {
    sampling:$("sampling").value, interval:Number($("interval").value),
    max_accuracy:$("accuracy").value === "" ? null : Number($("accuracy").value),
    rotation: Number($("rotation").value),
    manual_points: current.jobs.find(job => job.state === "completed")?.settings.manual_points || []
  });
  await refresh();
});
$("cancel").onclick = action(async () => { await api(root + "/jobs/" + current.jobs[0].id + "/cancel","POST"); await refresh(); });
$("delete").onclick = action(async () => {
  if (!confirm("Delete this survey from the catalog?")) return;
  await api(base(),"DELETE");
  survey = null;
  $("survey").hidden = true;
  $("message").textContent = "Survey deleted.";
  await catalog();
});
$("publication").onclick = action(async () => {
  await api(base() + "/publication/" + (current.published ? "unpublish" : "publish"),"POST");
  await refresh(); await catalog();
});
const artifact = (job, name) => base() + "/runs/" + job + "/" + name;
async function showRun(job, requested) {
  const [data, route] = await Promise.all([api(artifact(job,"points.geojson")), api(artifact(job,"route.geojson"))]);
  if (requested !== survey) return;
  shownRun = job;
  $("results").hidden = false;
  if (!viewer) viewer = new SurveyViewer(location => {
    if (!$("add-point").closest("details").open) return;
    $("point-lat").value = location.lat.toFixed(7);
    $("point-lon").value = L.Util.wrapNum(location.lng, [-180, 180], true).toFixed(7);
  });
  viewer.load(data, route, name => artifact(job, name));
  const settings = current.jobs.find(item => item.id === job)?.settings;
  if (settings) {
    $("sampling").value = settings.sampling;
    $("interval").value = settings.interval;
    $("accuracy").value = settings.max_accuracy ?? "";
    $("rotation").value = settings.rotation || 0;
  }
  $("downloads").replaceChildren(...["survey.zip","points.gpkg","points.geojson","points.csv","route.geojson","qa_report.json"].map(name => {
    const a = document.createElement("a"); a.textContent = name; a.href = artifact(job,name); a.download = name; return a;
  }));
}
$("add-point").onsubmit = action(async () => {
  const settings = current.jobs.find(job => job.id === shownRun).settings;
  const point = {
    lat: Number($("point-lat").value),
    lon: Number($("point-lon").value),
    video_elapsed_ms: Math.round(Number($("point-time").value) * 1000),
    bearing: $("point-bearing").value === "" ? null : Number($("point-bearing").value)
  };
  await api(base() + "/process", "POST", {
    ...settings, manual_points: [...(settings.manual_points || []), point]
  });
  $("add-point").reset();
  await refresh();
});
setInterval(() => {
  if (current?.jobs.some(job => ["queued","running"].includes(job.state))) action(refresh)();
},1500);
action(catalog)();
