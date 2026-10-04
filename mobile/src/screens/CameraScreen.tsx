import { useCallback, useEffect, useRef, useState } from "react";
import {
  AccessibilityInfo,
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from "react-native";
import {
  CameraView,
  type CameraType,
  useCameraPermissions,
  useMicrophonePermissions,
} from "expo-camera";

import { useI18n } from "../i18n/I18nProvider";
import { useUploadQueue } from "../queue/use-upload-queue";
import type { FilmPublic } from "../api/types";

type Props = {
  code: string;
  token: string;
  film: FilmPublic;
  remaining: number | null;
  onRemainingChange: (remaining: number) => void;
  clipsRemaining: number | null;
  onClipsRemainingChange: (remaining: number) => void;
  onUnauthorized: () => void;
};

// Well under the server's cap; the worker trims to the clip limit regardless.
const CLIP_MAX_BYTES = 100 * 1024 * 1024;

export function CameraScreen({
  code,
  token,
  film,
  remaining,
  onRemainingChange,
  clipsRemaining,
  onClipsRemainingChange,
  onUnauthorized,
}: Props) {
  const { t } = useI18n();
  const cameraRef = useRef<CameraView>(null);
  const { height: windowHeight } = useWindowDimensions();
  const [permission, requestPermission] = useCameraPermissions();
  // Only ever requested from the record button, so a photos-only guest never
  // sees a microphone prompt.
  const [micPermission, requestMicPermission] = useMicrophonePermissions({ request: false });
  const [mode, setMode] = useState<"photo" | "clip">("photo");
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [facing, setFacing] = useState<CameraType>("back");
  const [torchOn, setTorchOn] = useState(false);
  const [zoom, setZoom] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [closed, setClosed] = useState(false);

  const { snapshot, enqueue, waiting, photosWaiting, clipsWaiting } = useUploadQueue(code, {
    token,
    onRemainingChange,
    onClipsRemainingChange,
    onUnauthorized,
    onClosed: () => {
      setClosed(true);
      setError(t("filmClosedCapture"));
    },
  });

  const unlimited = film.unlimited_shots;
  const left = unlimited
    ? 9999
    : Math.max((remaining ?? film.shot_limit) - photosWaiting, 0);
  const clipsLeft = Math.max((clipsRemaining ?? film.clips_per_guest) - clipsWaiting, 0);
  const clipMode = film.video_pack && mode === "clip";
  const empty = clipMode ? clipsLeft <= 0 : left <= 0;

  useEffect(() => {
    if (!recording) return;
    const started = Date.now();
    const id = setInterval(() => setElapsed((Date.now() - started) / 1000), 250);
    return () => clearInterval(id);
  }, [recording]);

  async function toggleRecording() {
    const camera = cameraRef.current;
    if (!camera) return;
    if (recording) {
      // The file takes a moment to finalise; stop the clock now so the guest
      // is not watching it count past the moment they let go.
      setRecording(false);
      setBusy(true);
      camera.stopRecording();
      return;
    }
    if (busy || clipsLeft <= 0 || closed) return;
    setError("");

    if (!micPermission?.granted) {
      const asked = await requestMicPermission();
      if (!asked.granted) {
        setError(t("micPermission"));
        return;
      }
    }

    setRecording(true);
    setElapsed(0);
    try {
      // Resolves on stop, at maxDuration, or if the preview goes away.
      const clip = await camera.recordAsync({
        maxDuration: film.clip_max_seconds,
        maxFileSize: CLIP_MAX_BYTES,
      });
      setRecording(false);
      if (!clip?.uri) throw new Error("Could not record");
      setBusy(true);
      await enqueue(clip.uri, "clip");
      AccessibilityInfo.announceForAccessibility(t("clipSaved"));
    } catch {
      setError(t("shotNotSaved"));
    } finally {
      setRecording(false);
      setBusy(false);
    }
  }

  function formatSeconds(total: number): string {
    const whole = Math.floor(total);
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
  }

  const zoomLabel = `${(1 + zoom * 3).toFixed(1)}×`;

  function stepZoom(delta: number) {
    setZoom((current) => Math.min(1, Math.max(0, Math.round((current + delta) * 5) / 5)));
  }

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

      // The shutter is silent, so this is the only confirmation VoiceOver gets.
      // Live regions are Android-only in RN; announce works on both.
      const after = left - 1;
      AccessibilityInfo.announceForAccessibility(
        unlimited
          ? t("shotSaved")
          : after === 1
            ? t("shotLeftOne")
            : t("shotsLeft", { count: Math.max(after, 0) }),
      );
    } catch {
      setError(t("shotNotSaved"));
    } finally {
      setBusy(false);
    }
  }, [busy, closed, enqueue, left, t, unlimited]);

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
        <Text style={styles.copy}>{t("cameraPermission")}</Text>
        <Pressable
          style={styles.primary}
          onPress={() => void requestPermission()}
          accessibilityRole="button"
          accessibilityLabel={t("allowCamera")}
        >
          <Text style={styles.primaryLabel}>{t("allowCamera")}</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.wrap}>
      {/* The mode switch costs a row, so the preview gives it back. */}
      <View
        style={[styles.preview, { maxHeight: windowHeight * (film.video_pack ? 0.42 : 0.5) }]}
      >
        <CameraView
          ref={cameraRef}
          style={StyleSheet.absoluteFill}
          facing={facing}
          enableTorch={torchOn && facing === "back"}
          zoom={zoom}
          mode={clipMode ? "video" : "picture"}
          videoQuality="1080p"
        />
        <View style={styles.hud}>
          <Text style={styles.hudText}>{film.title}</Text>
          <Text style={[styles.hudText, recording && styles.recordingText]}>
            {recording
              ? `● ${formatSeconds(elapsed)} / ${formatSeconds(film.clip_max_seconds)}`
              : clipMode
                ? clipsLeft === 1
                  ? t("clipLeftOne")
                  : t("clipsLeft", { count: clipsLeft })
                : unlimited
                  ? t("unlimited")
                  : `${left} / ${film.shot_limit}`}
          </Text>
        </View>
        <View style={styles.controls}>
          <View style={styles.controlRow}>
            {facing === "back" ? (
            <Pressable
              style={[styles.control, torchOn && styles.controlActive]}
              onPress={() => setTorchOn((on) => !on)}
              accessibilityRole="button"
              accessibilityState={{ selected: torchOn }}
              accessibilityLabel={torchOn ? t("turnTorchOff") : t("turnTorchOn")}
            >
                <Text style={styles.controlLabel}>{torchOn ? t("torchOn") : t("torch")}</Text>
              </Pressable>
            ) : (
              <View style={styles.controlSpacer} />
            )}
            <View style={styles.zoomControls}>
              <Pressable
                style={styles.zoomButton}
                hitSlop={12}
                onPress={() => stepZoom(-0.2)}
                accessibilityRole="button"
                accessibilityLabel={t("zoomOut")}
              >
                <Text style={styles.controlLabel}>−</Text>
              </Pressable>
              <Text
                style={styles.zoomLabel}
                accessibilityLabel={t("zoomLevel", { level: zoomLabel })}
              >
                {zoomLabel}
              </Text>
              <Pressable
                style={styles.zoomButton}
                hitSlop={12}
                onPress={() => stepZoom(0.2)}
                accessibilityRole="button"
                accessibilityLabel={t("zoomIn")}
              >
                <Text style={styles.controlLabel}>+</Text>
              </Pressable>
            </View>
          </View>
          <Pressable
            style={[styles.control, recording && styles.disabled]}
            disabled={recording}
            onPress={() => {
              setTorchOn(false);
              setZoom(0);
              setFacing((current) => (current === "back" ? "front" : "back"));
            }}
            accessibilityRole="button"
            accessibilityLabel={t("switchCamera")}
          >
            <Text style={styles.controlLabel}>{t("flipCamera")}</Text>
          </Pressable>
        </View>
      </View>
      {waiting > 0 ? (
        <Text style={styles.copy} accessibilityLiveRegion="polite">
          {snapshot.uploading > 0
            ? t("uploading", { count: waiting })
            : waiting === 1
              ? t("photoWaiting")
              : t("photosWaiting", { count: waiting })}
        </Text>
      ) : null}
      {snapshot.failed > 0 ? (
        <Text style={styles.error} accessibilityRole="alert" accessibilityLiveRegion="assertive">
          {snapshot.failed === 1
            ? t("shotFailed")
            : t("shotsFailed", { count: snapshot.failed })}
        </Text>
      ) : null}
      {error ? (
        <Text style={styles.error} accessibilityRole="alert" accessibilityLiveRegion="assertive">
          {error}
        </Text>
      ) : null}
      {film.video_pack ? (
        <View style={styles.modes} accessibilityRole="radiogroup">
          {(["photo", "clip"] as const).map((option) => (
            <Pressable
              key={option}
              style={[styles.mode, mode === option && styles.modeActive]}
              onPress={() => setMode(option)}
              disabled={recording}
              accessibilityRole="radio"
              accessibilityState={{ checked: mode === option, disabled: recording }}
            >
              <Text style={[styles.modeLabel, mode === option && styles.modeLabelActive]}>
                {t(option === "photo" ? "modePhoto" : "modeClip")}
              </Text>
            </Pressable>
          ))}
        </View>
      ) : null}
      {clipMode ? (
        <Pressable
          style={[styles.shutter, styles.recordShutter, !recording && (busy || empty || closed) && styles.disabled]}
          onPress={() => void toggleRecording()}
          disabled={!recording && (busy || empty || closed)}
          accessibilityRole="button"
          accessibilityState={{ disabled: !recording && (busy || empty || closed), busy }}
          accessibilityLabel={recording ? t("stopClip") : t("recordClip")}
        >
          <View style={recording ? styles.stopDot : styles.recordDot} />
        </Pressable>
      ) : (
        <Pressable
          style={[styles.shutter, (busy || left <= 0 || closed) && styles.disabled]}
          onPress={() => void shoot()}
          disabled={busy || left <= 0 || closed}
          accessibilityRole="button"
          accessibilityState={{ disabled: busy || left <= 0 || closed, busy }}
          accessibilityLabel={t("takePhoto")}
        />
      )}
      {empty ? (
        <Text style={styles.copy}>
          {clipMode
            ? t("clipsEmpty")
            : t(film.instant_reveal ? "cameraEmptyLive" : "cameraEmpty")}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 16 },
  // 3:4 on tall phones; capped on 16:9 ones so the shutter stays above the fold.
  preview: {
    width: "100%",
    alignSelf: "center",
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
  hudText: {
    color: "#fff",
    fontSize: 14,
    textShadowColor: "rgba(0,0,0,0.8)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
  },
  controls: {
    position: "absolute",
    left: 16,
    right: 16,
    bottom: 16,
    gap: 8,
  },
  controlRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 8,
  },
  controlSpacer: { width: 88 },
  zoomControls: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "rgba(0,0,0,0.7)",
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  zoomButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255,255,255,0.2)",
  },
  zoomLabel: { color: "#fff", fontSize: 14, minWidth: 42, textAlign: "center" },
  control: {
    backgroundColor: "rgba(0,0,0,0.7)",
    borderRadius: 999,
    minHeight: 44,
    minWidth: 44,
    paddingHorizontal: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  controlActive: { backgroundColor: "rgba(255,255,255,0.3)" },
  controlLabel: { color: "#fff", fontSize: 14, fontWeight: "500" },
  shutter: {
    alignSelf: "center",
    width: 80,
    height: 80,
    borderRadius: 40,
    borderWidth: 4,
    borderColor: "#fff",
    backgroundColor: "rgba(255,255,255,0.9)",
  },
  recordShutter: {
    backgroundColor: "transparent",
    alignItems: "center",
    justifyContent: "center",
  },
  recordDot: { width: 56, height: 56, borderRadius: 28, backgroundColor: "#ef4444" },
  stopDot: { width: 28, height: 28, borderRadius: 6, backgroundColor: "#ef4444" },
  recordingText: { color: "#fca5a5", fontVariant: ["tabular-nums"] },
  modes: {
    alignSelf: "center",
    flexDirection: "row",
    backgroundColor: "#18181b",
    borderRadius: 999,
    padding: 4,
  },
  mode: {
    minHeight: 44,
    paddingHorizontal: 20,
    borderRadius: 999,
    justifyContent: "center",
  },
  modeActive: { backgroundColor: "#fff" },
  modeLabel: { color: "#d4d4d8", fontSize: 15, fontWeight: "500" },
  modeLabelActive: { color: "#000" },
  disabled: { opacity: 0.4 },
  centered: { gap: 16, paddingVertical: 24 },
  copy: { color: "#a1a1aa", textAlign: "center" },
  error: { color: "#f87171", textAlign: "center" },
  primary: {
    alignSelf: "center",
    backgroundColor: "#fff",
    borderRadius: 999,
    minHeight: 44,
    justifyContent: "center",
    paddingHorizontal: 24,
  },
  primaryLabel: { color: "#000", fontWeight: "600", fontSize: 16 },
});
