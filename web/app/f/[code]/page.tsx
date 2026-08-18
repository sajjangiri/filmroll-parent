import { GuestApp } from "@/components/GuestApp";

export default async function FilmPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  return (
    <main className="mx-auto flex min-h-full max-w-lg flex-col p-6">
      <GuestApp code={code} />
    </main>
  );
}
