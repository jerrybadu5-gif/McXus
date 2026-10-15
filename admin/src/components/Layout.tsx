import { Banknote, FileBarChart, Flag, Gavel, Home, Lock, LogOut, ScrollText, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "@/lib/api";
import { can, ROLE_NAMES, useSession } from "@/lib/session";
import type { Overview } from "@/lib/types";
import { cn } from "@/lib/utils";

export function Layout({ children }: { children: React.ReactNode }) {
  const { me, signOut } = useSession();
  const location = useLocation();
  const [counts, setCounts] = useState<Overview | null>(null);
  useEffect(() => { api.get<Overview>("/v1/admin/overview").then(setCounts, () => {}); }, [location.pathname]);

  const waiting = counts ? {
    disputes: (counts.disputes.mediation ?? 0) + (counts.disputes.appeal ?? 0),
    money: counts.deposits_pending + counts.withdrawals_requested,
    moderation: counts.reports_open + counts.content_reports_open,
    freezes: counts.freeze_appeals,
  } : null;

  const items = [
    { to: "/", label: "Home", icon: Home, show: true, end: true },
    { to: "/disputes", label: "Disputes", icon: Gavel, show: can(me, "disputes"), count: waiting?.disputes, late: counts?.disputes_overdue },
    { to: "/money", label: "Deposits & payouts", icon: Banknote, show: can(me, "money"), count: waiting?.money },
    { to: "/moderation", label: "Reports", icon: Flag, show: can(me, "moderation"), count: waiting?.moderation },
    { to: "/people", label: "People", icon: Users, show: can(me, "people") },
    { to: "/freezes", label: "Frozen accounts", icon: Lock, show: can(me, "freezes"), count: waiting?.freezes },
    { to: "/reports", label: "Money reports", icon: FileBarChart, show: can(me, "reports") },
    { to: "/audit", label: "Staff activity", icon: ScrollText, show: can(me, "audit") },
  ];

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <nav aria-label="Main" className="flex shrink-0 flex-col bg-navy text-navy-muted md:sticky md:top-0 md:h-screen md:w-60">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <img src="/icon.svg" alt="" className="h-8 w-8" />
          <div className="flex-1 leading-tight">
            <p className="font-bold text-white">McXus staff</p>
            <p className="text-2xs">Sandbox · Stars are not real money</p>
          </div>
          {/* On narrow windows the account box below is hidden, so sign-out lives here. */}
          <button onClick={signOut} className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs hover:bg-navy-soft hover:text-white md:hidden" title={me.display_name || me.phone || ""}>
            <LogOut size={14} />Sign out
          </button>
        </div>
        <ul className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:overflow-visible">
          {items.filter((i) => i.show).map((i) => (
            <li key={i.to} className="shrink-0">
              <NavLink to={i.to} end={i.end}
                className={({ isActive }) => cn("flex items-center gap-2.5 rounded-lg px-3 py-2 font-medium hover:bg-navy-soft hover:text-white",
                  isActive && "bg-navy-soft text-white")}>
                <i.icon size={16} aria-hidden />
                <span className="flex-1 whitespace-nowrap">{i.label}</span>
                {!!i.late && <span className="num rounded bg-late px-1.5 text-2xs font-bold text-white" title="Past the mediator deadline">{i.late} late</span>}
                {!!i.count && <span className="num rounded bg-gold px-1.5 text-2xs font-bold text-ink" title="Waiting">{i.count}</span>}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="mt-auto hidden border-t border-navy-line px-5 py-4 md:block">
          <p className="truncate font-semibold text-white">{me.display_name || me.phone}</p>
          <p className="text-2xs">{ROLE_NAMES[me.role]}</p>
          <button onClick={signOut} className="mt-3 flex items-center gap-1.5 text-xs hover:text-white"><LogOut size={14} />Sign out</button>
        </div>
      </nav>
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}

export function PageHead({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3 border-b border-line bg-white px-6 py-5">
      <h1 className="text-xl font-bold">{title}</h1>
      {children}
    </header>
  );
}
