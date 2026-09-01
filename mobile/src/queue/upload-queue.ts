/**
 * Offline capture queue.
 *
 * Venue wifi dies constantly. The shutter copies the JPEG into the app
 * documents directory and returns; a drain loop talks to the API once a
 * connection exists. Killing the app does not lose photos because the queue
 * lives on disk, not in memory.
 *
 * iOS will not run this in the background. Opening the film again is enough
 * to resume draining, same as the PWA.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  copyAsync,
  deleteAsync,
  documentDirectory,
  makeDirectoryAsync,
} from "expo-file-system/legacy";

import {
  ApiError,
  captureShot,
  isRetryableUploadError,
} from "../api/client";

export type QueuedShot = {
  shotId: string;
  code: string;
  token: string;
  fileUri: string;
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

const metaKey = (code: string) => `filmroll-queue-${code}`;

type Listener = () => void;

const listeners = new Set<Listener>();
const snapshots = new Map<string, QueueSnapshot>();
const locks = new Map<string, Promise<void>>();

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

function withLock(code: string, fn: () => Promise<void>): Promise<void> {
  const previous = locks.get(code) ?? Promise.resolve();
  const next = previous.then(fn, fn);
  locks.set(
    code,
    next.then(
      () => undefined,
      () => undefined,
    ),
  );
  return next;
}

async function loadShots(code: string): Promise<QueuedShot[]> {
  const raw = await AsyncStorage.getItem(metaKey(code));
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as QueuedShot[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function saveShots(code: string, shots: QueuedShot[]): Promise<void> {
  if (shots.length === 0) {
    await AsyncStorage.removeItem(metaKey(code));
    return;
  }
  await AsyncStorage.setItem(metaKey(code), JSON.stringify(shots));
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

async function persistCopy(shotId: string, fromUri: string): Promise<string> {
  if (!documentDirectory) {
    throw new Error("No durable directory on this device");
  }
  const dir = `${documentDirectory}queued-shots/`;
  await makeDirectoryAsync(dir, { intermediates: true });
  const dest = `${dir}${shotId}.jpg`;
  await copyAsync({ from: fromUri, to: dest });
  return dest;
}

async function removeFile(fileUri: string): Promise<void> {
  try {
    await deleteAsync(fileUri, { idempotent: true });
  } catch {
    // Already gone.
  }
}

export async function refreshSnapshot(code: string): Promise<QueueSnapshot> {
  const snapshot = countSnapshot(await loadShots(code));
  notify(code, snapshot);
  return snapshot;
}

export async function enqueueShot(input: {
  code: string;
  token: string;
  fileUri: string;
}): Promise<string> {
  const shotId = crypto.randomUUID();
  const fileUri = await persistCopy(shotId, input.fileUri);
  const shot: QueuedShot = {
    shotId,
    code: input.code,
    token: input.token,
    fileUri,
    createdAt: Date.now(),
    status: "pending",
    attempts: 0,
  };

  await withLock(input.code, async () => {
    const shots = await loadShots(input.code);
    shots.push(shot);
    await saveShots(input.code, shots);
  });
  await refreshSnapshot(input.code);
  void drainQueue(input.code);
  return shotId;
}

let draining = false;
let drainRequested = false;

export async function drainQueue(code: string): Promise<void> {
  drainRequested = true;
  if (draining) return;
  draining = true;
  try {
    while (drainRequested) {
      drainRequested = false;
      await withLock(code, async () => {
        const existing = await loadShots(code);
        let changed = false;
        for (const shot of existing) {
          if (shot.status === "uploading") {
            shot.status = "pending";
            changed = true;
          }
        }
        if (changed) await saveShots(code, existing);
      });
      await refreshSnapshot(code);

      for (;;) {
        const next = (await loadShots(code)).find((shot) => shot.status === "pending");
        if (!next) break;
        await uploadOne(next);
      }
    }
  } finally {
    draining = false;
    await refreshSnapshot(code);
  }
}

async function putShot(shot: QueuedShot): Promise<void> {
  await withLock(shot.code, async () => {
    const shots = await loadShots(shot.code);
    const index = shots.findIndex((item) => item.shotId === shot.shotId);
    if (index === -1) shots.push(shot);
    else shots[index] = shot;
    await saveShots(shot.code, shots);
  });
}

async function deleteShot(shot: QueuedShot): Promise<void> {
  await withLock(shot.code, async () => {
    const shots = (await loadShots(shot.code)).filter((item) => item.shotId !== shot.shotId);
    await saveShots(shot.code, shots);
  });
  await removeFile(shot.fileUri);
}

async function uploadOne(shot: QueuedShot): Promise<void> {
  shot.status = "uploading";
  shot.attempts += 1;
  await putShot(shot);
  await refreshSnapshot(shot.code);

  try {
    const committed = await captureShot(shot.code, shot.token, shot.fileUri, shot.shotId);
    await deleteShot(shot);
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
