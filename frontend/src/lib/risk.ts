import type { RiskLevel } from "./api";

// Keep the bands in sync with backend/planit/ml/score.py level_for().
// Status colors for the near-black "Skyline" theme (also --color-risk-* in globals.css). Always shown with a label
// or number, never color alone. RISK_INK is the text color that reads on each fill (dark on all four).
export const RISK_COLORS: Record<RiskLevel, string> = {
  low: "#3fbf7f",
  moderate: "#f5b83d",
  high: "#f0804f",
  extreme: "#ff4a4a",
};

export const RISK_INK: Record<RiskLevel, string> = {
  low: "#06080c",
  moderate: "#06080c",
  high: "#06080c",
  extreme: "#06080c",
};

/** Lighter tint of each level for text on the dark page (e.g. "EXTREME" next to a score). */
export const RISK_TEXT: Record<RiskLevel, string> = {
  low: "#7fdcae",
  moderate: "#ffd27a",
  high: "#ffad85",
  extreme: "#ff8a8a",
};

export const NO_SCORE_COLOR = "#4a5368";
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
