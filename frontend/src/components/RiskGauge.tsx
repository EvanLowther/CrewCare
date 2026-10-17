import type { RiskLevel } from "@/lib/api";
import { NO_SCORE_COLOR, RISK_COLORS, RISK_LABELS } from "@/lib/risk";

const R = 80;
const CIRC = Math.PI * R; // half circle

/** Half-ring meter for a 0-10 score. The fill carries the level color; the track is the same hue, faint. */
export function RiskGauge({ score, level }: { score: number | null; level: RiskLevel | null }) {
  const color = level ? RISK_COLORS[level] : NO_SCORE_COLOR;
  const filled = score === null ? 0 : Math.max(0.02, Math.min(1, score / 10));
  return (
    <div className="relative mx-auto w-full max-w-[240px]">
      <svg viewBox="0 0 200 110" className="w-full" role="img" aria-label={score === null ? "No risk score yet" : `Risk ${score.toFixed(1)} of 10, ${RISK_LABELS[level!]}`}>
        <path d={`M 20 100 A ${R} ${R} 0 0 1 180 100`} fill="none" stroke={color} strokeOpacity={0.18} strokeWidth={14} strokeLinecap="round" />
        <path
          d={`M 20 100 A ${R} ${R} 0 0 1 180 100`}
          fill="none"
          stroke={color}
          strokeWidth={14}
          strokeLinecap="round"
          strokeDasharray={`${CIRC * filled} ${CIRC}`}
        />
      </svg>
      <div className="absolute inset-x-0 bottom-1 flex flex-col items-center">
        <span className="text-5xl font-semibold leading-none text-ink">{score === null ? "–" : score.toFixed(1)}</span>
        <span className="mt-1 text-xs text-muted">{level ? `${RISK_LABELS[level]} risk · out of 10` : "No score yet"}</span>
      </div>
    </div>
  );
}
