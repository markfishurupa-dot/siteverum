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
    const [points, route] = await Promise.all([load(file("points.geojson")), load(file("route.geojson"))]);
    document.getElementById("title").textContent = survey.label;
    document.title = survey.label + " | StreetView";
    document.getElementById("results").hidden = false;
    new SurveyViewer().load(points, route, file);
  } catch (error) {
    document.getElementById("message").textContent = error.message;
  }
})();
