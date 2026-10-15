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

/** A lap time as timing screens show it: "1:20.901". */
export function formatLapTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = (seconds - minutes * 60).toFixed(3).padStart(6, "0");
  return minutes ? `${minutes}:${rest}` : rest;
}

/** A race time: "1:13:24.325". */
export function formatRaceTime(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  if (!hours) return formatLapTime(seconds);
  const rest = seconds - hours * 3600;
  const minutes = Math.floor(rest / 60);
  return `${hours}:${String(minutes).padStart(2, "0")}:${(rest - minutes * 60).toFixed(3).padStart(6, "0")}`;
}

/** A gap behind: "+19.207", "+1:02.519". */
export function formatGap(seconds: number): string {
  return `+${formatLapTime(seconds)}`;
}

const durations = new Intl.NumberFormat(locale, { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const temperatures = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
const points = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });

/** A duration in seconds, in French: "24,4 s". */
export function formatSeconds(seconds: number): string {
  return `${durations.format(seconds)} s`;
}

/** "26 °C" */
export function formatTemperature(celsius: number): string {
  return `${temperatures.format(celsius)} °C`;
}

/** Points, half points kept: "25", "0,5". */
export function formatPoints(value: number): string {
  return points.format(value);
}
