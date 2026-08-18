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
  FilmPublic,
  GalleryResponse,
  HostAccount,
  JoinResponse,
  ReserveResponse,
  ReviewResponse,
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

// ------------------------------------------------------------------- endpoints

export function createFilm(input: {
  title: string;
  event_type: string;
  closes_at: string;
  reveal_at: string;
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

export function joinFilm(code: string, displayName: string): Promise<JoinResponse> {
  return request<JoinResponse>(`/v1/films/${code}/join`, {
    method: "POST",
    body: JSON.stringify({ display_name: displayName }),
  });
}

export function getGallery(code: string): Promise<GalleryResponse> {
  return request<GalleryResponse>(`/v1/films/${code}/gallery`);
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
): Promise<ReserveResponse> {
  return request<ReserveResponse>(`/v1/films/${code}/shots/reserve`, {
    method: "POST",
    token,
    body: JSON.stringify({ shot_id: shotId, content_type: "image/jpeg" }),
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
 * Reserve a slot, put the bytes in storage, then confirm.
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
  const reserved = await reserveShot(code, token, shotId);

  let lastError: unknown;
  for (let attempt = 1; attempt <= UPLOAD_ATTEMPTS; attempt += 1) {
    try {
      const upload = await fetch(reserved.upload_url, {
        method: "PUT",
        body: photo,
        headers: { "Content-Type": "image/jpeg" },
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
