/**
 * Offline capture queue.
 *
 * Venue wifi dies constantly. The shutter therefore writes the JPEG to
 * IndexedDB first and returns; a separate drain loop talks to the API once a
 * connection exists. Reloading the page does not lose photos because the queue
 * lives on disk, not in memory.
 *
 * iOS will suspend a background tab, and Background Sync is not available
 * there, so this does not depend on either. Opening the film again is enough
 * to resume draining.
 */

import {
  ApiError,
  captureShot,
  isRetryableUploadError,
} from "@/lib/api";

const DB_NAME = "filmroll";
const STORE = "queued-shots";
const DB_VERSION = 1;

export type QueuedShot = {
  shotId: string;
  code: string;
  token: string;
  photo: Blob;
  createdAt: number;
  status: "pending" | "uploading" | "failed";
  attempts: number;
  lastError?: string;
};

export type QueueSnapshot = {
  pending: number;
  uploading: number;
  failed: number;
};

export const EMPTY_SNAPSHOT: QueueSnapshot = {
  pending: 0,
  uploading: 0,
  failed: 0,
};

type Listener = () => void;

const listeners = new Set<Listener>();
const snapshots = new Map<string, QueueSnapshot>();

function notify(code: string, snapshot: QueueSnapshot): void {
  snapshots.set(code, snapshot);
  for (const listener of listeners) listener();
}

export function subscribeQueue(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getQueueSnapshot(code: string): QueueSnapshot {
  return snapshots.get(code) ?? EMPTY_SNAPSHOT;
}

export function getServerQueueSnapshot(): QueueSnapshot {
  return EMPTY_SNAPSHOT;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: "shotId" });
        store.createIndex("code", "code", { unique: false });
        store.createIndex("status", "status", { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("indexedDB open failed"));
  });
}

function req<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("indexedDB request failed"));
  });
}

async function allForCode(code: string): Promise<QueuedShot[]> {
  const db = await openDb();
  try {
    const tx = db.transaction(STORE, "readonly");
    const index = tx.objectStore(STORE).index("code");
    return (await req(index.getAll(code))) as QueuedShot[];
  } finally {
    db.close();
  }
}

async function putShot(shot: QueuedShot): Promise<void> {
  const db = await openDb();
  try {
    const tx = db.transaction(STORE, "readwrite");
    await req(tx.objectStore(STORE).put(shot));
  } finally {
    db.close();
  }
}

async function deleteShot(shotId: string): Promise<void> {
  const db = await openDb();
  try {
    const tx = db.transaction(STORE, "readwrite");
    await req(tx.objectStore(STORE).delete(shotId));
  } finally {
    db.close();
  }
}

function countSnapshot(shots: QueuedShot[]): QueueSnapshot {
  const snapshot: QueueSnapshot = { pending: 0, uploading: 0, failed: 0 };
  for (const shot of shots) {
    if (shot.status === "pending") snapshot.pending += 1;
    else if (shot.status === "uploading") snapshot.uploading += 1;
    else snapshot.failed += 1;
  }
  return snapshot;
}

export async function refreshSnapshot(code: string): Promise<QueueSnapshot> {
  const snapshot = countSnapshot(await allForCode(code));
  notify(code, snapshot);
  return snapshot;
}

export async function enqueueShot(input: {
  code: string;
  token: string;
  photo: Blob;
}): Promise<string> {
  const shot: QueuedShot = {
    shotId: crypto.randomUUID(),
    code: input.code,
    token: input.token,
    photo: input.photo,
    createdAt: Date.now(),
    status: "pending",
    attempts: 0,
  };
  await putShot(shot);
  await refreshSnapshot(input.code);
  void drainQueue(input.code);
  return shot.shotId;
}

let draining = false;
let drainRequested = false;

/**
 * Reset rows left in `uploading` after a crash or a killed tab, then push
 * everything that is still pending.
 */
export async function drainQueue(code: string): Promise<void> {
  drainRequested = true;
  if (draining) return;
  draining = true;
  try {
    while (drainRequested) {
      drainRequested = false;
      const existing = await allForCode(code);
      for (const shot of existing) {
        if (shot.status === "uploading") {
          shot.status = "pending";
          await putShot(shot);
        }
      }
      await refreshSnapshot(code);

      while (navigator.onLine !== false) {
        const next = (await allForCode(code)).find((shot) => shot.status === "pending");
        if (!next) break;
        await uploadOne(next);
      }
    }
  } finally {
    draining = false;
    await refreshSnapshot(code);
  }
}

async function uploadOne(shot: QueuedShot): Promise<void> {
  shot.status = "uploading";
  shot.attempts += 1;
  await putShot(shot);
  await refreshSnapshot(shot.code);

  try {
    const committed = await captureShot(shot.code, shot.token, shot.photo, shot.shotId);
    await deleteShot(shot.shotId);
    listenersForSuccess.forEach((fn) => fn(shot, committed.shots_remaining));
  } catch (error) {
    if (isRetryableUploadError(error) && shot.attempts < 8) {
      shot.status = "pending";
      shot.lastError = error instanceof Error ? error.message : "upload failed";
      await putShot(shot);
      const delay = Math.min(2 ** shot.attempts * 400, 15_000);
      await new Promise((resolve) => setTimeout(resolve, delay));
      return;
    }

    shot.status = "failed";
    shot.lastError = error instanceof Error ? error.message : "upload failed";
    await putShot(shot);
    listenersForFailure.forEach((fn) => fn(shot, error));
  }
}

type ShotListener = (shot: QueuedShot, remaining: number) => void;
type FailListener = (shot: QueuedShot, error: unknown) => void;

const listenersForSuccess = new Set<ShotListener>();
const listenersForFailure = new Set<FailListener>();

export function onShotUploaded(listener: ShotListener): () => void {
  listenersForSuccess.add(listener);
  return () => {
    listenersForSuccess.delete(listener);
  };
}

export function onShotFailed(listener: FailListener): () => void {
  listenersForFailure.add(listener);
  return () => {
    listenersForFailure.delete(listener);
  };
}

export function isCapError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409 && /every shot/i.test(error.message);
}

export function isClosedError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 410;
}

export function isAuthError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 403);
}
