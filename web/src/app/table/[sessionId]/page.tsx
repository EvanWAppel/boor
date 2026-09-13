import SessionRoom from "@/components/table/SessionRoom";

// The live session room. `params` is a Promise in this Next.js version — await it.
export default async function TablePage({ params }: PageProps<"/table/[sessionId]">) {
  const { sessionId } = await params;
  return (
    <div className="flex min-h-0 flex-1 flex-col bg-stone-950 text-stone-100">
      <SessionRoom sessionId={sessionId} />
    </div>
  );
}
