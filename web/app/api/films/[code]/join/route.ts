import { NextResponse } from "next/server";
import { randomId } from "@/lib/codes";
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

  const now = Date.now();
  if (now > Date.parse(film.closesAt)) {
    return NextResponse.json({ error: "This film is closed" }, { status: 403 });
  }

  const body = (await request.json()) as { name?: string; guestId?: string };
  if (body.guestId) {
    const existing = film.guests.find((g) => g.id === body.guestId);
    if (existing) {
      return NextResponse.json({ film: publicFilm(film), guest: existing });
    }
  }

  if (film.guests.length >= film.guestCap) {
    return NextResponse.json(
      { error: `This film is full (${film.guestCap} guests)` },
      { status: 403 },
    );
  }

  const name = (body.name ?? "").trim().slice(0, 32);
  if (!name) {
    return NextResponse.json({ error: "Name is required" }, { status: 400 });
  }

  const guest = {
    id: randomId(16),
    name,
    joinedAt: new Date(now).toISOString(),
    shotsTaken: 0,
  };
  film.guests.push(guest);
  await saveFilm(film);
  return NextResponse.json({ film: publicFilm(film), guest });
}
