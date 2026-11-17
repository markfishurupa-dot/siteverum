"use strict";

class SurveyViewer {
  constructor(options = {}) {
    this.options = options;
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

    document.getElementById("previous").onclick = () => this.showPhoto(this.index - 1, true);
    document.getElementById("next").onclick = () => this.showPhoto(this.index + 1, true);
    document.addEventListener("keydown", event => {
      if (document.getElementById("results").hidden || event.defaultPrevented ||
          event.target.closest("input, select, textarea, .leaflet-container")) return;
      if (event.key === "ArrowRight") this.showPhoto(this.index + 1, true);
      if (event.key === "ArrowLeft") this.showPhoto(this.index - 1, true);
    });
  }

  load(points, route, file, preserveView = false) {
    this.map.closePopup();
    const previousIndex = this.index;
    this.points = points.features;
    this.file = file;
    this.route.clearLayers();
    const line = L.geoJSON(route, {style: {color: "#287691", weight: 4}}).addTo(this.route);
    this.map.invalidateSize();
    if (!this.points.length) {
      this.index = 0;
      document.getElementById("photo").removeAttribute("src");
      document.getElementById("download-photo").hidden = true;
      document.getElementById("caption").textContent = "No photo points";
      document.getElementById("previous").disabled = true;
      document.getElementById("next").disabled = true;
      this.drawMarkers();
      if (line.getBounds().isValid()) this.map.fitBounds(line.getBounds(), {padding: [25, 25], maxZoom: 19});
      return;
    }
    const locations = this.points.map(feature => this.location(feature));
    if (!preserveView)
      this.map.fitBounds(L.latLngBounds(locations), {padding: [25, 25], maxZoom: 19});
    this.showPhoto(preserveView ? Math.min(previousIndex ?? 0, this.points.length - 1) : 0, false);
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
        .addTo(this.markers).on("click", () => {
          this.showPhoto(i, false);
          this.openDetails(i);
        });
    });
  }

  showPhoto(index, pan) {
    const feature = this.points[index];
    if (!feature) return;
    if (index !== this.index) this.map.closePopup();
    this.index = index;
    const properties = feature.properties;
    const url = this.file(properties.image_path);
    document.getElementById("photo").src = url;
    document.getElementById("download-photo").href = url;
    document.getElementById("download-photo").hidden = false;
    document.getElementById("caption").textContent =
      "Photo " + (index + 1) + " of " + this.points.length + " | " + properties.actual_pts.toFixed(3) + " s" +
      (properties.recording_number ? " | Recording " + properties.recording_number : "") +
      (properties.manual ? " | Added manually" : "");
    document.getElementById("previous").disabled = index === 0;
    document.getElementById("next").disabled = index === this.points.length - 1;
    if (pan) this.map.panTo(this.location(feature));
    this.drawMarkers();
  }

  openDetails(index) {
    this.map.closePopup();
    const feature = this.points[index];
    const properties = feature.properties;
    const [longitude, latitude] = feature.geometry.coordinates;
    const box = document.createElement("div");
    box.className = "point-popup";
    const heading = document.createElement("strong");
    heading.textContent = "Photo " + (index + 1);
    const fields = document.createElement("dl");
    const values = {};
    const addField = (label, value) => {
      const term = document.createElement("dt");
      term.textContent = label;
      const detail = document.createElement("dd");
      detail.textContent = value;
      fields.append(term, detail);
      values[label] = detail;
    };
    const measurement = (value, unit) => value == null || value === "" ? "Unavailable" : Number(value).toFixed(2) + " " + unit;
    addField("Latitude", latitude.toFixed(7));
    addField("Longitude", longitude.toFixed(7));
    addField("Altitude", measurement(properties.alt_m, "m"));
    addField("Speed", measurement(properties.speed_mps, "m/s"));
    addField("Bearing", measurement(properties.bearing, "deg"));
    addField("GPS accuracy", measurement(properties.accuracy_m, "m"));
    if (properties.original_coordinates) {
      const [originalLon, originalLat] = properties.original_coordinates;
      addField("Original GPS", originalLat.toFixed(7) + ", " + originalLon.toFixed(7));
    }
    box.append(heading, fields);
    const popup = L.popup({maxWidth: 285, closeOnClick: false})
      .setLatLng(this.location(feature)).setContent(box).openOn(this.map);

    if (this.options.telemetry && !Object.hasOwn(properties, "speed_mps")) {
      this.options.telemetry(properties.frame_index).then(telemetry => {
        values.Altitude.textContent = measurement(telemetry.alt_m, "m");
        values.Speed.textContent = measurement(telemetry.speed_mps, "m/s");
        popup.update();
      }).catch(() => {});
    }
    if (this.options.saveEdit && this.options.canEdit()) {
      const edit = document.createElement("button");
      edit.textContent = "Edit";
      edit.onclick = () => {
        edit.remove();
        this.editCoordinates(popup, box, feature);
      };
      box.append(edit);
      popup.update();
    }
  }

  editCoordinates(popup, box, feature) {
    box.querySelector("dl").hidden = true;
    popup.options.offset = L.point(0, -24);
    const form = document.createElement("form");
    form.className = "point-editor";
    const field = (text, value, min, max, required = true, parent = form) => {
      const label = document.createElement("label");
      label.textContent = text;
      const input = document.createElement("input");
      Object.assign(input, {type: "number", step: "any", min, max, required, value});
      label.append(input);
      parent.append(label);
      return input;
    };
    const [longitude, latitude] = feature.geometry.coordinates;
    const address = document.createElement("p");
    address.textContent = "Drag the handle or enter new coordinates.";
    form.append(address);
    const positions = document.createElement("div");
    positions.className = "point-editor-row";
    form.append(positions);
    const lat = field("New latitude", latitude, -90, 90, true, positions);
    const lon = field("New longitude", longitude, -180, 180, true, positions);
    const originalBearing = feature.properties.bearing;
    const bearing = field("Bearing (degrees)", originalBearing == null || originalBearing === "" ?
      "" : Number(originalBearing) % 360, 0, 360, false);
    const save = document.createElement("button");
    save.textContent = "Save changes";
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Delete point";
    remove.className = "destructive";
    const status = document.createElement("p");
    status.setAttribute("role", "status");
    const actions = document.createElement("div");
    actions.className = "point-editor-row";
    actions.append(save, remove);
    form.append(actions, status);
    box.append(form);
    L.DomEvent.disableClickPropagation(form);

    const handle = L.marker(this.location(feature), {
      draggable: true, autoPan: true, zIndexOffset: 1000,
      icon: L.divIcon({className: "edit-handle", iconSize: [30, 30], iconAnchor: [15, 15],
        html: '<span aria-hidden="true">+</span>'}),
      title: "Drag to correct the photo position"
    }).addTo(this.map);
    const preview = handle.getElement().querySelector("span");
    const updateBearing = () => {
      const hasBearing = bearing.value !== "" && bearing.checkValidity();
      preview.classList.toggle("edit-bearing", hasBearing);
      preview.textContent = hasBearing ? "" : "+";
      preview.style.transform = hasBearing ? "rotate(" + Number(bearing.value) + "deg)" : "";
    };
    bearing.oninput = updateBearing;
    updateBearing();
    handle.on("drag", () => {
      const position = handle.getLatLng().wrap();
      lat.value = position.lat.toFixed(7);
      lon.value = position.lng.toFixed(7);
    });
    handle.on("dragend", () => popup.setLatLng(handle.getLatLng()));
    popup.once("remove", () => handle.remove());
    for (const input of [lat, lon]) input.onchange = () => {
      if (!lat.checkValidity() || !lon.checkValidity()) return;
      const position = L.latLng(Number(lat.value), Number(lon.value));
      handle.setLatLng(position);
      popup.setLatLng(position);
    };
    const submit = async change => {
      save.disabled = true;
      remove.disabled = true;
      try {
        await change();
        if (popup.isOpen()) this.map.closePopup(popup);
      } catch (error) {
        status.textContent = error.message;
        save.disabled = false;
        remove.disabled = false;
      }
    };
    form.onsubmit = event => {
      event.preventDefault();
      const coordinates = {lat: Number(lat.value), lon: Number(lon.value)};
      if (bearing.value !== "" && (originalBearing == null || originalBearing === "" || Number(bearing.value) !== Number(originalBearing) % 360)) {
        coordinates.bearing = Number(bearing.value) % 360;
      }
      submit(() => this.options.saveEdit(feature.properties.frame_index, coordinates));
    };
    remove.onclick = () => {
      if (window.confirm("Delete this photo point from the current survey?")) {
        submit(() => this.options.deletePoint(feature.properties.frame_index));
      }
    };
    popup.update();
    lat.focus({preventScroll: true});
  }

}
