/**
 * Guest "save this photo".
 *
 * The system share sheet rather than the photo library: it needs no permission
 * prompt, and it is the only route an App Clip will have (PhotoKit is inert
 * there), so the clip can reuse this flow. iOS offers "Save Image"; Android
 * offers Photos, Files and the rest. React Native's own Share cannot send a
 * file on Android, hence expo-sharing.
 */

import { cacheDirectory, downloadAsync } from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";

import type { GalleryPhoto } from "./api/types";

export async function shareMedia(photo: GalleryPhoto, basename: string): Promise<void> {
  if (!cacheDirectory) throw new Error("No cache directory");
  // A clip is only ever served as its MP4 transcode; a photo is the uploaded JPEG.
  const clip = photo.kind === "clip";
  // Left in the cache when the sheet closes: on Android the receiving app can
  // still be reading it. The name is per shot, so saving again overwrites.
  const download = await downloadAsync(
    photo.url,
    `${cacheDirectory}${basename}.${clip ? "mp4" : "jpg"}`,
  );
  if (download.status !== 200) throw new Error(`Download failed: ${download.status}`);
  await Sharing.shareAsync(download.uri, {
    mimeType: clip ? "video/mp4" : "image/jpeg",
    UTI: clip ? "public.mpeg-4" : "public.jpeg",
  });
}
