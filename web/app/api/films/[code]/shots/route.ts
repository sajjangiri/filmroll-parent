import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
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

  const form = await request.formData();
  const guestId = String(form.get("guestId") ?? "");
  const file = form.get("photo");
  const guest = film.guests.find((g) => g.id === guestId);
  if (!guest) {
    return NextResponse.json({ error: "Join this film first" }, { status: 403 });
  }
  if (guest.shotsTaken >= film.shotLimit) {
    return NextResponse.json(
      { error: "No shots left on this camera" },
      { status: 403 },
    );
  }
  if (!(file instanceof File) || file.size === 0) {
    return NextResponse.json({ error: "Photo is required" }, { status: 400 });
  }
  if (file.size > 8 * 1024 * 1024) {
    return NextResponse.json({ error: "Photo is too large" }, { status: 400 });
  }

  const shotId = randomId(16);
  const dir = path.join(process.cwd(), "public", "uploads", film.id);
  await mkdir(dir, { recursive: true });
  const filename = `${shotId}.jpg`;
  const buffer = Buffer.from(await file.arrayBuffer());
  await writeFile(path.join(dir, filename), buffer);

  guest.shotsTaken += 1;
  film.shots.push({
    id: shotId,
    guestId: guest.id,
    guestName: guest.name,
    createdAt: new Date(now).toISOString(),
    url: `/uploads/${film.id}/${filename}`,
  });
  await saveFilm(film);
  return NextResponse.json({ film: publicFilm(film), guest });
}
