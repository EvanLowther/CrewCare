"use client";

// Site-page charts. Every chart is ONE series (no legend needed, the card title names it):
// 2px line in the accent, ~10% area wash, hairline solid grid, muted axis text, crosshair tooltip.
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Conditions, RiskLevel, RiskPoint } from "@/lib/api";
import { siteDay, siteHour } from "@/lib/format";
import { RISK_LABELS } from "@/lib/risk";

const ACCENT = "#6e7bff";
const GRID = "#1f2a58";
const MUTED = "#7a84ae";
const AXIS_TICK = { fill: MUTED, fontSize: 11 };
const HOUR = 3_600_000;

type TooltipRow = { label: string; value: string };

function ChartTooltip({ title, rows }: { title: string; rows: TooltipRow[] }) {
  return (
    <div className="rounded-lg border border-line bg-raised px-3 py-2 shadow-xl">
      <p className="text-xs text-muted">{title}</p>
      {rows.map((r) => (
        <p key={r.label} className="mt-1 flex items-center gap-2 text-xs text-ink-2">
          <span className="h-0.5 w-3 rounded-full bg-accent" aria-hidden />
          <span className="tabular text-sm font-semibold text-ink">{r.value}</span>
          {r.label}
        </p>
      ))}
    </div>
  );
}

function timeTicks(start: number, end: number, stepHours: number, timeZone: string): number[] {
  // Ticks on whole site-local hours that are multiples of the step (e.g. 12 AM, 6 AM, 12 PM, 6 PM).
  const ticks: number[] = [];
  for (let t = Math.ceil(start / HOUR) * HOUR; t <= end; t += HOUR) {
    const hour = Number(new Date(t).toLocaleString("en-US", { hour: "numeric", hour12: false, timeZone }));
    if (hour % stepHours === 0) ticks.push(t);
  }
  return ticks;
}

function hourLabel(t: number, timeZone: string): string {
  const iso = new Date(t).toISOString();
  const label = siteHour(iso, timeZone);
  return label === "12 AM" ? siteDay(iso, timeZone) : label;
}

