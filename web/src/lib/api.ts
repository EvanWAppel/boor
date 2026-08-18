// Typed client for the boor FastAPI service.
//
// Auth-provider-agnostic on purpose: it takes a `getToken` callback rather than
// importing Clerk, so it stays testable and adds no runtime dependency. Wire it up
// once Clerk is configured (see CLERK-SETUP.md):
//
//   const { getToken } = useAuth();            // @clerk/nextjs
//   const api = createApiClient({ baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL!, getToken });
//   const me = await api.me();

import type {
  AcceptResult,
  Campaign,
  Character,
  CharacterCreate,
  Invite,
  Me,
  Member,
  MembershipRole,
  Profile,
  ProfileInput,
  RedLine,
  RedLineInput,
} from "./types";

export type TokenGetter = () => Promise<string | null> | string | null;

export interface ApiClientOptions {
  /** Base URL of the service, e.g. http://localhost:8000 (no trailing slash). */
  baseUrl: string;
  /** Returns the current Clerk session token, or null when signed out. */
  getToken: TokenGetter;
}

/** Thrown for any non-2xx response; `detail` carries the service's message. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
  }
}

export function createApiClient({ baseUrl, getToken }: ApiClientOptions) {
  async function request<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const token = await getToken();
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;

    const res = await fetch(`${baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });

    if (!res.ok) {
      throw new ApiError(res.status, await extractDetail(res));
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  return {
    // account
    me: () => request<Me>("GET", "/me"),

    // campaigns
    listCampaigns: () => request<Campaign[]>("GET", "/campaigns"),
    createCampaign: (name: string) =>
      request<Campaign>("POST", "/campaigns", { name }),
    listMembers: (campaignId: string) =>
      request<Member[]>("GET", `/campaigns/${campaignId}/members`),
    removeMember: (campaignId: string, userId: string) =>
      request<void>("DELETE", `/campaigns/${campaignId}/members/${userId}`),

    // invites
    createInvite: (
      campaignId: string,
      email: string,
      role: MembershipRole = "player",
    ) => request<Invite>("POST", `/campaigns/${campaignId}/invites`, { email, role }),
    acceptInvite: (token: string) =>
      request<AcceptResult>("POST", `/invites/${token}/accept`),

    // characters
    listCharacters: (campaignId: string) =>
      request<Character[]>("GET", `/campaigns/${campaignId}/characters`),
    createCharacter: (campaignId: string, character: CharacterCreate) =>
      request<Character>("POST", `/campaigns/${campaignId}/characters`, character),
    getCharacter: (characterId: string) =>
      request<Character>("GET", `/characters/${characterId}`),

    // stand-in personality profile + red lines
    getProfile: (characterId: string) =>
      request<Profile>("GET", `/characters/${characterId}/profile`),
    setProfile: (characterId: string, profile: ProfileInput) =>
      request<Profile>("PUT", `/characters/${characterId}/profile`, profile),
    listRedLines: (characterId: string) =>
      request<RedLine[]>("GET", `/characters/${characterId}/red-lines`),
    addRedLine: (characterId: string, redLine: RedLineInput) =>
      request<RedLine>("POST", `/characters/${characterId}/red-lines`, redLine),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;

async function extractDetail(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
  } catch {
    // non-JSON body — fall through to the status text
  }
  return res.statusText;
}
