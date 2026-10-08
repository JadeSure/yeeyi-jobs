import { useEffect, useRef } from "react";
import L from "leaflet";
import { ageLabel, bandOf, shortSuburb } from "./lib.js";

// Standard OSM tiles (no key). Dark mode inverts them in CSS (.dark-tiles).
const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const MELBOURNE = [-37.8136, 144.9631];
const FIT_RADIUS_M = 80_000;

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

function groupBySuburb(jobs) {
  const groups = new Map();
  for (const j of jobs) {
    if (!j.key) continue;
    if (!groups.has(j.key)) groups.set(j.key, []);
    groups.get(j.key).push(j);
  }
  return groups;
}

export default function JobMap({ jobs, selected, onSelect, dark, fitKey }) {
  const el = useRef(null);
  const map = useRef(null);
  const pins = useRef(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    map.current = L.map(el.current, { zoomSnap: 0.25 }).setView(MELBOURNE, 10);
    map.current.attributionControl.setPrefix(false);
    pins.current = L.layerGroup().addTo(map.current);
    L.tileLayer(TILE_URL, { attribution: ATTRIBUTION, maxZoom: 19 }).addTo(map.current);
    // Leaflet measures its box once; re-measure when layout settles (fonts, phone rotation).
    const ro = new ResizeObserver(() => map.current.invalidateSize());
    ro.observe(el.current);
    return () => {
      ro.disconnect();
      map.current.remove();
    };
  }, []);

  useEffect(() => {
    map.current.getContainer().classList.toggle("dark-tiles", dark);
  }, [dark]);

  useEffect(() => {
    pins.current.clearLayers();
    for (const [key, list] of groupBySuburb(jobs)) {
      const band = bandOf(list[0].refreshed); // jobs arrive newest first
      const size = Math.round(18 + Math.sqrt(list.length) * 5);
      const icon = L.divIcon({
        className: "",
        html: `<div class="pin b${band}${selected === key ? " sel" : ""}" style="width:${size}px;height:${size}px">${list.length}</div>`,
        iconSize: [size, size],
      });
      const rows = list
        .slice(0, 6)
        .map((j) => `<span class="dot b${bandOf(j.refreshed)}"></span>${esc(j.title)} <small>${ageLabel(j.refreshed)}</small>`)
        .join("<br>");
      const marker = L.marker(key.split(",").map(Number), {
        icon,
        title: `${shortSuburb(list[0].suburb)} ${list.length}个职位`,
        zIndexOffset: (6 - band) * 1000, // newest areas draw on top
      })
        .bindPopup(`<b>${esc(shortSuburb(list[0].suburb))} · ${list.length}个</b>${rows}${list.length > 6 ? "<br>…" : ""}`)
        .on("click", () => onSelectRef.current(key))
        .addTo(pins.current);
      if (key === selected) marker.openPopup(); // pins are redrawn on select, so reopen its popup
    }
  }, [jobs, selected]);

  // Refit only when the filters change, not when a suburb is picked.
  useEffect(() => {
    // Fit to metro pins only; a lone country job (e.g. Apollo Bay) stays on the map but doesn't zoom it out.
    const center = L.latLng(MELBOURNE);
    const points = jobs.filter((j) => j.latlng && center.distanceTo(j.latlng) < FIT_RADIUS_M).map((j) => j.latlng);
    map.current.invalidateSize();
    if (points.length) map.current.fitBounds(points, { padding: [24, 24], maxZoom: 12 });
  }, [fitKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={el} id="map" role="region" aria-label="墨尔本地图" />;
}
