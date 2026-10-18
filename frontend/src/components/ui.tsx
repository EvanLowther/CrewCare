// Shared building blocks for the dark dashboard look. Server- and client-safe (no hooks).
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import type { Alert, RiskLevel } from "@/lib/api";
import { SEVERITY_LABELS, SEVERITY_STYLES } from "@/lib/alerts";
import { NO_SCORE_COLOR, NO_SCORE_INK, RISK_COLORS, RISK_INK, RISK_LABELS } from "@/lib/risk";

/** Padded, centered page body for every page except the full-bleed dashboard and the site page. */
export function PageBody({ children }: { children: ReactNode }) {
  return <main className="mx-auto w-full max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-line bg-card ${className}`}>{children}</section>;
}

export function CardHeader({
  title,
  subtitle,
  icon: Icon,
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  icon?: LucideIcon;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4 pb-3">
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
          {Icon && <Icon className="h-4 w-4 text-accent" aria-hidden />}
          {title}
        </h2>
        {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      </div>
      {actions}
    </header>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="font-display text-5xl leading-[0.95] font-extrabold text-ink">{title}</h1>
        {subtitle && <div className="mt-1 text-sm text-ink-2">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function StatTile({
  label,
  value,
  icon: Icon,
  detail,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  icon: LucideIcon;
  detail?: ReactNode;
  tone?: "default" | "danger";
}) {
  return (
    <Card className="px-5 py-4">
      <div className="flex items-center gap-2 text-xs text-ink-2">
        <span
          className={`flex h-6 w-6 items-center justify-center rounded-md ${
            tone === "danger" ? "bg-[rgb(255_74_74/0.18)] text-[#ff8a8a]" : "bg-accent-soft text-accent"
          }`}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden />
        </span>
        {label}
      </div>
      <div className="mt-3 font-display text-4xl leading-none font-extrabold text-ink">{value}</div>
      {detail && <div className="mt-1 text-xs text-muted">{detail}</div>}
    </Card>
  );
}

export function SeverityBadge({ severity }: { severity: Alert["severity"] }) {
  const s = SEVERITY_STYLES[severity];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium"
      style={{ background: s.bg, color: s.fg }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.dot }} aria-hidden />
      {SEVERITY_LABELS[severity]}
    </span>
  );
}

/** Score chip in the risk color; always shows the number, so color never carries meaning alone. */
export function ScoreChip({ score, level, size = "md" }: { score: number | null; level: RiskLevel | null; size?: "md" | "lg" }) {
  const bg = level ? RISK_COLORS[level] : NO_SCORE_COLOR;
  const fg = level ? RISK_INK[level] : NO_SCORE_INK;
  const dims = size === "lg" ? "h-10 w-14 text-base" : "h-8 w-11 text-sm";
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-lg font-bold ${dims}`}
      style={{ background: bg, color: fg }}
      title={level ? `${RISK_LABELS[level]} risk` : "No score yet"}
    >
      {score === null ? "–" : score.toFixed(1)}
    </span>
  );
}

export function RiskLegend() {
  return (
    <ul className="flex flex-wrap items-center gap-3 text-xs text-ink-2" aria-label="Risk levels">
      {(Object.keys(RISK_COLORS) as RiskLevel[]).map((level) => (
        <li key={level} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: RISK_COLORS[level] }} aria-hidden />
          {RISK_LABELS[level]}
        </li>
      ))}
    </ul>
  );
}

export function LiveIndicator({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1 text-xs text-ink-2">
      <span className="live-dot" aria-hidden />
      {label}
    </span>
  );
}

export function EmptyState({ icon: Icon, title, detail }: { icon: LucideIcon; title: string; detail?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-accent-soft text-accent">
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <p className="text-sm font-medium text-ink">{title}</p>
      {detail && <p className="max-w-sm text-xs text-muted">{detail}</p>}
    </div>
  );
}

/** `retrying`: the page polls, so say it will try again on its own. */
export function ErrorBanner({ message, retrying = false }: { message: string; retrying?: boolean }) {
  return (
    <p role="alert" className="rounded-lg border border-[rgb(255_74_74/0.4)] bg-[rgb(255_74_74/0.12)] px-4 py-2 text-sm text-[#ff9b9b]">
      {message}
      {retrying && " Retrying automatically."}
    </p>
  );
}
