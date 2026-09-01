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
  FilmPublic,
  GalleryResponse,
  JoinResponse,
  ReserveResponse,
} from "./types";

export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

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

export async function saveGuestToken(code: string, token: string): Promise<void> {
  await AsyncStorage.setItem(guestKey(code), token);
}

export async function loadGuestToken(code: string): Promise<string | null> {
  return AsyncStorage.getItem(guestKey(code));
}

export async function clearGuestToken(code: string): Promise<void> {
  await AsyncStorage.removeItem(guestKey(code));
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
 * Reserve a slot, PUT the file at the camera URI, then commit.
 *
 * The shot id is generated here and reused across retries so a drop on venue
 * wifi cannot burn two slots.
 */
export async function captureShot(
  code: string,
  token: string,
  fileUri: string,
  shotId: string = crypto.randomUUID(),
): Promise<CommitResponse> {
  const reserved = await reserveShot(code, token, shotId);

  let lastError: unknown;
  for (let attempt = 1; attempt <= UPLOAD_ATTEMPTS; attempt += 1) {
    try {
      const uploaded = await uploadAsync(reserved.upload_url, fileUri, {
        httpMethod: "PUT",
        uploadType: FileSystemUploadType.BINARY_CONTENT,
        headers: { "Content-Type": "image/jpeg" },
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
  const match = raw.match(/\/f\/([A-Za-z0-9]{4,12})(?:[/?#]|$)/i);
  return match ? match[1].toUpperCase() : null;
}
