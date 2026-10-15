import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Money comes from the API as a decimal string ("200.00"); never parse it into a float for arithmetic. */
export function kina(value: string | null | undefined): string {
  if (value == null) return "–";
  const [whole, cents = "00"] = value.split(".");
  return `K${Number(whole).toLocaleString("en-PG")}.${cents.padEnd(2, "0").slice(0, 2)}`;
}

/** Cents-exact subtraction on decimal strings (amount - refund), for the split preview. */
export function minus(a: string, b: string): string {
  const toCents = (s: string) => {
    const [w, c = "0"] = s.trim().split(".");
    const sign = w.startsWith("-") ? -1 : 1;
    return sign * (Math.abs(Number(w)) * 100 + Number(c.padEnd(2, "0").slice(0, 2)));
  };
  const cents = toCents(a) - toCents(b);
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}

export function isMoney(value: string): boolean {
  return /^\d{1,12}(\.\d{1,2})?$/.test(value.trim());
}

export function compareMoney(a: string, b: string): number {
  return Number(minus(a, b).replace(".", ""));
}

const PNG = "Pacific/Port_Moresby";

export function when(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleString("en-AU", {
    timeZone: PNG, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

/** "in 2 days", "5 hours late" — relative to now, for deadlines. */
export function until(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "";
  const ms = new Date(iso).getTime() - now.getTime();
  const late = ms < 0;
  const mins = Math.round(Math.abs(ms) / 60000);
  const days = Math.round(mins / 1440);
  const text = mins < 60 ? `${mins} min` : mins < 48 * 60 ? `${Math.round(mins / 60)} h` : `${days} day${days === 1 ? "" : "s"}`;
  return late ? `${text} late` : `${text} left`;
}

export function short(id: string): string {
  return id.slice(0, 8);
}
