import { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import {
  CameraView,
  type CameraType,
  useCameraPermissions,
} from "expo-camera";

import { useUploadQueue } from "../queue/use-upload-queue";
import type { FilmPublic } from "../api/types";

type Props = {
  code: string;
  token: string;
  film: FilmPublic;
  remaining: number | null;
  onRemainingChange: (remaining: number) => void;
  onUnauthorized: () => void;
};

export function CameraScreen({
  code,
  token,
  film,
  remaining,
  onRemainingChange,
  onUnauthorized,
}: Props) {
  const cameraRef = useRef<CameraView>(null);
  const [permission, requestPermission] = useCameraPermissions();
  const [facing, setFacing] = useState<CameraType>("back");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [closed, setClosed] = useState(false);

  const { snapshot, enqueue, waiting } = useUploadQueue(code, {
    token,
    onRemainingChange,
    onUnauthorized,
    onClosed: () => {
      setClosed(true);
      setError("This film has closed.");
    },
  });

  const unlimited = film.unlimited_shots;
  const left = unlimited
    ? 9999
    : Math.max((remaining ?? film.shot_limit) - waiting, 0);

  const shoot = useCallback(async () => {
    if (!cameraRef.current || busy || left <= 0 || closed) return;
    setBusy(true);
    setError("");
    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.86,
        skipProcessing: true,
      });
      if (!photo?.uri) throw new Error("Could not capture");
      await enqueue(photo.uri);
    } catch {
      setError("That shot did not save on this device. Try again.");
    } finally {
      setBusy(false);
    }
  }, [busy, closed, enqueue, left]);

  if (!permission) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color="#fff" />
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.centered}>
        <Text style={styles.copy}>Camera permission is required to shoot.</Text>
        <Pressable style={styles.primary} onPress={() => void requestPermission()}>
          <Text style={styles.primaryLabel}>Allow camera</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.wrap}>
      <View style={styles.preview}>
        <CameraView ref={cameraRef} style={StyleSheet.absoluteFill} facing={facing} />
        <View style={styles.hud}>
          <Text style={styles.hudText}>{film.title}</Text>
          <Text style={styles.hudText}>
            {unlimited ? "Unlimited" : `${left} / ${film.shot_limit}`}
          </Text>
        </View>
        <Pressable
          style={styles.flip}
          onPress={() => setFacing((current) => (current === "back" ? "front" : "back"))}
        >
          <Text style={styles.flipLabel}>Flip</Text>
        </Pressable>
      </View>
      {waiting > 0 ? (
        <Text style={styles.copy}>
          {snapshot.uploading > 0
            ? `Uploading… ${waiting} waiting`
            : `${waiting} ${waiting === 1 ? "photo" : "photos"} saved on this phone`}
        </Text>
      ) : null}
      {snapshot.failed > 0 ? (
        <Text style={styles.error}>
          {snapshot.failed} {snapshot.failed === 1 ? "shot" : "shots"} could not be uploaded.
        </Text>
      ) : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Pressable
        style={[styles.shutter, (busy || left <= 0 || closed) && styles.disabled]}
        onPress={() => void shoot()}
        disabled={busy || left <= 0 || closed}
      />
      {left <= 0 ? (
        <Text style={styles.copy}>This camera is empty. Photos unlock when the film develops.</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 16 },
  preview: {
    aspectRatio: 3 / 4,
    overflow: "hidden",
    borderRadius: 16,
    backgroundColor: "#18181b",
  },
  hud: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    flexDirection: "row",
    justifyContent: "space-between",
    padding: 16,
  },
  hudText: { color: "#fff", fontSize: 14 },
  flip: {
    position: "absolute",
    right: 16,
    bottom: 16,
    backgroundColor: "rgba(0,0,0,0.6)",
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  flipLabel: { color: "#fff", fontSize: 12 },
  shutter: {
    alignSelf: "center",
    width: 80,
    height: 80,
    borderRadius: 40,
    borderWidth: 4,
    borderColor: "#fff",
    backgroundColor: "rgba(255,255,255,0.9)",
  },
  disabled: { opacity: 0.4 },
  centered: { gap: 16, paddingVertical: 24 },
  copy: { color: "#a1a1aa", textAlign: "center" },
  error: { color: "#f87171", textAlign: "center" },
  primary: {
    alignSelf: "center",
    backgroundColor: "#fff",
    borderRadius: 999,
    paddingHorizontal: 20,
    paddingVertical: 12,
  },
  primaryLabel: { color: "#000", fontWeight: "600" },
});
