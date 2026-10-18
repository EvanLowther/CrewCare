"use client";

import {
  ArrowRight,
  Camera,
  CheckCircle2,
  Crosshair,
  ImagePlus,
  Loader2,
  LogIn,
  Lock,
  MapPin,
  TriangleAlert,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type HazardReport, type HazardType, type ReportSeverity, type SiteSummary } from "@/lib/api";
import { DEV_AUTH, signInHref } from "@/lib/auth";
import { HAZARD_ICONS } from "@/lib/reports";
import { useMe } from "./MeProvider";
import type { LatLng } from "./ReportPinMap";
import { Card, CardHeader, EmptyState } from "./ui";

const ReportPinMap = dynamic(() => import("./ReportPinMap"), {
  ssr: false,
  loading: () => <div className="flex h-full items-center justify-center text-sm text-muted">Loading map…</div>,
});

// Grouped so the common ones come first; "Other" stays last.
const HAZARDS: { value: HazardType; label: string; hint?: string }[] = [
  { value: "lightning", label: "Lightning", hint: "Thunder heard or lightning seen" },
  { value: "flooding", label: "Flooding" },
  { value: "high_wind", label: "High wind" },
  { value: "heat_illness", label: "Heat illness" },
  { value: "cold_stress", label: "Cold stress", hint: "Frostbite, shivering, numbness" },
  { value: "ice", label: "Ice", hint: "Icy roads, walkways or equipment" },
  { value: "snow", label: "Snow / drifts" },
  { value: "smoke", label: "Smoke", hint: "Wildfire smoke or bad air" },
  { value: "fire", label: "Fire" },
  { value: "wildlife", label: "Wildlife", hint: "Snakes, gators, bears, wasps…" },
  { value: "downed_line", label: "Downed line" },
  { value: "fallen_tree", label: "Fallen tree", hint: "Trees or debris blocking access" },
  { value: "unstable_ground", label: "Soft ground" },
  { value: "sinkhole", label: "Sinkhole", hint: "Sinkhole, washout or collapse" },
  { value: "earthquake_damage", label: "Quake damage", hint: "Cracks or damage after a quake" },
  { value: "gas_leak", label: "Gas leak / spill", hint: "Gas smell, chemical or fuel spill" },
  { value: "other", label: "Other" },
];

const SEVERITIES: { value: ReportSeverity; label: string; hint: string; color: string }[] = [
  { value: "low", label: "Low", hint: "Heads-up", color: "#0ca30c" },
  { value: "medium", label: "Medium", hint: "Work around it", color: "#fab219" },
  { value: "high", label: "High", hint: "Stop / keep clear", color: "#d03b3b" },
];

const REPORT_RADIUS_MI = 5; // same as the API's REPORT_RADIUS_MI (planit/api/access.py)

function miles(a: LatLng, b: { latitude: number; longitude: number }): number {
  const rad = Math.PI / 180;
  const dLat = (b.latitude - a.lat) * rad;
  const dLng = (b.longitude - a.lng) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.latitude * rad) * Math.sin(dLng / 2) ** 2;
  return 3958.8 * 2 * Math.asin(Math.sqrt(h));
}

function fmtMiles(mi: number) {
  return mi < 0.1 ? `${Math.round(mi * 5280)} ft` : `${mi.toFixed(1)} mi`;
}

type Gps = { status: "idle" | "locating" | "ok" | "denied" | "unavailable" | "insecure"; accuracyM: number | null };

/** Where GPS stands before we ask: HTTP pages and browsers without geolocation can't give a fix at all. */
function initialGps(): Gps {
  if (typeof window === "undefined") return { status: "idle", accuracyM: null };
  if (!window.isSecureContext) return { status: "insecure", accuracyM: null };
  if (!navigator.geolocation) return { status: "unavailable", accuracyM: null };
  return { status: "locating", accuracyM: null };
}

/** Signed-in members report on their sites; signed-out visitors get a sign-in prompt. */
export function ReportForm({ initialSiteId }: { initialSiteId: number | null }) {
  const { me } = useMe();
  if (!me) return <p className="text-sm text-muted">Loading…</p>;
  if (!me.user) {
    return (
      <Card className="mx-auto max-w-xl">
        <EmptyState icon={Lock} title="Sign in to report a hazard" detail="Reports go to the crews and managers on your sites." />
        <div className="pb-8 text-center">
          {DEV_AUTH ? (
            <p className="text-sm text-muted">Pick a user in the sidebar&apos;s &ldquo;Sign in as&rdquo; menu.</p>
          ) : (
            <a
              href={signInHref(`/report${initialSiteId ? `?site=${initialSiteId}` : ""}`)}
              className="inline-flex items-center gap-2 rounded-lg bg-accent-strong px-4 py-2 text-sm font-medium text-on-accent hover:bg-accent"
            >
              <LogIn className="h-4 w-4" aria-hidden /> Sign in
            </a>
          )}
        </div>
      </Card>
    );
  }
  return <SignedInReportForm initialSiteId={initialSiteId} isAdmin={me.user.role === "admin"} reporter={me.user.name ?? me.user.email ?? "you"} />;
}

