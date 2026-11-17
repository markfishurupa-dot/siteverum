"use strict";
(async () => {
  try {
    const load = async name => {
      const response = await fetch(name);
      if (!response.ok) throw new Error("The sample could not be loaded.");
      return response.json();
    };
    const [points, route, dataset] = await Promise.all([
      load("data/points.geojson"), load("data/route.geojson"), load("data/dataset.json")
    ]);
    document.getElementById("dataset-notice").textContent = dataset.description +
      " Video processing requires a local installation. OpenStreetMap requests tiles from its servers.";
    document.getElementById("results").hidden = false;
    new SurveyViewer({defaultBasemap: dataset.defaultBasemap}).load(points, route, name => new URL(name, document.baseURI).href);
  } catch (error) {
    document.getElementById("message").textContent = error.message;
  }
})();
