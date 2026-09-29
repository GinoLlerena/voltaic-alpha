/** A received-at timestamp as the reader sees it: UTC, to the second. */
export function checkedAt(iso: string): string {
  return `${iso.replace("T", " ").slice(0, 19)} UTC`;
}
