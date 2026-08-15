export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-4xl font-semibold tracking-tight text-black dark:text-zinc-50">
        boor
      </h1>
      <p className="max-w-md text-lg leading-8 text-zinc-600 dark:text-zinc-400">
        An AI-assisted D&amp;D virtual tabletop where the campaign continues even
        when players are away.
      </p>
      <p className="text-sm text-zinc-500">Scaffold — the table is coming.</p>
    </main>
  );
}
