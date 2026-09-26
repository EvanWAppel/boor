// Small shared UI primitives for the front-door screens (dashboard, campaign
// detail, invite). Matches the app-shell zinc theme (light/dark), distinct from
// the table's dark stone theme. Inline Tailwind everywhere else; these are just
// the bits repeated across every screen.

"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

import type { MembershipRole, SessionStatus } from "@/lib/types";

/** A centered page container with consistent width + padding. */
export function Page({ children }: { children: ReactNode }) {
  return <main className="mx-auto w-full max-w-3xl flex-1 p-6">{children}</main>;
}

/** A bordered content card. */
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/40 ${className}`}
    >
      {children}
    </div>
  );
}

/** A section heading with an optional right-aligned action. */
export function SectionHeader({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">{title}</h2>
      {action}
    </div>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
};

const BUTTON_VARIANTS: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary:
    "bg-zinc-900 text-white hover:bg-zinc-700 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200",
  secondary:
    "border border-zinc-300 text-zinc-800 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-100 dark:hover:bg-zinc-800",
  danger:
    "border border-rose-300 text-rose-700 hover:bg-rose-50 dark:border-rose-800 dark:text-rose-300 dark:hover:bg-rose-950/40",
};

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${BUTTON_VARIANTS[variant]} ${className}`}
    />
  );
}

/** A styled text input sharing the form look across screens. */
export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 ${props.className ?? ""}`}
    />
  );
}

/** A member's role, as a small pill. */
export function RoleBadge({ role }: { role: MembershipRole }) {
  const label = role === "dm" ? "DM" : "Player";
  const tone =
    role === "dm"
      ? "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300"
      : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300";
  return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${tone}`}>{label}</span>;
}

/** A session's lifecycle status, as a small pill. */
export function StatusBadge({ status }: { status: SessionStatus }) {
  const tone: Record<SessionStatus, string> = {
    active: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
    scheduled: "bg-sky-100 text-sky-800 dark:bg-sky-950/50 dark:text-sky-300",
    ended: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  };
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${tone[status]}`}>{status}</span>
  );
}

/** A dismissable-looking inline error line (rose). */
export function ErrorText({ children }: { children: ReactNode }) {
  if (!children) return null;
  return <p className="text-sm text-rose-600 dark:text-rose-400">{children}</p>;
}
