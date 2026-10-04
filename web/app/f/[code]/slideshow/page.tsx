import type { Metadata } from "next";
import { Slideshow } from "@/components/guest/Slideshow";

export const metadata: Metadata = {
  title: "Filmroll slideshow",
};

export default async function SlideshowPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  return <Slideshow code={code} />;
}
