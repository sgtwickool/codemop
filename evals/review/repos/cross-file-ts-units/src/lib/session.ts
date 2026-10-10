import { addMinutes } from "date-fns";
import { SESSION_TIMEOUT } from "@/lib/config";

export function sessionExpiry(now: Date): Date {
  return addMinutes(now, SESSION_TIMEOUT);
}

export function isExpired(expiresAt: Date, now = new Date()): boolean {
  return expiresAt <= now;
}
