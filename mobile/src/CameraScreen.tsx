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

import { ApiError, captureShot } from "./api";
import type { FilmPublic } from "./types";

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

  const unlimited = film.unlimited_shots;
  const left = unlimited ? 9999 : Math.max(remaining ?? film.shot_limit, 0);

  const shoot = useCallback(async () => {
    if (!cameraRef.current || busy || left <= 0) return;
    setBusy(true);
    setError("");
    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.86,
        skipProcessing: true,
      });
      if (!photo?.uri) throw new Error("Could not capture");
      const committed = await captureShot(code, token, photo.uri);
      onRemainingChange(committed.shots_remaining);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      if (err instanceof ApiError && err.status === 410) {
        setError("This film has closed.");
        return;
      }
      setError("That shot did not upload. Try again.");
    } finally {
      setBusy(false);
    }
  }, [busy, code, left, onRemainingChange, onUnauthorized, token]);

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
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Pressable
        style={[styles.shutter, (busy || left <= 0) && styles.disabled]}
        onPress={() => void shoot()}
        disabled={busy || left <= 0}
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
