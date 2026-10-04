/**
 * Client for the Filmroll API.
 *
 * Same contract as the web app: the phone talks to FastAPI and uploads photo
 * bytes straight to object storage with a presigned PUT. Nothing proxies the
 * image through Expo.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import { FileSystemUploadType, uploadAsync } from "expo-file-system/legacy";

import type {
  CommitResponse,
  ExportResponse,
  FilmCreated,
  FilmDeleted,
  FilmPublic,
  GalleryResponse,
  HostAccount,
  JoinResponse,
  ReportReason,
  ReportResponse,
  ReserveResponse,
  ShotKind,
  ReviewResponse,
  SeatClaimed,
  SeatCreated,
  SeatsResponse,
  StaffRole,
} from "./types";

export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";
export const WEB_URL = process.env.EXPO_PUBLIC_WEB_URL ?? "http://localhost:3000";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  init: RequestInit & { token?: string } = {},
): Promise<T> {
  const { token, headers, ...rest } = init;
  const response = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: {
      ...(rest.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body.
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const guestKey = (code: string) => `filmroll-guest-${code}`;
const hostKey = (code: string) => `filmroll-host-${code}`;
const hostedFilmsKey = "filmroll-hosted-films";
const hostNameKey = "filmroll-host-name";
const deletedKey = (code: string) => `filmroll-deleted-${code}`;
const roleKey = (code: string) => `filmroll-role-${code}`;

export type HostedFilm = { code: string; title: string };

export async function saveHostName(name: string): Promise<void> {
  await AsyncStorage.setItem(hostNameKey, name);
}

export async function loadHostName(): Promise<string | null> {
  return AsyncStorage.getItem(hostNameKey);
}

export async function saveGuestToken(code: string, token: string): Promise<void> {
  await AsyncStorage.setItem(guestKey(code), token);
}

export async function loadGuestToken(code: string): Promise<string | null> {
  return AsyncStorage.getItem(guestKey(code));
}

export async function clearGuestToken(code: string): Promise<void> {
  await AsyncStorage.removeItem(guestKey(code));
}

export async function saveHostToken(code: string, token: string): Promise<void> {
  await AsyncStorage.setItem(hostKey(code), token);
}

export async function loadHostToken(code: string): Promise<string | null> {
  return AsyncStorage.getItem(hostKey(code));
}

export async function rememberHostedFilm(code: string, title: string): Promise<void> {
  const raw = await AsyncStorage.getItem(hostedFilmsKey);
  const list: HostedFilm[] = raw ? (JSON.parse(raw) as HostedFilm[]) : [];
  const next = [{ code, title }, ...list.filter((film) => film.code !== code)].slice(0, 20);
  await AsyncStorage.setItem(hostedFilmsKey, JSON.stringify(next));
}

export async function listHostedFilms(): Promise<HostedFilm[]> {
  const raw = await AsyncStorage.getItem(hostedFilmsKey);
  return raw ? (JSON.parse(raw) as HostedFilm[]) : [];
}

// Which seat this phone holds. The API enforces the boundary either way; this
// only decides which controls are worth rendering.
export async function saveStaffRole(code: string, role: StaffRole): Promise<void> {
  await AsyncStorage.setItem(roleKey(code), role);
}

export async function loadStaffRole(code: string): Promise<StaffRole> {
  const saved = await AsyncStorage.getItem(roleKey(code));
  return saved === "cohost" || saved === "photographer" ? saved : "host";
}

// A deleted film is a 404 to every request, so the host screen cannot learn that
// a restore is still possible. This is the note the deleting phone leaves itself;
// the API is what actually enforces the deadline.
export async function saveDeleted(code: string, deleted: FilmDeleted): Promise<void> {
  await AsyncStorage.setItem(deletedKey(code), JSON.stringify(deleted));
}

export async function loadDeleted(code: string): Promise<FilmDeleted | null> {
  const raw = await AsyncStorage.getItem(deletedKey(code));
  if (!raw) return null;
  try {
    return JSON.parse(raw) as FilmDeleted;
  } catch {
    return null;
  }
}

export async function clearDeleted(code: string): Promise<void> {
  await AsyncStorage.removeItem(deletedKey(code));
}

export function createFilm(input: {
  title: string;
  event_type: string;
  closes_at: string;
  reveal_at?: string | null;
  instant_reveal?: boolean;
  shared_gallery?: boolean;
  shot_limit: number;
  guest_cap: number;
  host_email?: string;
}): Promise<FilmCreated> {
  return request<FilmCreated>("/v1/films", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getFilm(code: string): Promise<FilmPublic> {
  return request<FilmPublic>(`/v1/films/${code}`);
}

export function joinFilm(
  code: string,
  displayName: string,
  joinPin?: string,
): Promise<JoinResponse> {
  return request<JoinResponse>(`/v1/films/${code}/join`, {
    method: "POST",
    body: JSON.stringify({ display_name: displayName, join_pin: joinPin ?? null }),
  });
}

export function setJoinPin(code: string, hostToken: string, pin: string): Promise<FilmPublic> {
  return request<FilmPublic>(`/v1/films/${code}/pin`, {
    method: "PUT",
    token: hostToken,
    body: JSON.stringify({ pin }),
  });
}

export function clearJoinPin(code: string, hostToken: string): Promise<FilmPublic> {
  return request<FilmPublic>(`/v1/films/${code}/pin`, {
    method: "DELETE",
    token: hostToken,
  });
}

export function deleteFilm(code: string, hostToken: string): Promise<FilmDeleted> {
  return request<FilmDeleted>(`/v1/films/${code}`, {
    method: "DELETE",
    token: hostToken,
  });
}

export function restoreFilm(code: string, hostToken: string): Promise<FilmPublic> {
  return request<FilmPublic>(`/v1/films/${code}/restore`, {
    method: "POST",
    token: hostToken,
  });
}

export function listSeats(code: string, hostToken: string): Promise<SeatsResponse> {
  return request<SeatsResponse>(`/v1/films/${code}/seats`, { token: hostToken });
}

export function createSeat(
  code: string,
  hostToken: string,
  input: { role: "cohost" | "photographer"; label: string },
): Promise<SeatCreated> {
  return request<SeatCreated>(`/v1/films/${code}/seats`, {
    method: "POST",
    token: hostToken,
    body: JSON.stringify(input),
  });
}

export function revokeSeat(code: string, seatId: string, hostToken: string): Promise<void> {
  return request<void>(`/v1/films/${code}/seats/${seatId}`, {
    method: "DELETE",
    token: hostToken,
  });
}

export function claimSeat(code: string, inviteToken: string): Promise<SeatClaimed> {
  return request<SeatClaimed>(`/v1/films/${code}/seats/claim`, {
    method: "POST",
    body: JSON.stringify({ invite_token: inviteToken }),
  });
}

export function getGallery(code: string, guestToken?: string | null): Promise<GalleryResponse> {
  return request<GalleryResponse>(`/v1/films/${code}/gallery`, {
    token: guestToken ?? undefined,
  });
}

export function reportShot(
  code: string,
  shotId: string,
  guestToken: string,
  reason: ReportReason,
): Promise<ReportResponse> {
  return request<ReportResponse>(`/v1/films/${code}/shots/${shotId}/report`, {
    method: "POST",
    token: guestToken,
    body: JSON.stringify({ reason }),
  });
}

export function registerPushToken(
  code: string,
  guestToken: string,
  token: string,
  locale: "en" | "es" | "fr",
): Promise<void> {
  return request<void>(`/v1/films/${code}/push-token`, {
    method: "PUT",
    token: guestToken,
    body: JSON.stringify({ token, locale }),
  });
}

export function revealFilm(code: string, hostToken: string): Promise<FilmPublic> {
  return request<FilmPublic>(`/v1/films/${code}/reveal`, {
    method: "POST",
    token: hostToken,
  });
}

export function hideShot(code: string, shotId: string, hostToken: string): Promise<void> {
  return request<void>(`/v1/films/${code}/shots/${shotId}/hide`, {
    method: "POST",
    token: hostToken,
  });
}

export function unhideShot(code: string, shotId: string, hostToken: string): Promise<void> {
  return request<void>(`/v1/films/${code}/shots/${shotId}/unhide`, {
    method: "POST",
    token: hostToken,
  });
}

export function getReview(code: string, hostToken: string): Promise<ReviewResponse> {
  return request<ReviewResponse>(`/v1/films/${code}/review`, { token: hostToken });
}

export function updateFilm(
  code: string,
  hostToken: string,
  patch: {
    closes_at?: string;
    reveal_at?: string;
    shot_limit?: number;
    guest_cap?: number;
    host_email?: string;
    shared_gallery?: boolean;
  },
): Promise<FilmPublic> {
  return request<FilmPublic>(`/v1/films/${code}`, {
    method: "PATCH",
    token: hostToken,
    body: JSON.stringify(patch),
  });
}

export function startExport(code: string, hostToken: string): Promise<ExportResponse> {
  return request<ExportResponse>(`/v1/films/${code}/export`, {
    method: "POST",
    token: hostToken,
  });
}

export function getExport(code: string, hostToken: string): Promise<ExportResponse> {
  return request<ExportResponse>(`/v1/films/${code}/export`, { token: hostToken });
}

export function recoverHost(code: string, email: string): Promise<void> {
  return request<void>(`/v1/films/${code}/host/recover`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function consumeMagicSession(code: string, magicToken: string): Promise<FilmCreated> {
  return request<FilmCreated>(`/v1/films/${code}/host/session`, {
    method: "POST",
    body: JSON.stringify({ magic_token: magicToken }),
  });
}

export function getHostAccount(code: string, hostToken: string): Promise<HostAccount> {
  return request<HostAccount>(`/v1/films/${code}/host/account`, { token: hostToken });
}

export type FilmrollLink = {
  code: string;
  role: "host" | "guest";
  magic: string | null;
  /** Co-host / photographer invite, exchanged once for this phone's own token. */
  seat: string | null;
};

