"use strict";
(async () => {
  try {
    const load = async name => {
      const response = await fetch(name);
      if (!response.ok) throw new Error("The sample could not be loaded.");
      return response.json();
    };
    const [points, route] = await Promise.all([load("data/points.geojson"), load("data/route.geojson")]);
    document.getElementById("results").hidden = false;
    new SurveyViewer().load(points, route, name => new URL(name, document.baseURI).href);
  } catch (error) {
    document.getElementById("message").textContent = error.message;
  }
})();
