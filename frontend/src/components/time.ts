/** A received-at timestamp as the reader sees it: UTC, to the second. */
export function checkedAt(iso: string): string {
  return `${iso.replace("T", " ").slice(0, 19)} UTC`;
}

const ET = "America/New_York";
const dayFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: ET, weekday: "short", month: "short", day: "numeric", year: "numeric",
});
const clockFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: ET, hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

/**
 * A market-session timestamp in New York time, with the zone named (PUI §5).
 * The precise UTC value stays available to the caller for a title or detail.
 */
export function marketTime(iso: string): string {
  const at = new Date(iso);
  return `${dayFmt.format(at)}, ${clockFmt.format(at)} ET`;
}

/** A run of decisions: one day with its clock span, or the two days it spans. */
export function marketSpan(firstIso: string, lastIso: string): string {
  const first = new Date(firstIso);
  const last = new Date(lastIso);
  const firstDay = dayFmt.format(first);
  const lastDay = dayFmt.format(last);
  if (firstDay === lastDay) {
    return `${lastDay}, ${clockFmt.format(first)}–${clockFmt.format(last)} ET`;
  }
  return `${firstDay}, ${clockFmt.format(first)} ET – ${lastDay}, ${clockFmt.format(last)} ET`;
}

const utcDayFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC", weekday: "short", month: "short", day: "numeric", year: "numeric",
});

/** A market day the server named (YYYY-MM-DD), as a reader says it. */
export function marketDay(day: string): string {
  return utcDayFmt.format(new Date(`${day}T12:00:00Z`));
}

/**
 * A served decimal, without its padding: "774.830000" reads as "774.83".
 * Only trailing zeros past two places are dropped. Nothing is rounded, so a
 * value recorded to four places still shows four.
 */
export function plain(value: string): string {
  const match = /^(-?\d+\.\d{2}\d*?)0+$/.exec(value);
  return match ? match[1]! : value;
}

/** A served change, with its sign said: "5.190000" reads as "+5.19". */
export function signed(value: string): string {
  const shown = plain(value);
  return shown.startsWith("-") || Number(value) === 0 ? shown : `+${shown}`;
}

/** A served duration in seconds, in the largest two units that fit. */
export function duration(seconds: number): string {
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  if (days > 0) return `${days} d ${hours} h`;
  if (hours > 0) return `${hours} h ${minutes} min`;
  return `${minutes} min`;
}
