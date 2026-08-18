import { HostDashboard } from "@/components/HostDashboard";

export default async function HostPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  return (
    <main className="mx-auto flex min-h-full max-w-3xl flex-col p-6">
      <HostDashboard code={code} />
    </main>
  );
}
