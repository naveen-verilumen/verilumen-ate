const UNAVAILABLE = "Unavailable";

export function formatRate(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return UNAVAILABLE;
  }
  return `${(value * 100).toFixed(2)}%`;
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return UNAVAILABLE;
  }
  return value.toLocaleString("en-US");
}

export function formatSignedRate(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return UNAVAILABLE;
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(2)}%`;
}

export function formatMetric(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return UNAVAILABLE;
  }
  return value.toFixed(digits);
}

export function authorizedLabel(value: boolean): string {
  return value ? "YES" : "NO";
}

const IST_PARTS = new Intl.DateTimeFormat("en-US", {
  timeZone: "Asia/Kolkata",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

function analysisTimestampParts(value: string): Record<string, string> | null {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  const parts: Record<string, string> = {};
  for (const part of IST_PARTS.formatToParts(date)) {
    if (part.type !== "literal") {
      parts[part.type] = part.value;
    }
  }
  if (!parts.day || !parts.month || !parts.year || !parts.hour || !parts.minute) {
    return null;
  }
  return parts;
}

/** Presentational IST conversion. Source timestamps stay unchanged. */
export function formatAnalysisTimestampIst(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const parts = analysisTimestampParts(value);
  if (!parts) {
    return null;
  }
  const period = (parts.dayPeriod ?? "AM").replace(/\./g, "").toUpperCase();
  return `${parts.day} ${parts.month} ${parts.year}, ${parts.hour}:${parts.minute} ${period} IST`;
}
