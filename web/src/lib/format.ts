import { locale } from "@/lib/i18n";

const dates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric" });
const relative = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });

/** "15 oct. 2026" */
export function formatDate(iso: string): string {
  return dates.format(new Date(iso));
}

/** "il y a 5 minutes", "hier": how long ago, in the largest unit that fits. */
export function formatAgo(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((new Date(iso).getTime() - now.getTime()) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return relative.format(Math.trunc(seconds / size), unit);
  }
  return relative.format(0, "minute");
}
