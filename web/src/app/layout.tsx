import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { headers } from "next/headers";
import Link from "next/link";
import {
  ClerkProvider,
  Show,
  SignInButton,
  SignUpButton,
  UserButton,
} from "@clerk/nextjs";
import { ClerkAuthSession, DemoAuthSession, DevAuthSession } from "@/lib/auth";
import { isDemoHost, requestHost } from "@/lib/demo";
import "./globals.css";

// Inlined at build time; when absent (CI's `pnpm build`) we render the plain shell
// without Clerk, matching the dev-token seam in src/lib/auth.tsx.
const CLERK_ENABLED = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "boor — AI-assisted D&D tabletop",
  description:
    "A virtual tabletop where a D&D campaign continues even when players are absent — an AI plays their character within limits they set.",
};

function AuthHeader() {
  return (
    <header className="flex items-center justify-between gap-3 border-b border-zinc-200 px-6 py-3 dark:border-zinc-800">
      <Link
        href="/"
        className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50"
      >
        boor
      </Link>
      <div className="flex items-center gap-3">
        {/* Core 3 replaced <SignedIn>/<SignedOut> with a single <Show when=...>. */}
        <Show when="signed-out">
          <SignInButton />
          <SignUpButton />
        </Show>
        <Show when="signed-in">
          <UserButton />
        </Show>
      </div>
    </header>
  );
}

/** The public demo's header (PLAT-DEMO-01): no sign-in, and say plainly what this is. */
function DemoHeader() {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-amber-200 bg-amber-50 px-6 py-3 dark:border-amber-900 dark:bg-amber-950/40">
      <Link
        href="/"
        className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50"
      >
        boor <span className="text-sm font-normal text-amber-700 dark:text-amber-400">demo</span>
      </Link>
      <p className="text-sm text-amber-800 dark:text-amber-300">
        A private sandbox for this browser. Sample data, AI features off, wiped daily.
      </p>
    </header>
  );
}

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // Runtime env + request host: the same deploy serves the demo on its hostname.
  const demo = isDemoHost(requestHost(await headers()), {
    BOOR_DEMO: process.env.BOOR_DEMO,
    DEMO_HOSTNAMES: process.env.DEMO_HOSTNAMES,
  });
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {demo ? (
          <DemoAuthSession>
            <DemoHeader />
            {children}
          </DemoAuthSession>
        ) : CLERK_ENABLED ? (
          <ClerkProvider>
            <ClerkAuthSession>
              <AuthHeader />
              {children}
            </ClerkAuthSession>
          </ClerkProvider>
        ) : (
          <DevAuthSession>{children}</DevAuthSession>
        )}
      </body>
    </html>
  );
}
