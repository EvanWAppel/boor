// Clerk auth runs in Next's "proxy" — the Next 16 rename of `middleware` (see
// node_modules/next/dist/docs/.../file-conventions/proxy.md). Clerk's own guidance:
// name the file `proxy.ts` on Next 16+, `middleware.ts` on 15 and below; the body
// is identical either way.
//
// Guarded on the publishable key so a build with Clerk unconfigured (CI, which runs
// `pnpm build` without keys) is a pass-through no-op — mirroring the dev-token seam
// in src/lib/auth.ts, which promises "CI stays green without a Clerk publishable key."
import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

export default process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  ? clerkMiddleware()
  : () => NextResponse.next();

export const config = {
  matcher: [
    // Run on everything except Next internals and static files (Clerk's default).
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes.
    "/(api|trpc)(.*)",
  ],
};
