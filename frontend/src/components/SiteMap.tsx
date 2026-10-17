"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import Link from "next/link";
import { useEffect, useMemo, useRef } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import type { SiteSummary } from "@/lib/api";
import { ALERT_ICONS, ALERT_LABELS } from "@/lib/alerts";
import { RISK_COLORS, RISK_LABELS } from "@/lib/risk";

const FLORIDA_CENTER: L.LatLngTuple = [27.9, -83.2];
const NO_SCORE_COLOR = "#6b7280";

function pinIcon(site: SiteSummary, selected: boolean): L.DivIcon {
  const color = site.risk ? RISK_COLORS[site.risk.level] : NO_SCORE_COLOR;
  const size = site.risk && site.risk.score >= 7.5 ? 38 : 32;
  const classes = ["site-pin", site.top_alert ? "alerting" : "", selected ? "selected" : ""].join(" ");
  const badge = site.top_alert === "lightning" ? `<span class="badge">${ALERT_ICONS.lightning}</span>` : "";
  return L.divIcon({
    className: "site-pin-wrap",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
    html: `<div class="${classes}" style="width:${size}px;height:${size}px;background:${color};--pin-color:${color}">
             ${site.risk ? site.risk.score.toFixed(1) : "–"}${badge}
           </div>`,
  });
}

/** Fits all sites on first load, then flies to the selected one. */
function MapController({
  sites,
  selectedId,
  markers,
}: {
  sites: SiteSummary[];
  selectedId: number | null;
  markers: React.RefObject<Map<number, L.Marker>>;
}) {
  const map = useMap();
  const fitted = useRef(false);

  useEffect(() => {
    if (fitted.current || sites.length === 0) return;
    map.fitBounds(L.latLngBounds(sites.map((s) => [s.latitude, s.longitude])), { padding: [30, 30] });
    fitted.current = true;
  }, [map, sites]);

  useEffect(() => {
    if (selectedId === null) return;
    const site = sites.find((s) => s.id === selectedId);
    if (!site) return;
    map.flyTo([site.latitude, site.longitude], Math.max(map.getZoom(), 9), { duration: 0.8 });
    markers.current.get(selectedId)?.openPopup();
    // Only re-run when the selection changes, not on every poll.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  return null;
}

export default function SiteMap({
  sites,
  selectedId,
  onSelect,
}: {
  sites: SiteSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const markers = useRef(new Map<number, L.Marker>());
  // Draw the riskiest sites on top when pins overlap.
  const ordered = useMemo(() => [...sites].reverse(), [sites]);

  return (
    <MapContainer center={FLORIDA_CENTER} zoom={6} className="h-full w-full" scrollWheelZoom>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <MapController sites={sites} selectedId={selectedId} markers={markers} />
      {ordered.map((site, i) => (
        <Marker
          key={site.id}
          position={[site.latitude, site.longitude]}
          icon={pinIcon(site, site.id === selectedId)}
          zIndexOffset={i * 10}
          eventHandlers={{ click: () => onSelect(site.id) }}
          ref={(m) => {
            if (m) markers.current.set(site.id, m);
            else markers.current.delete(site.id);
          }}
        >
          <Popup minWidth={220}>
            <SitePopup site={site} />
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}

function SitePopup({ site }: { site: SiteSummary }) {
  const risk = site.risk;
  return (
    <div className="space-y-2 text-sm">
      <div>
        <div className="text-base font-semibold">{site.name}</div>
        <div className="text-neutral-500">
          {site.utility} · {site.county} County
        </div>
      </div>
      {risk ? (
        <div className="flex items-center gap-2">
          <span
            className="rounded px-2 py-0.5 font-bold text-white"
            style={{ background: RISK_COLORS[risk.level] }}
          >
            {risk.score.toFixed(1)}
          </span>
          <span className="font-medium">{RISK_LABELS[risk.level]} risk</span>
        </div>
      ) : (
        <div className="text-neutral-500">No risk score yet</div>
      )}
      {site.top_alert && (
        <div className="font-medium text-red-700">
          {ALERT_ICONS[site.top_alert]} {ALERT_LABELS[site.top_alert]}
          {site.active_alert_count > 1 && ` +${site.active_alert_count - 1} more`}
        </div>
      )}
      {risk && risk.factors.length > 0 && (
        <ul className="list-disc pl-4 text-neutral-700">
          {risk.factors.slice(0, 3).map((f) => (
            <li key={f.key}>{f.label}</li>
          ))}
        </ul>
      )}
      <Link href={`/sites/${site.id}`} className="inline-block font-medium text-blue-700 hover:underline">
        View site →
      </Link>
    </div>
  );
}
