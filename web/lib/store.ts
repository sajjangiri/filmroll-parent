import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import type { Film } from "./types";

const DATA_DIR = path.join(process.cwd(), "data");
const FILMS_PATH = path.join(DATA_DIR, "films.json");

async function ensure() {
  await mkdir(DATA_DIR, { recursive: true });
  await mkdir(path.join(process.cwd(), "public", "uploads"), { recursive: true });
}

async function readAll(): Promise<Film[]> {
  await ensure();
  try {
    const raw = await readFile(FILMS_PATH, "utf8");
    return JSON.parse(raw) as Film[];
  } catch {
    return [];
  }
}

async function writeAll(films: Film[]) {
  await ensure();
  await writeFile(FILMS_PATH, JSON.stringify(films, null, 2));
}

export async function listFilms() {
  return readAll();
}

export async function getFilmByCode(code: string) {
  const films = await readAll();
  return films.find((f) => f.code.toLowerCase() === code.toLowerCase()) ?? null;
}

export async function saveFilm(film: Film) {
  const films = await readAll();
  const index = films.findIndex((f) => f.id === film.id);
  if (index >= 0) films[index] = film;
  else films.push(film);
  await writeAll(films);
  return film;
}

export function publicFilm(film: Film) {
  const { hostSecret: _, ...rest } = film;
  return rest;
}