function SignedInReportForm({ initialSiteId, isAdmin, reporter }: { initialSiteId: number | null; isAdmin: boolean; reporter: string }) {
  const [sites, setSites] = useState<SiteSummary[] | null>(null);
  const [gps, setGps] = useState<Gps>(initialGps);
  const [gpsFix, setGpsFix] = useState<LatLng | null>(null);
  const [pin, setPin] = useState<LatLng | null>(null);
  const [recenterKey, setRecenterKey] = useState(0);
  const [photo, setPhoto] = useState<File | null>(null);
  const [hazard, setHazard] = useState<HazardType | null>(null);
  const [severity, setSeverity] = useState<ReportSeverity | null>(null);
  const [description, setDescription] = useState("");
  const [chosenId, setChosenId] = useState<number | null>(initialSiteId);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<HazardReport | null>(null);

  useEffect(() => {
    // The sites this person may report on: the ones they're on (admins: all).
    api
      .sites("rules")
      .then((r) => setSites(r.sites.filter((s) => isAdmin || s.my_role)))
      .catch(() => setSites([]));
  }, [isAdmin]);

  /** Ask the browser for a fix; state only changes in its callbacks. */
  const requestFix = useCallback(() => {
    navigator.geolocation.getCurrentPosition(
      (p) => {
        const fix = { lat: p.coords.latitude, lng: p.coords.longitude };
        setGpsFix(fix);
        setPin(fix);
        setGps({ status: "ok", accuracyM: Math.round(p.coords.accuracy) });
        setRecenterKey((k) => k + 1);
      },
      (e) => setGps({ status: e.code === e.PERMISSION_DENIED ? "denied" : "unavailable", accuracyM: null }),
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 30_000 },
    );
  }, []);

  /** "My location" button: same request, after showing the spinner. */
  const locate = useCallback(() => {
    const start = initialGps();
    setGps(start);
    if (start.status === "locating") requestFix();
  }, [requestFix]);

  // Ask for the location as soon as the form opens: crews report where they stand.
  useEffect(() => {
    if (initialGps().status === "locating") requestFix();
  }, [requestFix]);

  const preview = useMemo(() => (photo ? URL.createObjectURL(photo) : null), [photo]);
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  // Your sites by distance from where you are (the GPS fix, or the pin until there is one).
  const options = useMemo(() => {
    const from = gpsFix ?? pin;
    return (sites ?? [])
      .map((site) => {
        const mi = from ? miles(from, site) : null;
        return { site, mi, eligible: isAdmin || (gpsFix !== null && mi !== null && mi <= REPORT_RADIUS_MI) };
      })
      .sort((a, b) => (a.mi ?? Infinity) - (b.mi ?? Infinity));
  }, [sites, gpsFix, pin, isAdmin]);

  // The chosen site if it's still eligible, otherwise the nearest eligible one.
  const chosen =
    options.find((o) => o.site.id === chosenId && o.eligible) ?? options.find((o) => o.eligible) ?? null;
  const pinMi = chosen && pin ? miles(pin, chosen.site) : null;
  const pinTooFar = !isAdmin && pinMi !== null && pinMi > REPORT_RADIUS_MI;

  const moved = pin && gpsFix ? miles(gpsFix, { latitude: pin.lat, longitude: pin.lng }) * 5280 : 0; // feet
  const ready = pin !== null && chosen !== null && !pinTooFar && hazard !== null && severity !== null && !submitting;

  async function submit() {
    if (!pin || !hazard || !severity || !chosen) return;
    setSubmitting(true);
    setError(null);
    try {
      const report = await api.createReport({
        site_id: chosen.site.id,
        latitude: pin.lat,
        longitude: pin.lng,
        gps_latitude: gpsFix?.lat,
        gps_longitude: gpsFix?.lng,
        gps_accuracy_m: gps.accuracyM ?? undefined,
        hazard_type: hazard,
        severity,
        description: description.trim() || undefined,
        photo: photo ?? undefined,
      });
      setCreated(report);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send the report");
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    setCreated(null);
    setPhoto(null);
    setHazard(null);
    setSeverity(null);
    setDescription("");
    setPin(gpsFix);
  }

  if (created) {
    const site = (sites ?? []).find((s) => s.id === created.site_id);
    return (
      <Card className="mx-auto max-w-xl">
        <div className="flex flex-col items-center gap-3 px-6 py-10 text-center">
          <CheckCircle2 className="h-12 w-12 text-risk-low" aria-hidden />
          <h2 className="text-lg font-semibold text-ink">Report shared</h2>
          <p className="text-sm text-ink-2">
            {site ? `Filed on ${site.name}. ` : "Pinned on the map. "}Its crew and managers can see it now.
          </p>
          {created.photo_url && (
            // eslint-disable-next-line @next/next/no-img-element -- our own resized upload
            <img src={api.photoUrl(created.photo_url)} alt="" className="max-h-48 rounded-lg border border-line" />
          )}
          <div className="mt-2 flex flex-wrap justify-center gap-2">
            {site && (
              <Link
                href={`/sites/${site.id}?model=rules`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-line px-4 py-2 text-sm text-ink hover:bg-raised"
              >
                View {site.name} <ArrowRight className="h-4 w-4" aria-hidden />
              </Link>
            )}
            <button
              type="button"
              onClick={reset}
              className="rounded-lg bg-accent-strong px-4 py-2 text-sm font-medium text-on-accent hover:bg-accent"
            >
              Report another
            </button>
          </div>
        </div>
      </Card>
    );
  }

  if (sites !== null && sites.length === 0) {
    return (
      <Card className="mx-auto max-w-xl">
        <EmptyState
          icon={MapPin}
          title="You're not on any sites yet"
          detail="You can report hazards on sites you belong to. Ask your site manager to add you."
        />
      </Card>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <Card className="flex flex-col overflow-hidden">
        <CardHeader
          title="1. Where is it?"
          icon={MapPin}
          subtitle="Drag the pin onto the hazard, or tap the map"
          actions={
            <button
              type="button"
              onClick={locate}
              className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs text-ink-2 hover:text-ink"
            >
              {gps.status === "locating" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              ) : (
                <Crosshair className="h-3.5 w-3.5" aria-hidden />
              )}
              My location
            </button>
          }
        />
        <div className="h-72 border-y border-line sm:h-80 lg:h-[420px]">
          <ReportPinMap
            position={pin}
            gps={gpsFix}
            accuracyM={gps.accuracyM}
            recenterKey={recenterKey}
            sites={sites ?? []}
            onMove={setPin}
          />
        </div>
        <div className="space-y-1 px-5 py-3 text-xs">
          <GpsStatus gps={gps} hasPin={pin !== null} movedFt={moved} />
          {pinTooFar && chosen && (
            <p className="text-[#fcc954]">
              The pin is {fmtMiles(pinMi!)} from {chosen.site.name}. Move it within {REPORT_RADIUS_MI} miles of the site.
            </p>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader title="2. What is it?" icon={TriangleAlert} subtitle="A photo helps the next crew recognize it" />
        <div className="space-y-5 px-5 pb-5">
          <SitePicker options={options} chosenId={chosen?.site.id ?? null} onChoose={setChosenId} isAdmin={isAdmin} gps={gpsFix !== null ? "ok" : gps.status === "locating" || gps.status === "idle" ? "waiting" : "off"} loading={sites === null} />
          <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-line bg-raised/50 p-3 hover:border-accent">
            {preview ? (
              // eslint-disable-next-line @next/next/no-img-element -- local preview of the chosen photo
              <img src={preview} alt="Selected hazard photo" className="h-16 w-16 rounded-md object-cover" />
            ) : (
              <span className="flex h-16 w-16 items-center justify-center rounded-md bg-accent-soft text-accent">
                <Camera className="h-6 w-6" aria-hidden />
              </span>
            )}
            <span className="text-sm">
              <span className="block font-medium text-ink">{photo ? "Change photo" : "Take or choose a photo"}</span>
              <span className="text-xs text-muted">{photo ? photo.name : "Optional · location data is removed before it's shared"}</span>
            </span>
            <ImagePlus className="ml-auto h-4 w-4 text-muted" aria-hidden />
            <input
              type="file"
              accept="image/*"
              capture="environment"
              className="sr-only"
              onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
            />
          </label>

          <fieldset>
            <legend className="mb-2 text-xs font-medium text-muted">Hazard</legend>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-3 xl:grid-cols-4">
              {HAZARDS.map(({ value, label }) => {
                const Icon = HAZARD_ICONS[value];
                return (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={hazard === value}
                    onClick={() => setHazard(value)}
                    className={`flex flex-col items-center gap-1.5 rounded-lg border px-1.5 py-3 text-center text-xs leading-tight transition-colors ${
                      hazard === value ? "border-accent bg-accent-soft text-ink" : "border-line text-ink-2 hover:bg-raised"
                    }`}
                  >
                    <Icon className={`h-5 w-5 ${hazard === value ? "text-accent" : ""}`} aria-hidden />
                    {label}
                  </button>
                );
              })}
            </div>
            {hazard && HAZARDS.find((h) => h.value === hazard)?.hint && (
              <p className="mt-2 text-xs text-muted">{HAZARDS.find((h) => h.value === hazard)?.hint}</p>
            )}
          </fieldset>

          <fieldset>
            <legend className="mb-2 text-xs font-medium text-muted">Severity</legend>
            <div className="grid grid-cols-3 gap-2">
              {SEVERITIES.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  aria-pressed={severity === s.value}
                  onClick={() => setSeverity(s.value)}
                  className={`rounded-lg border px-2 py-2.5 text-left transition-colors ${
                    severity === s.value ? "border-accent bg-accent-soft" : "border-line hover:bg-raised"
                  }`}
                >
                  <span className="flex items-center gap-1.5 text-sm font-medium text-ink">
                    <span className="h-2 w-2 rounded-full" style={{ background: s.color }} aria-hidden />
                    {s.label}
                  </span>
                  <span className="text-xs text-muted">{s.hint}</span>
                </button>
              ))}
            </div>
          </fieldset>

          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-muted">What did you see? (optional)</span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              maxLength={500}
              placeholder="e.g. 8 ft gator in the canal next to the laydown yard"
              className="w-full rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </label>

          <p className="text-xs text-muted">Reporting as {reporter}</p>

          {error && <p className="rounded-lg bg-[rgb(255_74_74/0.12)] px-3 py-2 text-sm text-[#ff9b9b]">{error}</p>}

          <button
            type="button"
            onClick={submit}
            disabled={!ready}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent-strong px-4 py-3 text-sm font-semibold text-on-accent transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
            {submitting ? "Sharing…" : "Share hazard"}
          </button>
          {!ready && !submitting && (
            <p className="text-center text-xs text-muted">
              {!pin
                ? "Set the location first"
                : !chosen
                  ? gpsFix
                    ? `None of your sites is within ${REPORT_RADIUS_MI} miles of you`
                    : "Turn on location so we can confirm you're at the site"
                  : pinTooFar
                    ? "Move the pin closer to the site"
                    : !hazard
                      ? "Pick a hazard type"
                      : "Pick a severity"}
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}

function GpsStatus({ gps, hasPin, movedFt }: { gps: Gps; hasPin: boolean; movedFt: number }) {
  switch (gps.status) {
    case "locating":
      return <p className="text-muted">Finding your location…</p>;
    case "ok":
      return (
        <p className="text-ink-2">
          GPS fix ±{gps.accuracyM} m
          {movedFt > 30 && ` · pin moved ${movedFt < 5280 ? `${Math.round(movedFt)} ft` : `${(movedFt / 5280).toFixed(1)} mi`} from you`}
        </p>
      );
    case "denied":
      return <p className="text-[#fcc954]">Location permission is off. Tap the map where the hazard is.</p>;
    case "insecure":
      return (
        <p className="text-[#fcc954]">
          GPS needs an https:// address (or localhost). Tap the map where the hazard is.
        </p>
      );
    case "unavailable":
      return <p className="text-[#fcc954]">Couldn&apos;t get a GPS fix. Tap the map where the hazard is.</p>;
    default:
      return hasPin ? null : <p className="text-muted">Tap the map where the hazard is.</p>;
  }
}

type SiteOption = { site: SiteSummary; mi: number | null; eligible: boolean };

/** Which site the report is for: your sites within 5 miles of your GPS fix, nearest first. */
function SitePicker({
  options,
  chosenId,
  onChoose,
  isAdmin,
  gps,
  loading,
}: {
  options: SiteOption[];
  chosenId: number | null;
  onChoose: (id: number) => void;
  isAdmin: boolean;
  gps: "ok" | "waiting" | "off";
  loading: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-muted">
        Site {isAdmin ? "(admin: any site)" : `(yours, within ${REPORT_RADIUS_MI} miles of you)`}
      </span>
      <select
        value={chosenId ?? ""}
        onChange={(e) => onChoose(Number(e.target.value))}
        disabled={loading || !options.some((o) => o.eligible)}
        className="w-full rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none disabled:opacity-60"
      >
        {loading && <option value="">Loading your sites…</option>}
        {!loading && !options.some((o) => o.eligible) && (
          <option value="">
            {gps === "ok"
              ? `None of your sites within ${REPORT_RADIUS_MI} mi`
              : gps === "waiting"
                ? "Waiting for your location…"
                : "Turn on location to report"}
          </option>
        )}
        {options.map((o) => (
          <option key={o.site.id} value={o.site.id} disabled={!o.eligible}>
            {o.site.name}
            {o.mi !== null ? ` · ${fmtMiles(o.mi)}` : ""}
            {!o.eligible && o.mi !== null ? " (too far)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
