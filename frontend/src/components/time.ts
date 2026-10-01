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
