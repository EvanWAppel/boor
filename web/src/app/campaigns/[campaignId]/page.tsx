import CampaignDetail from "@/components/campaigns/CampaignDetail";

// `params` is a Promise in this Next.js version — await it.
export default async function CampaignPage({ params }: PageProps<"/campaigns/[campaignId]">) {
  const { campaignId } = await params;
  return <CampaignDetail campaignId={campaignId} />;
}