function queryParam(raw: string, name: string): string | null {
  const match = raw.match(new RegExp(`[?&]${name}=([^&#]+)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/** Route universal links and custom-scheme URLs to host vs guest surfaces. */
export function parseFilmrollUrl(raw: string): FilmrollLink | null {
  const pathMatch = raw.match(/\/f\/([A-Za-z0-9]{4,12})(\/host)?(?:[/?#]|$)/i);
  if (!pathMatch) return null;

  return {
    code: pathMatch[1].toUpperCase(),
    role: pathMatch[2] ? "host" : "guest",
    magic: queryParam(raw, "magic"),
    seat: queryParam(raw, "seat"),
  };
}

function reserveShot(
  code: string,
  token: string,
  shotId: string,
  kind: ShotKind,
  contentType: string,
): Promise<ReserveResponse> {
  return request<ReserveResponse>(`/v1/films/${code}/shots/reserve`, {
    method: "POST",
    token,
    body: JSON.stringify({ shot_id: shotId, kind, content_type: contentType }),
  });
}

/** iOS records QuickTime, Android MP4. The worker transcodes either. */
export function clipContentType(fileUri: string): string {
  return /\.mov$/i.test(fileUri) ? "video/quicktime" : "video/mp4";
}

function commitShot(
  code: string,
  token: string,
  shotId: string,
): Promise<CommitResponse> {
  return request<CommitResponse>(`/v1/films/${code}/shots/${shotId}/commit`, {
    method: "POST",
    token,
  });
}

const UPLOAD_ATTEMPTS = 3;

/**
 * Client-generated shot id (UUID v4). Hermes has no global `crypto`, so this
 * falls back to Math.random: the id only has to be unique per guest, since the
 * guest token is what authorises the upload.
 */
export function newShotId(): string {
  const native = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  if (native?.randomUUID) return native.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
    const nibble = Math.floor(Math.random() * 16);
    return (char === "x" ? nibble : (nibble & 0x3) | 0x8).toString(16);
  });
}

/**
 * Reserve a slot, PUT the file at the camera URI, then commit.
 *
 * The shot id is generated here and reused across retries so a drop on venue
 * wifi cannot burn two slots.
 */
export async function captureShot(
  code: string,
  token: string,
  fileUri: string,
  shotId: string = newShotId(),
  kind: ShotKind = "photo",
): Promise<CommitResponse> {
  const contentType = kind === "clip" ? clipContentType(fileUri) : "image/jpeg";
  let lastError: unknown;
  for (let attempt = 1; attempt <= UPLOAD_ATTEMPTS; attempt += 1) {
    try {
      const reserved = await reserveShot(code, token, shotId, kind, contentType);
      const uploaded = await uploadAsync(reserved.upload_url, fileUri, {
        httpMethod: "PUT",
        uploadType: FileSystemUploadType.BINARY_CONTENT,
        headers: { "Content-Type": reserved.content_type },
      });
      if (uploaded.status < 200 || uploaded.status >= 300) {
        throw new ApiError(uploaded.status, `Upload failed (${uploaded.status})`);
      }
      return await commitShot(code, token, shotId);
    } catch (error) {
      lastError = error;
      if (attempt < UPLOAD_ATTEMPTS) {
        await new Promise((resolve) => setTimeout(resolve, 2 ** attempt * 400));
      }
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new Error("Could not upload this photo");
}

/** Errors that should stay in the queue and retry. Anything else is terminal. */
export function isRetryableUploadError(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  return error.status === 429 || error.status >= 500;
}

/** Pull a 6-character film code out of a universal link or custom scheme. */
export function filmCodeFromUrl(raw: string): string | null {
  return parseFilmrollUrl(raw)?.code ?? null;
}
