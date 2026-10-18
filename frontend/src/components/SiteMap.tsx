"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, Marker, Popup, TileLayer, Tooltip, useMap, useMapEvents, ZoomControl } from "react-leaflet";
import { api, type Alert, type HazardReport, type Scorer, type SiteSummary } from "@/lib/api";
import { ALERT_ICONS, ALERT_LABELS, SEVERITY_STYLES } from "@/lib/alerts";
import { factorKind, HAZARD_KINDS } from "@/lib/hazardKinds";
import { relativeTime } from "@/lib/format";
import { HAZARD_ICON_PATHS, HAZARD_LABELS, REPORT_SEVERITY_COLORS } from "@/lib/reports";
import { NO_SCORE_COLOR, RISK_COLORS, RISK_GUIDANCE, RISK_LABELS, RISK_TEXT } from "@/lib/risk";
import { useIsShown } from "@/lib/useIsShown";

const US_CENTER: L.LatLngTuple = [39.5, -98.35];

/** The first view fits the lower 48; Alaska and Hawaii would zoom it out to half the Pacific, so they're a pan away. */
function inLower48(s: SiteSummary): boolean {
  return s.latitude >= 24 && s.latitude <= 50 && s.longitude >= -125 && s.longitude <= -66;
}

// Esri's free dark-gray canvas (no key); labels come from a separate reference layer drawn on top.
const BASE_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}";
const LABEL_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}";
const ATTRIBUTION = "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors";

/**
 * Marker size by zoom. National: a plain 10px dot (160 numbered discs would overlap into a wall).
 * State: a 30px disc with the score. Local: 40px.
 */
type Tier = { size: number; fontSize: number; outline: number; showScore: boolean };
function tierFor(zoom: number): Tier {
  if (zoom <= 5) return { size: 10, fontSize: 0, outline: 1.5, showScore: false };
  if (zoom <= 8) return { size: 30, fontSize: 11, outline: 2, showScore: true };
  return { size: 40, fontSize: 15, outline: 2, showScore: true };
}

const BOLT_SVG =
  '<svg width="11" height="11" viewBox="0 0 24 24" fill="#06080c" aria-hidden="true"><path d="M13 2L4 14h7l-1 8 9-12h-7z"/></svg>';

function siteIcon(site: SiteSummary, tier: Tier, selected: boolean, ringColor: string | null): L.DivIcon {
  const color = site.risk ? RISK_COLORS[site.risk.level] : NO_SCORE_COLOR;
  const lightning = site.top_alert === "lightning";
  const ring = ringColor ? `<span class="pc-ring" style="--ring-color:${ringColor}"></span>` : "";
  const bolt = lightning && tier.showScore ? `<span class="pc-bolt">${BOLT_SVG}</span>` : "";
  const label = tier.showScore ? (site.risk ? site.risk.score.toFixed(1) : "–") : "";
  return L.divIcon({
    className: "pc-icon",
    iconSize: [tier.size, tier.size],
    iconAnchor: [tier.size / 2, tier.size / 2],
    popupAnchor: [0, -tier.size / 2 - 4],
    tooltipAnchor: [-tier.size / 2 - 6, 0],
    html: `<div class="pc-mark${selected ? " is-selected" : ""}" style="--pin-color:${color};--pin-outline:${tier.outline}px">
             ${ring}<span class="pc-body" style="font-size:${tier.fontSize}px">${label}</span>${bolt}
           </div>`,
  });
}

function reportIcon(r: HazardReport, tier: Tier): L.DivIcon {
  const size = tier.showScore ? 30 : 20;
  const icon = tier.showScore ? 13 : 10;
  return L.divIcon({
    className: "pc-icon",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
    html: `<div class="pc-diamond" style="--report-color:${REPORT_SEVERITY_COLORS[r.severity]}">
             <svg width="${icon}" height="${icon}" viewBox="0 0 24 24" fill="none" stroke="#06080c" stroke-width="2.6"
               stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${HAZARD_ICON_PATHS[r.hazard_type]}"/></svg>
           </div>`,
  });
}

export type MapInsets = { top: number; right: number; bottom: number; left: number };

