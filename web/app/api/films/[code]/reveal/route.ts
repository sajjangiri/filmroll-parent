import { NextResponse } from "next/server";
import { getFilmByCode, publicFilm, saveFilm } from "@/lib/store";

export async function POST(
  request: Request,
  context: { params: Promise<{ code: string }> },
) {
  const { code } = await context.params;
  const film = await getFilmByCode(code);
  if (!film) {
    return NextResponse.json({ error: "Film not found" }, { status: 404 });
  }

  const body = (await request.json()) as { hostSecret?: string };
  if (body.hostSecret !== film.hostSecret) {
    return NextResponse.json({ error: "Not the host" }, { status: 403 });
  }

  film.revealed = true;
  film.revealAt = new Date().toISOString();
  await saveFilm(film);
  return NextResponse.json({ film: publicFilm(film) });
}
