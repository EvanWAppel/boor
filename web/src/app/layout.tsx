import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import {
  ClerkProvider,
  Show,
  SignInButton,
  SignUpButton,
  UserButton,
} from "@clerk/nextjs";
import "./globals.css";

// Inlined at build time; when absent (CI's `pnpm build`) we render the plain shell
// without Clerk, matching the dev-token seam in src/lib/auth.ts.
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

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {CLERK_ENABLED ? (
          <ClerkProvider>
            <AuthHeader />
            {children}
          </ClerkProvider>
        ) : (
          children
        )}
      </body>
    </html>
  );
}