/** Fits all sites on first load (or centers on `focus`), flies to the selected one, and reports the zoom. */
function MapController({
  sites,
  selectedId,
  markers,
  insets,
  focus,
  onZoom,
}: {
  sites: SiteSummary[];
  selectedId: number | null;
  markers: React.RefObject<Map<number, L.Marker>>;
  insets: MapInsets;
  focus?: { lat: number; lng: number; zoom: number };
  onZoom: (zoom: number) => void;
}) {
  const map = useMap();
  const fitted = useRef<string | null>(null);
  const [sized, setSized] = useState(false);
  useMapEvents({ zoomend: () => onZoom(map.getZoom()) });

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

  // Fit once per set of sites (again when "My sites" / "All sites" changes it), not on every poll. The insets keep
  // the sites clear of the panels floating over the map.
  const siteKey = focus ? `focus:${focus.lat},${focus.lng}` : sites.map((s) => s.id).join(",");
  useEffect(() => {
    if (fitted.current === siteKey || !sized) return;
    if (focus) {
      map.setView([focus.lat, focus.lng], focus.zoom);
    } else {
      if (sites.length === 0) return;
      const shown = sites.some(inLower48) ? sites.filter(inLower48) : sites;
      // maxZoom: a single site would otherwise zoom past the tiles.
      map.fitBounds(L.latLngBounds(shown.map((s) => [s.latitude, s.longitude])), {
        paddingTopLeft: [insets.left + 24, insets.top + 24],
        paddingBottomRight: [insets.right + 24, insets.bottom + 24],
        maxZoom: 11,
      });
    }
    onZoom(map.getZoom());
    fitted.current = siteKey;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- siteKey stands for `sites` / `focus`
  }, [map, siteKey, sized]);

  useEffect(() => {
    if (selectedId === null || focus) return;
    const site = sites.find((s) => s.id === selectedId);
    if (!site) return;
    map.flyTo([site.latitude, site.longitude], Math.max(map.getZoom(), 7), { duration: 0.8 });
    markers.current.get(selectedId)?.openPopup();
    // Only re-run when the selection changes, not on every poll.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  return null;
}

const NO_INSETS: MapInsets = { top: 0, right: 0, bottom: 0, left: 0 };
const SEVERITY_ORDER = { danger: 0, warning: 1, info: 2 } as const;

export default function SiteMap({
  sites,
  selectedId,
  onSelect,
  model,
  reports = [],
  alerts = [],
  insets = NO_INSETS,
  focus,
  zoomPosition = "topright",
}: {
  sites: SiteSummary[];
  selectedId: number | null;
  onSelect?: (id: number) => void;
  model?: Scorer;
  reports?: HazardReport[];
  /** Active alerts: each site's most severe one colors its pulsing ring. */
  alerts?: Alert[];
  /** Room taken by panels floating over the map, in px, so the first fit keeps sites out from under them. */
  insets?: MapInsets;
  /** Start centered here instead of fitting every site (the site page). */
  focus?: { lat: number; lng: number; zoom: number };
  zoomPosition?: L.ControlPosition;
}) {
  const markers = useRef(new Map<number, L.Marker>());
  // Only while the page is on screen, so returning to it builds a fresh map (see useIsShown).
  const shown = useIsShown();
  const [zoom, setZoom] = useState(focus?.zoom ?? 4);
  const tier = tierFor(zoom);
  // Draw the riskiest sites on top when markers overlap.
  const ordered = useMemo(() => [...sites].reverse(), [sites]);
  const ringBySite = useMemo(() => {
    const worst = new Map<number, Alert["severity"]>();
    for (const a of alerts) {
      const prev = worst.get(a.site_id);
      if (!prev || SEVERITY_ORDER[a.severity] < SEVERITY_ORDER[prev]) worst.set(a.site_id, a.severity);
    }
    return worst;
  }, [alerts]);

  if (!shown) return null;
  return (
    // Scroll-wheel zoom off so scrolling the page over the map scrolls the page; +/- and pinch still zoom.
    // Start at the focus when there is one: jumping from zoom 4 leaves stretched zoom-4 label tiles behind.
    <MapContainer
      center={focus ? [focus.lat, focus.lng] : US_CENTER}
      zoom={focus?.zoom ?? 4}
      className="h-full w-full"
      scrollWheelZoom={false}
      zoomControl={false}
      zoomSnap={0.5}
    >
      <TileLayer attribution={ATTRIBUTION} url={BASE_TILES} maxZoom={16} />
      <TileLayer url={LABEL_TILES} maxZoom={16} opacity={0.7} />
      <ZoomControl position={zoomPosition} />
      <MapController
        sites={sites}
        selectedId={selectedId}
        markers={markers}
        insets={insets}
        focus={focus}
        onZoom={setZoom}
      />
      {ordered.map((site, i) => {
        const severity = ringBySite.get(site.id) ?? (site.active_alert_count > 0 ? "warning" : null);
        const ring = site.top_alert === "lightning" ? RISK_COLORS.extreme : severity ? SEVERITY_STYLES[severity].dot : null;
        return (
          <Marker
            key={site.id}
            position={[site.latitude, site.longitude]}
            icon={siteIcon(site, tier, site.id === selectedId, ring)}
            zIndexOffset={site.id === selectedId ? 5000 : i * 10}
            eventHandlers={{ click: () => onSelect?.(site.id) }}
            ref={(m) => {
              if (m) markers.current.set(site.id, m);
              else markers.current.delete(site.id);
            }}
          >
            <Tooltip direction="left" className={`pc-tag lvl-${site.risk?.level ?? "none"}`}>
              <SiteTag site={site} />
            </Tooltip>
            <Popup
              minWidth={280}
              maxWidth={320}
              autoPanPaddingTopLeft={[insets.left + 16, insets.top + 16]}
              autoPanPaddingBottomRight={[insets.right + 16, insets.bottom + 16]}
            >
              <SiteCard site={site} model={model} />
            </Popup>
          </Marker>
        );
      })}
      {reports.map((r) => (
        <Marker key={r.id} position={[r.latitude, r.longitude]} icon={reportIcon(r, tier)} zIndexOffset={6000}>
          <Tooltip direction="left" className="pc-tag">
            <span className="eyebrow block">Crew report · {r.severity} severity</span>
            <span className="text-sm font-semibold">{HAZARD_LABELS[r.hazard_type]}</span>
          </Tooltip>
          <Popup minWidth={240}>
            <ReportCard report={r} />
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}

/** Hover tag: SITE · COUNTY, score · level, top factor. */
function SiteTag({ site }: { site: SiteSummary }) {
  const risk = site.risk;
  return (
    <span className="flex flex-col gap-0.5">
      <span className="eyebrow !text-ink-2">
        {site.name}
        {site.county ? ` · ${site.county}` : ""}
      </span>
      <span className="text-sm font-semibold">
        {risk ? (
          <>
            {risk.score.toFixed(1)} · <span style={{ color: RISK_TEXT[risk.level] }}>{RISK_LABELS[risk.level].toUpperCase()}</span>
          </>
        ) : (
          "No score yet"
        )}
      </span>
      {risk?.factors[0] && <span className="text-xs text-ink-2">{risk.factors[0].label}</span>}
    </span>
  );
}

/** Click card: the site page's summary in miniature. */
function SiteCard({ site, model }: { site: SiteSummary; model?: Scorer }) {
  const risk = site.risk;
  const AlertIcon = site.top_alert ? ALERT_ICONS[site.top_alert] : null;
  const glow = risk?.level === "extreme" ? "radial-gradient(ellipse at 85% 0%, #2a0d10 0%, #0a0d13 60%)" : "#0a0d13";
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-line p-4 shadow-[0_16px_40px_rgb(0_0_0/0.55)]" style={{ background: glow }}>
      <div>
        <p className="eyebrow">
          {[site.county ? `${site.county} County` : null, site.utility].filter(Boolean).join(" · ")}
        </p>
        <p className="mt-1 font-display text-[26px] leading-none font-extrabold text-ink">{site.name}</p>
      </div>
      {risk ? (
        <div className="flex items-end gap-3">
          <span className="font-display text-[54px] leading-[0.8] font-extrabold" style={{ color: RISK_COLORS[risk.level] }}>
            {risk.score.toFixed(1)}
          </span>
          <span className="flex flex-col gap-0.5">
            <span className="font-mono text-[11px] tracking-[0.12em]" style={{ color: RISK_TEXT[risk.level] }}>
              {RISK_LABELS[risk.level].toUpperCase()}
            </span>
            <span className="text-[13px] font-semibold text-ink">{RISK_GUIDANCE[risk.level]}</span>
          </span>
        </div>
      ) : (
        <p className="text-sm text-ink-2">No risk score yet</p>
      )}
      {site.top_alert && AlertIcon && (
        <p className="flex items-center gap-2 text-xs font-medium text-risk-moderate">
          <AlertIcon className="h-4 w-4" aria-hidden />
          {ALERT_LABELS[site.top_alert]}
          {site.active_alert_count > 1 && <span className="text-muted">+{site.active_alert_count - 1} more</span>}
        </p>
      )}
      {risk && risk.factors.length > 0 && (
        <ul className="flex flex-col gap-1 text-xs text-ink">
          {risk.factors.slice(0, 3).map((f) => {
            const kind = HAZARD_KINDS[factorKind(f.key, f.label)];
            return (
              <li key={f.key} className="flex justify-between gap-3">
                <span className="flex items-start gap-1.5">
                  <kind.icon className="mt-px h-3.5 w-3.5 shrink-0" style={{ color: kind.color }} aria-label={kind.label} />
                  {f.label}
                </span>
                <span className="tabular font-mono" style={{ color: RISK_TEXT[risk.level] }}>
                  +{f.contribution.toFixed(1)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <Link
        href={`/sites/${site.id}${model ? `?model=${model}` : ""}`}
        className="inline-flex items-center gap-1.5 text-[13px] font-semibold !text-accent hover:underline"
      >
        View site <ArrowRight className="h-3.5 w-3.5" aria-hidden />
      </Link>
    </div>
  );
}

function ReportCard({ report }: { report: HazardReport }) {
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-line bg-card p-4 text-sm shadow-[0_16px_40px_rgb(0_0_0/0.55)]">
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rotate-45 rounded-[2px]" style={{ background: REPORT_SEVERITY_COLORS[report.severity] }} aria-hidden />
        <span className="font-semibold text-ink">{HAZARD_LABELS[report.hazard_type]}</span>
        <span className="text-xs text-muted">{report.severity} severity</span>
      </div>
      {report.photo_url && (
        // eslint-disable-next-line @next/next/no-img-element -- our own resized upload
        <img src={api.photoUrl(report.photo_url)} alt="" className="max-h-40 w-full rounded-lg object-cover" />
      )}
      {report.description && <p className="text-ink-2">{report.description}</p>}
      <p className="text-xs text-muted">
        Crew report · {report.reporter_name ?? "Crew member"} · {relativeTime(report.created_at)}
      </p>
    </div>
  );
}