/** Risk score from 24 h ago to 24 h ahead: solid line for scored hours, dashed for the forecast. */
export function RiskHistoryChart({ points, timeZone, now }: { points: RiskPoint[]; timeZone: string; now: number }) {
  const data = points
    .filter((p) => (p.kind === "current" ? true : new Date(p.ts).getTime() > now))
    .map((p) => ({ t: new Date(p.ts).getTime(), score: p.score, kind: p.kind, level: p.level as RiskLevel }))
    .sort((a, b) => a.t - b.t);
  // Split into two keys so the forecast can be dashed; the last scored point starts the forecast line.
  const lastPast = [...data].reverse().find((d) => d.kind === "current");
  const rows = data.map((d) => ({
    t: d.t,
    level: d.level,
    past: d.kind === "current" ? d.score : null,
    future: d.kind === "forecast" || d === lastPast ? d.score : null,
  }));
  const start = now - 24 * HOUR;
  const end = now + 24 * HOUR;

  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={rows} margin={{ top: 16, right: 16, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="riskWash" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={ACCENT} stopOpacity={0.28} />
            <stop offset="100%" stopColor={ACCENT} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          scale="time"
          domain={[start, end]}
          ticks={timeTicks(start, end, 6, timeZone)}
          tickFormatter={(t: number) => hourLabel(t, timeZone)}
          tick={AXIS_TICK}
          axisLine={{ stroke: GRID }}
          tickLine={false}
        />
        <YAxis domain={[0, 10]} ticks={[0, 2.5, 5, 7.5, 10]} tick={AXIS_TICK} axisLine={false} tickLine={false} width={44} />
        <ReferenceLine x={now} stroke={MUTED} strokeDasharray="3 3" label={{ value: "Now", fill: MUTED, fontSize: 11, position: "top" }} />
        <Tooltip
          cursor={{ stroke: MUTED, strokeWidth: 1 }}
          content={({ active, payload }) => {
            const row = payload?.[0]?.payload as (typeof rows)[number] | undefined;
            if (!active || !row) return null;
            const score = row.past ?? row.future;
            return (
              <ChartTooltip
                title={`${siteDay(new Date(row.t).toISOString(), timeZone)} ${siteHour(new Date(row.t).toISOString(), timeZone)}${row.past === null ? " · forecast" : ""}`}
                rows={[{ label: `${RISK_LABELS[row.level]} risk`, value: score?.toFixed(1) ?? "–" }]}
              />
            );
          }}
        />
        <Area dataKey="past" type="monotone" stroke={ACCENT} strokeWidth={2} fill="url(#riskWash)" connectNulls={false} isAnimationActive={false} dot={false} activeDot={{ r: 4, stroke: "#111a3d", strokeWidth: 2, fill: ACCENT }} />
        <Area dataKey="future" type="monotone" stroke={ACCENT} strokeWidth={2} strokeDasharray="5 4" fill="url(#riskWash)" fillOpacity={0.5} connectNulls={false} isAnimationActive={false} dot={false} activeDot={{ r: 4, stroke: "#111a3d", strokeWidth: 2, fill: ACCENT }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function forecastRows(forecast: Conditions[]) {
  return forecast.map((c) => ({ t: new Date(c.ts).getTime(), heat: c.heat_index_f, rain: c.precip_prob_pct }));
}

/** Heat index for the next 48 h, with the OSHA "extreme caution" line at 103°F. */
export function HeatIndexChart({ forecast, timeZone }: { forecast: Conditions[]; timeZone: string }) {
  const rows = forecastRows(forecast);
  if (rows.length === 0) return null;
  const start = rows[0].t;
  const end = rows[rows.length - 1].t;
  const values = rows.map((r) => r.heat ?? 0);
  const lo = Math.floor((Math.min(...values) - 5) / 10) * 10;
  const hi = Math.max(110, Math.ceil((Math.max(...values) + 5) / 10) * 10);

  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={rows} margin={{ top: 16, right: 16, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="heatWash" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={ACCENT} stopOpacity={0.24} />
            <stop offset="100%" stopColor={ACCENT} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          scale="time"
          domain={[start, end]}
          ticks={timeTicks(start, end, 12, timeZone)}
          tickFormatter={(t: number) => hourLabel(t, timeZone)}
          tick={AXIS_TICK}
          axisLine={{ stroke: GRID }}
          tickLine={false}
        />
        <YAxis domain={[lo, hi]} tick={AXIS_TICK} axisLine={false} tickLine={false} width={44} tickFormatter={(v: number) => `${v}°`} />
        <ReferenceLine y={103} stroke="#ec835a" strokeDasharray="4 4" label={{ value: "103°F extreme caution", fill: MUTED, fontSize: 11, position: "insideTopRight" }} />
        <Tooltip
          cursor={{ stroke: MUTED, strokeWidth: 1 }}
          content={({ active, payload }) => {
            const row = payload?.[0]?.payload as (typeof rows)[number] | undefined;
            if (!active || !row) return null;
            const iso = new Date(row.t).toISOString();
            return <ChartTooltip title={`${siteDay(iso, timeZone)} ${siteHour(iso, timeZone)}`} rows={[{ label: "heat index", value: row.heat === null ? "–" : `${Math.round(row.heat)}°F` }]} />;
          }}
        />
        <Area dataKey="heat" type="monotone" stroke={ACCENT} strokeWidth={2} fill="url(#heatWash)" isAnimationActive={false} dot={false} activeDot={{ r: 4, stroke: "#111a3d", strokeWidth: 2, fill: ACCENT }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** Chance of rain per hour for the next 48 h (columns from one baseline, rounded tops). */
export function RainChanceChart({ forecast, timeZone }: { forecast: Conditions[]; timeZone: string }) {
  const rows = forecastRows(forecast);
  if (rows.length === 0) return null;
  const start = rows[0].t;
  const end = rows[rows.length - 1].t;

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={rows} margin={{ top: 16, right: 16, bottom: 0, left: 0 }} barCategoryGap={2}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          scale="time"
          domain={[start - HOUR / 2, end + HOUR / 2]}
          ticks={timeTicks(start, end, 12, timeZone)}
          tickFormatter={(t: number) => hourLabel(t, timeZone)}
          tick={AXIS_TICK}
          axisLine={{ stroke: GRID }}
          tickLine={false}
        />
        <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={AXIS_TICK} axisLine={false} tickLine={false} width={44} tickFormatter={(v: number) => `${v}%`} />
        <Tooltip
          cursor={{ fill: "rgb(110 123 255 / 0.08)" }}
          content={({ active, payload }) => {
            const row = payload?.[0]?.payload as (typeof rows)[number] | undefined;
            if (!active || !row) return null;
            const iso = new Date(row.t).toISOString();
            return <ChartTooltip title={`${siteDay(iso, timeZone)} ${siteHour(iso, timeZone)}`} rows={[{ label: "chance of rain", value: row.rain === null ? "–" : `${Math.round(row.rain)}%` }]} />;
          }}
        />
        <Bar dataKey="rain" fill={ACCENT} radius={[3, 3, 0, 0]} maxBarSize={24} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
