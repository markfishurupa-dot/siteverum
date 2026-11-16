"use strict";

class SurveyViewer {
  constructor(onMapClick = () => {}) {
    this.map = L.map("map", {maxZoom: 21}).setView([0, 0], 2);
    this.route = L.layerGroup().addTo(this.map);
    this.markers = L.layerGroup().addTo(this.map);
    const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxNativeZoom: 19,
      maxZoom: 21,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    });
    L.control.layers({"Survey only": L.layerGroup().addTo(this.map), "OpenStreetMap": osm}, {}, {collapsed: false}).addTo(this.map);
    this.points = [];
    this.map.on("zoomend moveend", () => this.drawMarkers());
    this.map.on("click", event => onMapClick(event.latlng));
    document.getElementById("previous").onclick = () => this.showPhoto(this.index - 1, true);
    document.getElementById("next").onclick = () => this.showPhoto(this.index + 1, true);
    document.addEventListener("keydown", event => {
      if (document.getElementById("results").hidden || event.defaultPrevented ||
          event.target.closest("input, select, textarea, .leaflet-container")) return;
      if (event.key === "ArrowRight") this.showPhoto(this.index + 1, true);
      if (event.key === "ArrowLeft") this.showPhoto(this.index - 1, true);
    });
  }

  load(points, route, file) {
    this.points = points.features;
    this.file = file;
    this.route.clearLayers();
    const line = L.geoJSON(route, {style: {color: "#287691", weight: 4}}).addTo(this.route);
    this.map.invalidateSize();
    if (!this.points.length) {
      this.drawMarkers();
      if (line.getBounds().isValid()) this.map.fitBounds(line.getBounds(), {padding: [25, 25], maxZoom: 19});
      return;
    }
    const locations = this.points.map(feature => this.location(feature));
    this.map.fitBounds(L.latLngBounds(locations), {padding: [25, 25], maxZoom: 19});
    this.showPhoto(0, false);
  }

  location(feature) {
    const [longitude, latitude] = feature.geometry.coordinates;
    return L.latLng(latitude, longitude);
  }

  drawMarkers() {
    this.markers.clearLayers();
    const arrows = this.map.getZoom() >= 19;
    const bounds = this.map.getBounds();
    this.points.forEach((feature, i) => {
      const location = this.location(feature);
      if (arrows && !bounds.contains(location)) return;
      const color = i === this.index ? "#ffd400" : "#d7191c";
      const bearing = feature.properties.bearing;
      const directional = arrows && bearing !== null && bearing !== "" && Number.isFinite(Number(bearing));
      const icon = L.divIcon({
        className: directional ? "photo-marker arrow-marker" : "photo-marker point-marker",
        html: directional
          ? '<span style="background:' + color + ';transform:rotate(' + Number(bearing) + 'deg)"></span>'
          : '<span style="background:' + color + '"></span>',
        iconSize: directional ? [28, 28] : [18, 18]
      });
      L.marker(location, {icon, title: "Photo " + (i + 1), keyboard: true, bubblingMouseEvents: false})
        .addTo(this.markers).on("click", () => this.showPhoto(i, false));
    });
  }

  showPhoto(index, pan) {
    const feature = this.points[index];
    if (!feature) return;
    this.index = index;
    const properties = feature.properties;
    const url = this.file(properties.image_path);
    document.getElementById("photo").src = url;
    document.getElementById("download-photo").href = url;
    document.getElementById("caption").textContent =
      "Photo " + (index + 1) + " of " + this.points.length + " | " + properties.actual_pts.toFixed(3) + " s" +
      (properties.recording_number ? " | Recording " + properties.recording_number : "") +
      (properties.manual ? " | Added manually" : "");
    document.getElementById("previous").disabled = index === 0;
    document.getElementById("next").disabled = index === this.points.length - 1;
    if (pan) this.map.panTo(this.location(feature));
    this.drawMarkers();
  }
}
