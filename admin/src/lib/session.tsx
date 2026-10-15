import { createContext, useContext } from "react";
import type { Role, User } from "./types";

export interface Session {
  me: User;
  signOut: () => void;
  notify: (text: string, tone?: "ok" | "error") => void;
}

export const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const s = useContext(SessionContext);
  if (!s) throw new Error("No session");
  return s;
}

/** What each role may open. Admin sees everything (the API enforces the same rules). */
export const ACCESS: Record<string, Role[]> = {
  disputes: ["support", "mediator", "compliance"],
  money: ["finance"],
  reports: ["finance", "compliance"],
  moderation: ["moderator"],
  people: ["support", "kyc", "moderator", "mediator", "finance", "compliance"],
  audit: ["compliance"],
  freezes: ["compliance"],
};

export function can(me: User, area: keyof typeof ACCESS): boolean {
  return me.role === "admin" || ACCESS[area].includes(me.role);
}

export const ROLE_NAMES: Record<Role, string> = {
  user: "Customer", support: "Support", kyc: "KYC review", moderator: "Moderator", mediator: "Mediator",
  finance: "Finance", compliance: "Compliance", admin: "Admin",
};
