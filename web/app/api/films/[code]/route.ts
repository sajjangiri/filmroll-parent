import { NextResponse } from "next/server";
import { getFilmByCode, publicFilm } from "@/lib/store";

export async function GET(
  _request: Request,
  context: { params: Promise<{ code: string }> },
) {
  const { code } = await context.params;
  const film = await getFilmByCode(code);
  if (!film) {
    return NextResponse.json({ error: "Film not found" }, { status: 404 });
  }
  return NextResponse.json({ film: publicFilm(film) });
}
