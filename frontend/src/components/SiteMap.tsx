"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import { api, type HazardReport, type Scorer, type SiteSummary } from "@/lib/api";
import { ALERT_EMOJI, ALERT_ICONS, ALERT_LABELS } from "@/lib/alerts";
import { relativeTime } from "@/lib/format";
import { HAZARD_EMOJI, HAZARD_LABELS, REPORT_SEVERITY_COLORS } from "@/lib/reports";
import { NO_SCORE_COLOR, NO_SCORE_INK, RISK_COLORS, RISK_GUIDANCE, RISK_INK, RISK_LABELS } from "@/lib/risk";
import { ScoreChip } from "./ui";

const US_CENTER: L.LatLngTuple = [39.5, -98.35];

/** The first view fits the lower 48; Alaska and Hawaii would zoom it out to half the Pacific, so they're a pan away. */
function inLower48(s: SiteSummary): boolean {
  return s.latitude >= 24 && s.latitude <= 50 && s.longitude >= -125 && s.longitude <= -66;
}

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
  const fitted = useRef<string | null>(null);
  const [sized, setSized] = useState(false);

  // Leaflet only measures its box on window resize. In a background tab or a hidden pane the box is 0x0 at
  // first, and fitting then zooms to the maximum, so re-measure whenever the container's size changes.
  useEffect(() => {
    const container = map.getContainer();
    const observer = new ResizeObserver(() => {
      map.invalidateSize();
      setSized(container.clientWidth > 0 && container.clientHeight > 0);
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [map]);

  // Fit once per set of sites (again when "My sites" / "All sites" changes it), not on every poll.
  const siteKey = sites.map((s) => s.id).join(",");
  useEffect(() => {
    if (fitted.current === siteKey || !sized || sites.length === 0) return;
    const shown = sites.some(inLower48) ? sites.filter(inLower48) : sites;
    // maxZoom: a single site would otherwise zoom past the tiles.
    map.fitBounds(L.latLngBounds(shown.map((s) => [s.latitude, s.longitude])), { padding: [30, 30], maxZoom: 11 });
    fitted.current = siteKey;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- siteKey stands for `sites`
  }, [map, siteKey, sized]);

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
  model,
  reports = [],
}: {
  sites: SiteSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  model?: Scorer;
  reports?: HazardReport[];
}) {
  const markers = useRef(new Map<number, L.Marker>());
  // Draw the riskiest sites on top when pins overlap.
  const ordered = useMemo(() => [...sites].reverse(), [sites]);

  return (
    // Scroll-wheel zoom off so scrolling the page over the map scrolls the page; +/- and pinch still zoom.
    <MapContainer center={US_CENTER} zoom={4} className="h-full w-full" scrollWheelZoom={false}>
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
            <SitePopup site={site} model={model} />
          </Popup>
        </Marker>
      ))}
      {reports.map((r) => (
        <Marker key={r.id} position={[r.latitude, r.longitude]} icon={reportIcon(r)} zIndexOffset={2000}>
          <Popup minWidth={220}>
            <ReportPopup report={r} />
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}

function SitePopup({ site, model }: { site: SiteSummary; model?: Scorer }) {
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
        <span className="text-ink-2">{risk ? `${RISK_LABELS[risk.level]} · ${RISK_GUIDANCE[risk.level]}` : "No risk score yet"}</span>
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
              <span className="tabular text-muted">{f.contribution.toFixed(1)}</span>
            </li>
          ))}
        </ul>
      )}
      {risk?.factors.find((f) => f.action)?.action && (
        <p className="rounded-md bg-accent-soft px-2.5 py-1.5 text-xs text-ink">
          {risk.factors.find((f) => f.action)?.action}
        </p>
      )}
      <Link
        href={`/sites/${site.id}${model ? `?model=${model}` : ""}`}
        className="inline-flex items-center gap-1 text-sm font-medium !text-accent hover:underline"
      >
        View site <ArrowRight className="h-3.5 w-3.5" aria-hidden />
      </Link>
    </div>
  );
}

function reportIcon(r: HazardReport): L.DivIcon {
  return L.divIcon({
    className: "site-pin-wrap",
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    popupAnchor: [0, -13],
    html: `<div class="report-pin" style="--report-color:${REPORT_SEVERITY_COLORS[r.severity]}">${HAZARD_EMOJI[r.hazard_type]}</div>`,
  });
}

function ReportPopup({ report }: { report: HazardReport }) {
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: REPORT_SEVERITY_COLORS[report.severity] }} aria-hidden />
        <span className="font-semibold text-ink">{HAZARD_LABELS[report.hazard_type]}</span>
        <span className="text-xs text-muted">{report.severity} severity</span>
      </div>
      {report.photo_url && (
        // eslint-disable-next-line @next/next/no-img-element -- our own resized upload
        <img src={api.photoUrl(report.photo_url)} alt="" className="max-h-40 w-full rounded-md object-cover" />
      )}
      {report.description && <p className="text-ink-2">{report.description}</p>}
      <p className="text-xs text-muted">
        Crew report · {report.reporter_name ?? "Crew member"} · {relativeTime(report.created_at)}
      </p>
    </div>
  );
}
