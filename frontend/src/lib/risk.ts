import type { RiskLevel } from "./api";

// Keep the bands in sync with backend/planit/ml/score.py level_for().
// Status colors from the dataviz palette (dark-surface steps). Always shown with a label or number,
// never color alone. RISK_INK is the text color that reads on each fill.
export const RISK_COLORS: Record<RiskLevel, string> = {
  low: "#0ca30c",
  moderate: "#fab219",
  high: "#ec835a",
  extreme: "#d03b3b",
};

export const RISK_INK: Record<RiskLevel, string> = {
  low: "#0b1130",
  moderate: "#0b1130",
  high: "#0b1130",
  extreme: "#ffffff",
};

export const NO_SCORE_COLOR = "#4a5380";
export const NO_SCORE_INK = "#ffffff";

export const RISK_LABELS: Record<RiskLevel, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  extreme: "Extreme",
};

export const RISK_LEVELS: RiskLevel[] = ["low", "moderate", "high", "extreme"];

/** What each level means for a crew (matches backend/planit/hazards.py LEVEL_GUIDANCE). */
export const RISK_GUIDANCE: Record<RiskLevel, string> = {
  low: "Normal operations",
  moderate: "Work with precautions",
  high: "Restricted work",
  extreme: "Stop non-essential work",
};

/** Same bands as backend level_for(): low < 2.5 <= moderate < 5 <= high < 7.5 <= extreme. */
export function levelFor(score: number): RiskLevel {
  if (score >= 7.5) return "extreme";
  if (score >= 5) return "high";
  if (score >= 2.5) return "moderate";
  return "low";
}
