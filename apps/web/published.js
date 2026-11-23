"use strict";
(async () => {
  async function load(path) {
    const response = await fetch(path);
    if (!response.ok) throw Error("This survey map is unavailable.");
    return response.json();
  }
  try {
    const publication = "/api/v2/published" + location.pathname.replace(/\/$/, "");
    const survey = await load(publication);
    const file = name => publication + "/files/" + survey.job + "/" + name;
    const empty = {type: "FeatureCollection", features: []};
    const routeOnly = survey.layers === "route";
    const [points, route] = await Promise.all([
      routeOnly ? empty : load(file("points.geojson")),
      survey.layers === "points" ? empty : load(file("route.geojson"))
    ]);
    document.querySelector(".viewer").classList.toggle("route-only", routeOnly);
    document.querySelector("figure").hidden = routeOnly;
    document.getElementById("title").textContent = survey.label;
    document.title = survey.label + " | SiteVerum";
    document.getElementById("results").hidden = false;
    const viewer = new SurveyViewer({defaultBasemap: survey.default_basemap});
    viewer.load(points, route, file);
    const overlays = {};
    for (const item of survey.module_layers || []) {
      const key = item.layer === "poles" ? "Electrical Poles" : item.layer;
      const data = await load(publication + "/layers/" + item.run + "/" + encodeURIComponent(item.layer));
      overlays[key] ??= L.layerGroup();
      L.geoJSON(data, {
        pointToLayer: (_feature, position) => L.circleMarker(position, {
          radius: 7, color: "#55327f", fillColor: "#7139a1", fillOpacity: .85
        })
      }).addTo(overlays[key]);
    }
    if (Object.keys(overlays).length) L.control.layers(null, overlays, {collapsed: false}).addTo(viewer.map);
  } catch (error) {
    document.getElementById("message").textContent = error.message;
  }
})();
