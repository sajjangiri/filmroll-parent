import { Gallery } from "@/components/guest/Gallery";

export default async function GalleryPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  return <Gallery code={code} />;
}
