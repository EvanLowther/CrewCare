import type { RiskLevel } from "./api";

// Keep the bands in sync with backend/planit/ml/score.py level_for().
export const RISK_COLORS: Record<RiskLevel, string> = {
  low: "#16a34a",
  moderate: "#ca8a04",
  high: "#ea580c",
  extreme: "#dc2626",
};

export const RISK_LABELS: Record<RiskLevel, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  extreme: "Extreme",
};
