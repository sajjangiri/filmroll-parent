import { PrintCards } from "@/components/PrintCards";
import { getFilm } from "@/lib/api";

export default async function PrintPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  let title = code;
  try {
    const film = await getFilm(code);
    title = film.title;
  } catch {
    // The cards still print; the host can write the name by hand.
  }

  return <PrintCards code={code} title={title} />;
}
