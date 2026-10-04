import type { Metadata } from "next";

import { GuestApp } from "@/components/guest/GuestApp";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ code: string }>;
}): Promise<Metadata> {
  const { code } = await params;
  const appId = process.env.NEXT_PUBLIC_IOS_APP_STORE_ID;
  if (!appId) return {};

  const webUrl = process.env.NEXT_PUBLIC_WEB_URL ?? "https://filmroll.app";
  return {
    other: {
      "apple-itunes-app": `app-id=${appId}, app-argument=${webUrl}/f/${code}`,
    },
  };
}

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
