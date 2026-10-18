"use client";

import { Crosshair, Loader2, MapPin } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useState } from "react";
import type { LatLng } from "./ReportPinMap";

const PinMap = dynamic(() => import("./ReportPinMap"), {
  ssr: false,
  loading: () => <div className="flex h-full items-center justify-center text-sm text-muted">Loading map…</div>,
});

export type SiteFormValues = { name: string; description: string; latitude: number; longitude: number };

const inputClass =
  "w-full rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none";

/** Name, description and a map pin. Used to create a site and to edit one. */
export function SiteForm({
  initial,
  submitLabel,
  onSubmit,
}: {
  initial?: SiteFormValues;
  submitLabel: string;
  onSubmit: (values: SiteFormValues) => Promise<void>;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [pin, setPin] = useState<LatLng | null>(initial ? { lat: initial.latitude, lng: initial.longitude } : null);
  const [recenterKey, setRecenterKey] = useState(0);
  const [locating, setLocating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const locate = useCallback(() => {
    if (!navigator.geolocation) return setError("This browser can't share its location. Tap the map instead.");
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setPin({ lat: p.coords.latitude, lng: p.coords.longitude });
        setRecenterKey((k) => k + 1);
        setLocating(false);
      },
      () => {
        setError("Couldn't get your location. Tap the map where the site is.");
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 15_000 },
    );
  }, []);

  const ready = name.trim().length >= 2 && pin !== null && !saving;

  async function submit() {
    if (!pin) return;
    setSaving(true);
    setError(null);
    try {
      await onSubmit({ name: name.trim(), description: description.trim(), latitude: pin.lat, longitude: pin.lng });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save the site");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="flex flex-col overflow-hidden rounded-xl border border-line">
        <div className="flex items-center justify-between gap-2 px-4 py-3">
          <p className="flex items-center gap-1.5 text-sm text-ink">
            <MapPin className="h-4 w-4 text-accent" aria-hidden /> Where is the site?
          </p>
          <button
            type="button"
            onClick={locate}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs text-ink-2 hover:text-ink"
          >
            {locating ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Crosshair className="h-3.5 w-3.5" aria-hidden />}
            My location
          </button>
        </div>
        <div className="h-72 border-t border-line sm:h-80">
          <PinMap position={pin} gps={null} accuracyM={null} recenterKey={recenterKey} sites={[]} onMove={setPin} />
        </div>
        <p className="px-4 py-2 text-xs text-muted">
          {pin ? `${pin.lat.toFixed(5)}, ${pin.lng.toFixed(5)} · drag the pin or tap the map to move it` : "Tap the map, or use your location"}
        </p>
      </div>

      <div className="space-y-4">
        <label className="block">
          <span className="mb-1.5 block text-xs font-medium text-muted">Site name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="e.g. Riverside substation rebuild" className={inputClass} />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-xs font-medium text-muted">Description (shown on the site page)</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={5}
            maxLength={2000}
            placeholder="What's being built, access notes, hazards crews should know about…"
            className={inputClass}
          />
        </label>
        {error && <p className="rounded-lg bg-[rgb(255_74_74/0.12)] px-3 py-2 text-sm text-[#ff9b9b]">{error}</p>}
        <button
          type="button"
          onClick={submit}
          disabled={!ready}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent-strong px-4 py-2.5 text-sm font-semibold text-on-accent hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
        >
          {saving && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
          {submitLabel}
        </button>
        {!ready && !saving && (
          <p className="text-center text-xs text-muted">{name.trim().length < 2 ? "Give the site a name" : "Put the pin on the site"}</p>
        )}
      </div>
    </div>
  );
}
