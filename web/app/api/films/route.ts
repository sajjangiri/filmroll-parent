import { NextResponse } from "next/server";
import { filmCode, randomId } from "@/lib/codes";
import { publicFilm, saveFilm } from "@/lib/store";
import type { Film } from "@/lib/types";

export async function POST(request: Request) {
  const body = (await request.json()) as {
    title?: string;
    hoursOpen?: number;
    revealHours?: number;
    shotLimit?: number;
    guestCap?: number;
  };

  const title = (body.title ?? "").trim() || "Untitled film";
  const hoursOpen = Math.min(Math.max(body.hoursOpen ?? 24, 1), 168);
  const revealHours = Math.min(Math.max(body.revealHours ?? hoursOpen, 0), 336);
  const shotLimit = Math.min(Math.max(body.shotLimit ?? 8, 1), 40);
  const guestCap = Math.min(Math.max(body.guestCap ?? 5, 1), 200);

  const now = Date.now();
  const film: Film = {
    id: randomId(16),
    code: filmCode(),
    hostSecret: randomId(20),
    title,
    createdAt: new Date(now).toISOString(),
    closesAt: new Date(now + hoursOpen * 3600_000).toISOString(),
    revealAt: new Date(now + revealHours * 3600_000).toISOString(),
    revealed: revealHours === 0,
    shotLimit,
    guestCap,
    guests: [],
    shots: [],
  };

  await saveFilm(film);
  return NextResponse.json({
    film: publicFilm(film),
    hostSecret: film.hostSecret,
  });
}
