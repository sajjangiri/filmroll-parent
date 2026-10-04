/**
 * Client for the Filmroll API.
 *
 * The browser talks to FastAPI directly and uploads photo bytes straight to
 * object storage using a presigned URL. Nothing proxies the image through
 * Next.js, which is what keeps this surface cheap to run.
 */

import type {
  CatalogResponse,
  CheckoutResponse,
  CommitResponse,
  ExportResponse,
  FilmCreated,
  FilmDeleted,
  FilmPublic,
  GalleryResponse,
  HostAccount,
  JoinResponse,
  PaymentsResponse,
  ReportReason,
  ReportResponse,
  ReserveResponse,
  ReviewResponse,
  SeatClaimed,
  SeatCreated,
  SeatsResponse,
  StaffRole,
} from "@/lib/types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
    // Signed URLs are short-lived and shot counters change constantly, so a
    // cached response here would show guests stale state.
    cache: "no-store",
    headers: {
      ...(rest.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; the status text will have to do.
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// ------------------------------------------------------------------ device state
// Guests never create an account. Their identity is a signed token scoped to a
// single film, held on the device.

const guestKey = (code: string) => `filmroll-guest-${code}`;
const hostKey = (code: string) => `filmroll-host-${code}`;
const roleKey = (code: string) => `filmroll-role-${code}`;
const deletedKey = (code: string) => `filmroll-deleted-${code}`;

export function saveGuestToken(code: string, token: string): void {
  window.localStorage.setItem(guestKey(code), token);
}

export function loadGuestToken(code: string): string | null {
  return window.localStorage.getItem(guestKey(code));
}

export function clearGuestToken(code: string): void {
  window.localStorage.removeItem(guestKey(code));
}

export function saveHostToken(code: string, token: string): void {
  window.localStorage.setItem(hostKey(code), token);
}

export function loadHostToken(code: string): string | null {
  return window.localStorage.getItem(hostKey(code));
}

// Which seat this device holds. The API enforces the boundary either way; this
// only decides which controls are worth rendering.
export function saveStaffRole(code: string, role: StaffRole): void {
  window.localStorage.setItem(roleKey(code), role);
}

export function loadStaffRole(code: string): StaffRole {
  const saved = window.localStorage.getItem(roleKey(code));
  return saved === "cohost" || saved === "photographer" ? saved : "host";
}

// A deleted film is a 404 to every request, so the dashboard has no way to
// learn that a restore is still possible. This is the note the deleting device
// leaves itself; the API is what actually enforces the deadline.
export function saveDeleted(code: string, deleted: FilmDeleted): void {
  window.localStorage.setItem(deletedKey(code), JSON.stringify(deleted));
}

export function loadDeleted(code: string): FilmDeleted | null {
  const raw = window.localStorage.getItem(deletedKey(code));
  if (!raw) return null;
  try {
    return JSON.parse(raw) as FilmDeleted;
  } catch {
    return null;
  }
}

export function clearDeleted(code: string): void {
  window.localStorage.removeItem(deletedKey(code));
}

// ------------------------------------------------------------------- endpoints

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

export function revealFilm(code: string, hostToken: string): Promise<FilmPublic> {
  return request<FilmPublic>(`/v1/films/${code}/reveal`, {
    method: "POST",
    token: hostToken,
  });
}

export function hideShot(
  code: string,
  shotId: string,
  hostToken: string,
): Promise<void> {
  return request<void>(`/v1/films/${code}/shots/${shotId}/hide`, {
    method: "POST",
    token: hostToken,
  });
}

export function unhideShot(
  code: string,
  shotId: string,
  hostToken: string,
): Promise<void> {
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

export function cardsPdfUrl(code: string): string {
  return `${API_URL}/v1/films/${code}/cards.pdf`;
}

export function getCatalog(): Promise<CatalogResponse> {
  return request<CatalogResponse>("/v1/billing/catalog");
}

export function startCheckout(
  code: string,
  hostToken: string,
  body: { tier_id?: string; addon_id?: string },
): Promise<CheckoutResponse> {
  return request<CheckoutResponse>(`/v1/films/${code}/checkout`, {
    method: "POST",
    token: hostToken,
    body: JSON.stringify(body),
  });
}

export function getHostAccount(code: string, hostToken: string): Promise<HostAccount> {
  return request<HostAccount>(`/v1/films/${code}/host/account`, { token: hostToken });
}

export function getPayments(code: string, hostToken: string): Promise<PaymentsResponse> {
  return request<PaymentsResponse>(`/v1/films/${code}/payments`, { token: hostToken });
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
  body: { role: Exclude<StaffRole, "host">; label: string },
): Promise<SeatCreated> {
  return request<SeatCreated>(`/v1/films/${code}/seats`, {
    method: "POST",
    token: hostToken,
    body: JSON.stringify(body),
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

// --------------------------------------------------------------- capture flow

function reserveShot(
  code: string,
  token: string,
  shotId: string,
  media: Blob,
): Promise<ReserveResponse> {
  const clip = media.type.startsWith("video/");
  return request<ReserveResponse>(`/v1/films/${code}/shots/reserve`, {
    method: "POST",
    token,
    body: JSON.stringify({
      shot_id: shotId,
      kind: clip ? "clip" : "photo",
      content_type: clip ? media.type : "image/jpeg",
    }),
  });
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
 * Reserve a slot, put the bytes in storage, then confirm. A video blob is
 * reserved as a clip, which draws on its own allowance.
 *
 * The shot id is generated here and reused across every retry. That is what
 * makes the whole sequence idempotent: a guest on bad venue wifi can fail and
 * retry repeatedly without burning extra slots or creating duplicate photos.
 */
export async function captureShot(
  code: string,
  token: string,
  photo: Blob,
  shotId: string = crypto.randomUUID(),
): Promise<CommitResponse> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= UPLOAD_ATTEMPTS; attempt += 1) {
    try {
      // Re-reserve each attempt so a slow or dropped PUT gets a fresh presigned URL
      // without burning a second slot (same client shot id).
      const reserved = await reserveShot(code, token, shotId, photo);
      const upload = await fetch(reserved.upload_url, {
        method: "PUT",
        body: photo,
        headers: { "Content-Type": reserved.content_type },
      });
      if (!upload.ok) {
        throw new ApiError(upload.status, `Upload failed (${upload.status})`);
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
