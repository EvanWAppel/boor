// Public demo (PLAT-DEMO-01): the same deploy serves a sign-in-free demo when the
// request's host is the demo hostname. Pure helpers, shared by the proxy, the root
// layout (server) and the demo auth session (browser).
//
// On the demo host, Clerk is skipped entirely and each browser plays as a guest:
// a random id kept in localStorage, sent to the service as `Bearer demo.<id>`. The
// service recognizes demo requests by their Origin (the demo host) and serves them
// from a separate sandbox schema with AI off — so a demo page can never reach real
// data, whatever it sends.

/** The public demo hostname; override (comma-separated) with DEMO_HOSTNAMES. */
export const DEFAULT_DEMO_HOSTS = ["boor-demo.evanappel.me"];

/** localStorage key holding this browser's guest id. */
export const GUEST_KEY = "boor_demo_guest";

export interface DemoEnv {
  /** Local switch: "1" makes every host the demo (development only; off by default). */
  BOOR_DEMO?: string;
  DEMO_HOSTNAMES?: string;
}

function demoHosts(env: DemoEnv): string[] {
  if (env.DEMO_HOSTNAMES === undefined) return DEFAULT_DEMO_HOSTS;
  return env.DEMO_HOSTNAMES.split(",")
    .map((h) => h.trim().toLowerCase())
    .filter(Boolean);
}

export function isDemoHost(host: string | null, env: DemoEnv): boolean {
  if (env.BOOR_DEMO === "1") return true;
  if (!host) return false;
  const name = host.split(":")[0].toLowerCase();
  return demoHosts(env).includes(name);
}

/** The host the visitor asked for (the edge's forwarded host, else Host). */
export function requestHost(headers: Pick<Headers, "get">): string | null {
  return headers.get("x-forwarded-host") ?? headers.get("host");
}

const GUEST_ID = /^[0-9a-f]{32}$/;

/** A fresh guest id: 32 lowercase hex characters. */
export function randomGuestId(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

/** This browser's guest token, minting and storing an id on first use. */
export function guestToken(
  storage: Pick<Storage, "getItem" | "setItem"> | null,
  newId: () => string = randomGuestId,
): string {
  let id = storage?.getItem(GUEST_KEY) ?? null;
  if (!id || !GUEST_ID.test(id)) {
    id = newId();
    storage?.setItem(GUEST_KEY, id);
  }
  return `demo.${id}`;
}
