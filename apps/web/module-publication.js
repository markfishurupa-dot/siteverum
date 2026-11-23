
"use strict";

window.publicationControls = (() => {
  let surveyId, selectedPolicy, selectedDerivative, preferred = new Set(), versionList = [], runs = [], source;
  const select = (value, label) => {
    const item = document.createElement("option");
    item.value = value;
    item.textContent = label;
    return item;
  };

  function render() {
    const policy = $("privacy-module"), derivative = $("privacy-derivative"), layers = $("publish-module-layers");
    const selected = selectedPolicy || "";
    const redactors = [...new Map(versionList.filter(version => version.manifest.stage === "pre_publication")
      .map(version => [version.module_id, version.manifest.name]))];
    policy.replaceChildren(select("", "No redaction required"), ...redactors.map(([id, name]) => select(id, name)));
    if (selected && !redactors.some(([id]) => id === selected)) policy.append(select(selected, selected));
    policy.value = selected;
    const activePolicy = current?.privacy_module;
    const previousDerivative = selectedDerivative;
    const compatible = runs.filter(run => run.state === "completed" && run.source_job === source);
    const privacyRuns = compatible.filter(run => run.module_id === activePolicy && run.stage === "pre_publication");
    derivative.replaceChildren(select("", "Latest completed privacy run"),
      ...privacyRuns.map(run => select(run.id, new Date(run.created).toLocaleString())));
    if (privacyRuns.some(run => run.id === previousDerivative)) derivative.value = previousDerivative;
    $("privacy-derivative-label").hidden = !activePolicy;
    const vectorOptions = [];
    for (const run of compatible.filter(run => run.stage === "post_processing" && !run.temporary)) {
      for (const item of run.summary.layers || []) {
        const name = versionList.find(module => module.module_id === run.module_id && module.version === run.version)?.manifest.name || run.module_id;
        const option = select(run.id + "/" + item.id, name + " | " + item.id + " | " + new Date(run.created).toLocaleString());
        option.selected = preferred.has(option.value);
        vectorOptions.push(option);
      }
    }
    layers.replaceChildren(...vectorOptions);
    $("publish-module-layers-label").hidden = !vectorOptions.length;
  }

  function surveyChanged(data, job) {
    $("module-publication-settings").hidden = !job;
    if (surveyId !== data.id || source !== job) {
      surveyId = data.id;
      source = job;
      runs = [];
      preferred = new Set((data.module_layers || []).map(item => item.run + "/" + item.layer));
      selectedPolicy = data.privacy_module;
      selectedDerivative = data.published_derivative_run;
      render();
    }
  }

  $("privacy-module").onchange = () => { selectedPolicy = $("privacy-module").value; };
  $("privacy-derivative").onchange = () => { selectedDerivative = $("privacy-derivative").value; };
  $("publish-module-layers").onchange = () => {
    preferred = new Set([...$("publish-module-layers").selectedOptions].map(item => item.value));
  };
  $("save-privacy").onclick = action(async () => {
    const required_module = $("privacy-module").value || null;
    const requested = survey;
    await api(base() + "/privacy", "PUT", {required_module});
    if (survey !== requested) return;
    await refresh();
    render();
    $("message").textContent = required_module ? "Photo redaction required for publication." : "Privacy policy disabled.";
  });
  return {
    surveyChanged,
    modules(versions, list) {
      versionList = versions;
      runs = list;
      if (current) render();
    },
    settings() {
      const options = {};
      if (!$("publish-module-layers-label").hidden) {
        options.module_layers = [...$("publish-module-layers").selectedOptions].map(item => {
          const [run, layer] = item.value.split("/");
          return {run, layer, approved_only: true};
        });
      }
      if (!$("privacy-derivative-label").hidden && $("privacy-derivative").value) {
        options.derivative_run = $("privacy-derivative").value;
      }
      return options;
    }
  };
})();
