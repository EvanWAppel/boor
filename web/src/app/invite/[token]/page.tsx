import AcceptInvite from "@/components/invite/AcceptInvite";

// `params` is a Promise in this Next.js version — await it.
export default async function InvitePage({ params }: PageProps<"/invite/[token]">) {
  const { token } = await params;
  return <AcceptInvite token={token} />;
}
