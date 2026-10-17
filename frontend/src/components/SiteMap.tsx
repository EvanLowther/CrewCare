"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import type { SiteSummary } from "@/lib/api";
import { ALERT_EMOJI, ALERT_ICONS, ALERT_LABELS } from "@/lib/alerts";
import { NO_SCORE_COLOR, NO_SCORE_INK, RISK_COLORS, RISK_INK, RISK_LABELS } from "@/lib/risk";
import { ScoreChip } from "./ui";

const FLORIDA_CENTER: L.LatLngTuple = [27.9, -83.2];
// Esri's free dark-gray canvas (no key); labels come from a separate reference layer drawn on top.
const BASE_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}";
const LABEL_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}";
const ATTRIBUTION = "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors";

function pinIcon(site: SiteSummary, selected: boolean): L.DivIcon {
  const level = site.risk?.level;
  const color = level ? RISK_COLORS[level] : NO_SCORE_COLOR;
  const ink = level ? RISK_INK[level] : NO_SCORE_INK;
  const size = site.risk && site.risk.score >= 7.5 ? 38 : 32;
  const classes = ["site-pin", site.top_alert ? "alerting" : "", selected ? "selected" : ""].join(" ");
  const badge = site.top_alert === "lightning" ? `<span class="badge">${ALERT_EMOJI.lightning}</span>` : "";
  return L.divIcon({
    className: "site-pin-wrap",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
    html: `<div class="${classes}" style="width:${size}px;height:${size}px;background:${color};color:${ink};--pin-color:${color}">
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
    // Scroll-wheel zoom off so scrolling the page over the map scrolls the page; +/- and pinch still zoom.
    <MapContainer center={FLORIDA_CENTER} zoom={6} className="h-full w-full" scrollWheelZoom={false}>
      <TileLayer attribution={ATTRIBUTION} url={BASE_TILES} maxZoom={16} />
      <TileLayer url={LABEL_TILES} maxZoom={16} />
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
          <Popup minWidth={240}>
            <SitePopup site={site} />
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}

function SitePopup({ site }: { site: SiteSummary }) {
  const risk = site.risk;
  const AlertIcon = site.top_alert ? ALERT_ICONS[site.top_alert] : null;
  return (
    <div className="space-y-3 text-sm">
      <div>
        <div className="text-base font-semibold text-ink">{site.name}</div>
        <div className="text-xs text-muted">
          {site.utility} · {site.county} County
        </div>
      </div>
      <div className="flex items-center gap-2">
        <ScoreChip score={risk?.score ?? null} level={risk?.level ?? null} />
        <span className="text-ink-2">{risk ? `${RISK_LABELS[risk.level]} risk` : "No risk score yet"}</span>
      </div>
      {site.top_alert && AlertIcon && (
        <div className="flex items-center gap-2 font-medium text-[#ff9b9b]">
          <AlertIcon className="h-4 w-4" aria-hidden />
          {ALERT_LABELS[site.top_alert]}
          {site.active_alert_count > 1 && <span className="text-muted">+{site.active_alert_count - 1} more</span>}
        </div>
      )}
      {risk && risk.factors.length > 0 && (
        <ul className="space-y-1 text-xs text-ink-2">
          {risk.factors.slice(0, 3).map((f) => (
            <li key={f.key} className="flex justify-between gap-3">
              <span>{f.label}</span>
              <span className="tabular text-muted">+{f.contribution.toFixed(1)}</span>
            </li>
          ))}
        </ul>
      )}
      <Link
        href={`/sites/${site.id}`}
        className="inline-flex items-center gap-1 text-sm font-medium !text-accent hover:underline"
      >
        View site <ArrowRight className="h-3.5 w-3.5" aria-hidden />
      </Link>
    </div>
  );
}
