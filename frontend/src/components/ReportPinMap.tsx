"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect, useMemo, useRef } from "react";
import { Circle, MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import type { SiteSummary } from "@/lib/api";

const BASE_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}";
const LABEL_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}";
const US_CENTER: L.LatLngTuple = [39.5, -98.35];

export type LatLng = { lat: number; lng: number };

const pin = L.divIcon({
  className: "site-pin-wrap",
  iconSize: [30, 40],
  iconAnchor: [15, 38],
  html: `<svg width="30" height="40" viewBox="0 0 30 40" xmlns="http://www.w3.org/2000/svg">
    <path d="M15 1C7.3 1 1 7.2 1 14.9 1 25.3 15 39 15 39s14-13.7 14-24.1C29 7.2 22.7 1 15 1z" fill="#6e7bff" stroke="#0b1130" stroke-width="2"/>
    <circle cx="15" cy="15" r="5.5" fill="#0b1130"/></svg>`,
});

const siteDot = L.divIcon({
  className: "site-pin-wrap",
  iconSize: [10, 10],
  iconAnchor: [5, 5],
  html: `<div style="width:10px;height:10px;border-radius:9999px;background:#aeb6d9;border:2px solid #0b1130"></div>`,
});

/** Re-centers when the position comes from GPS (not when the user drags), and lets a tap move the pin. */
function Controller({ position, recenterKey, onMove }: { position: LatLng | null; recenterKey: number; onMove: (p: LatLng) => void }) {
  const map = useMap();
  useMapEvents({ click: (e) => onMove({ lat: e.latlng.lat, lng: e.latlng.lng }) });

  // Same reason as the dashboard map: measure again whenever the box changes size.
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);

  useEffect(() => {
    if (position) map.setView([position.lat, position.lng], Math.max(map.getZoom(), 16));
    // Only when a new GPS fix arrives (recenterKey), not on every drag.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recenterKey]);
  return null;
}

/** Small map for the report form: a draggable pin, the GPS accuracy circle, and nearby sites as dots. */
export default function ReportPinMap({
  position,
  gps,
  accuracyM,
  recenterKey,
  sites,
  onMove,
}: {
  position: LatLng | null;
  gps: LatLng | null; // the GPS fix itself; the accuracy circle stays here while the pin is dragged
  accuracyM: number | null;
  recenterKey: number;
  sites: SiteSummary[];
  onMove: (p: LatLng) => void;
}) {
  const markerRef = useRef<L.Marker>(null);
  const handlers = useMemo(
    () => ({
      dragend() {
        const ll = markerRef.current?.getLatLng();
        if (ll) onMove({ lat: ll.lat, lng: ll.lng });
      },
    }),
    [onMove],
  );

  return (
    <MapContainer
      center={position ? [position.lat, position.lng] : US_CENTER}
      zoom={position ? 16 : 4}
      className="h-full w-full"
      scrollWheelZoom={false}
    >
      <TileLayer attribution="Tiles &copy; Esri" url={BASE_TILES} maxZoom={18} />
      <TileLayer url={LABEL_TILES} maxZoom={18} />
      <Controller position={position} recenterKey={recenterKey} onMove={onMove} />
      {sites.map((s) => (
        <Marker key={s.id} position={[s.latitude, s.longitude]} icon={siteDot} interactive={false} />
      ))}
      {gps && accuracyM !== null && (
        <Circle
          center={[gps.lat, gps.lng]}
          radius={accuracyM}
          pathOptions={{ color: "#6e7bff", weight: 1, fillOpacity: 0.08 }}
        />
      )}
      {position && (
        <Marker position={[position.lat, position.lng]} icon={pin} draggable eventHandlers={handlers} ref={markerRef} />
      )}
    </MapContainer>
  );
}
