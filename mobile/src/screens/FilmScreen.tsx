import { useCallback, useEffect, useRef, useState } from "react";
import {
  AccessibilityInfo,
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  ApiError,
  clearGuestToken,
  getFilm,
  getGallery,
  joinFilm,
  loadGuestToken,
  loadHostName,
  reportShot,
  saveGuestToken,
} from "../api/client";
import { LanguagePicker } from "../components/LanguagePicker";
import { useI18n } from "../i18n/I18nProvider";
import { registerGuestPush } from "../notifications";
import { shareMedia } from "../share-media";
import { CameraScreen } from "./CameraScreen";
import { ClipTile } from "../components/ClipTile";
import type { FilmPublic, GalleryPhoto } from "../api/types";
import { drainQueue } from "../queue/upload-queue";

export function FilmScreen({
  code,
  onLeave,
  joinAsHost = false,
}: {
  code: string;
  onLeave: () => void;
  joinAsHost?: boolean;
}) {
  const { t, locale } = useI18n();
  const [film, setFilm] = useState<FilmPublic | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [clipsRemaining, setClipsRemaining] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState(false);
  const [photos, setPhotos] = useState<GalleryPhoto[]>([]);
  const [reported, setReported] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState<Set<string>>(new Set());
  const hostJoinTried = useRef(false);
  const pushAskedFor = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const loaded = await getFilm(code);
      setFilm(loaded);
      const saved = await loadGuestToken(code);
      setToken(saved);
      if (loaded.is_developed) {
        const gallery = await getGallery(code, saved);
        setPhotos(gallery.photos);
      }
    } catch {
      setError(t("filmNotFound"));
      setFilm(null);
    }
    setLoading(false);
  }, [code, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!film?.instant_reveal) return;
    const id = setInterval(() => {
      void refresh();
    }, 8000);
    return () => clearInterval(id);
  }, [film?.instant_reveal, refresh]);

  useEffect(() => {
    if (!token) return;
    void drainQueue(code);
  }, [code, token]);

  // Once per guest token: Android re-shows the permission prompt after a single
  // "Don't allow", so re-running this on every film refresh nags the guest.
  const filmLoaded = film !== null;
  const instantReveal = film?.instant_reveal ?? false;
  useEffect(() => {
    if (!token || !filmLoaded || instantReveal || pushAskedFor.current === token) return;
    pushAskedFor.current = token;
    void registerGuestPush(code, token, locale);
  }, [code, token, locale, filmLoaded, instantReveal]);

  useEffect(() => {
    if (!joinAsHost || loading || token || !film || hostJoinTried.current) return;
    hostJoinTried.current = true;
    void loadHostName().then((saved) => {
      if (!saved) return;
      setName(saved);
      // The host does not store the PIN they set, so a PIN film falls back to the form.
      if (!film.is_closed && !film.requires_pin) void onJoin(saved);
    });
  }, [joinAsHost, loading, token, film]);

  async function report(shotId: string) {
    if (!token) return;
    // Optimistic: a guest who taps report wants to stop thinking about it, and
    // the count the host sees is the thing that actually matters.
    setReported((current) => new Set(current).add(shotId));
    try {
      await reportShot(code, shotId, token, "inappropriate");
      AccessibilityInfo.announceForAccessibility(t("reportThanks"));
    } catch {
      setReported((current) => {
        const next = new Set(current);
        next.delete(shotId);
        return next;
      });
      setError(t("reportFailed"));
    }
  }

  async function save(photo: GalleryPhoto) {
    // A second tap while the download runs would open a second share sheet.
    if (saving.has(photo.shot_id)) return;
    setSaving((current) => new Set(current).add(photo.shot_id));
    setError("");
    try {
      await shareMedia(photo, `filmroll-${code}-${photo.shot_id.slice(0, 8)}`);
    } catch {
      setError(t("saveFailed"));
      AccessibilityInfo.announceForAccessibility(t("saveFailed"));
    } finally {
      setSaving((current) => {
        const next = new Set(current);
        next.delete(photo.shot_id);
        return next;
      });
    }
  }

  async function onJoin(displayName = name) {
    const trimmed = displayName.trim();
    if (!trimmed) return;
    setJoining(true);
    setError("");
    try {
      const joined = await joinFilm(code, trimmed, pin.trim() || undefined);
      await saveGuestToken(code, joined.guest_token);
      setToken(joined.guest_token);
      setRemaining(joined.shots_remaining);
      setClipsRemaining(joined.clips_remaining);
      setFilm((current) =>
        current ? { ...current, guest_count: current.guest_count + 1 } : current,
      );
      if (film?.is_developed) {
        const gallery = await getGallery(code, joined.guest_token);
        setPhotos(gallery.photos);
      }
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? t("filmFull")
          : err instanceof ApiError && err.status === 410
            ? t("filmClosed")
            : err instanceof ApiError && err.status === 403
              ? t("wrongPin")
              : t("couldNotJoin"),
      );
    } finally {
      setJoining(false);
    }
  }

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color="#fff" />
      </View>
    );
  }

  if (!film) {
    return (
      <View style={styles.centered}>
        <Text style={styles.error} accessibilityRole="alert">
          {error || t("filmNotFound")}
        </Text>
        <Pressable
          onPress={onLeave}
          hitSlop={16}
          accessibilityRole="button"
          accessibilityLabel={t("back")}
        >
          <Text style={styles.link}>{t("back")}</Text>
        </Pressable>
      </View>
    );
  }

  const shotsLabel = film.unlimited_shots
    ? t("unlimitedShots")
    : t("shotsEach", { count: film.shot_limit });
  const canJoin =
    !film.is_closed && !joining && Boolean(name.trim()) && (!film.requires_pin || Boolean(pin.trim()));

  const gallery = film.is_developed ? (
        <View style={styles.gallery}>
          <Text style={styles.section}>
            {film.instant_reveal ? t("liveGallery") : t("gallery")}
          </Text>
          {!film.shared_gallery ? (
            <Text style={styles.meta}>
              {token ? t("privateAlbumOwn") : t("privateAlbum")}
            </Text>
          ) : null}
          {/* The join form shows its own errors; once it is gone, a failed save
              or report has to surface here or nobody sees it. */}
          {error && (token || film.is_closed) ? (
            <Text style={styles.error} accessibilityRole="alert">
              {error}
            </Text>
          ) : null}
          {photos.length === 0 ? (
            film.shared_gallery ? (
              <Text style={styles.meta}>{t("noPhotosYet")}</Text>
            ) : token ? (
              <Text style={styles.meta}>{t("privateAlbumEmpty")}</Text>
            ) : null
          ) : (
            photos.map((photo) => (
              <View key={photo.shot_id} style={styles.shot}>
                {photo.kind === "clip" ? (
                  <ClipTile
                    url={photo.url}
                    posterUrl={photo.poster_url}
                    guestName={photo.guest_name}
                    durationMs={photo.duration_ms}
                    style={styles.image}
                  />
                ) : (
                  <Image source={{ uri: photo.url }} style={styles.image} />
                )}
                <View style={styles.shotFooter}>
                  <Text style={styles.caption}>{photo.guest_name}</Text>
                  <View style={styles.shotActions}>
                    {/* Anyone who can see the photo may keep it. */}
                    <Pressable
                      onPress={() => void save(photo)}
                      disabled={saving.has(photo.shot_id)}
                      hitSlop={12}
                      accessibilityRole="button"
                      accessibilityState={{ busy: saving.has(photo.shot_id) }}
                      accessibilityLabel={t(
                        photo.kind === "clip" ? "saveClipBy" : "savePhotoBy",
                        { name: photo.guest_name },
                      )}
                    >
                      <Text style={styles.actionLabel}>{t("save")}</Text>
                    </Pressable>
                    {token ? (
                      reported.has(photo.shot_id) ? (
                        <Text style={styles.reportedLabel}>{t("reported")}</Text>
                      ) : (
                        <Pressable
                          onPress={() => void report(photo.shot_id)}
                          hitSlop={12}
                          accessibilityRole="button"
                          accessibilityLabel={t("reportPhotoBy", {
                            name: photo.guest_name,
                          })}
                        >
                          <Text style={styles.reportLabel}>{t("report")}</Text>
                        </Pressable>
                      )
                    ) : null}
                  </View>
                </View>
              </View>
            ))
          )}
        </View>
  ) : null;

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <View style={styles.topRow}>
        <Pressable
          onPress={onLeave}
          hitSlop={16}
          accessibilityRole="button"
          accessibilityLabel={t("back")}
        >
          <Text style={styles.link}>{t("filmsNav")}</Text>
        </Pressable>
        <LanguagePicker />
      </View>
      <Text style={styles.kicker}>{t("brand")}</Text>
      <Text style={styles.title}>{film.title}</Text>
      <Text style={styles.meta}>
        {t("guestLine", {
          guestCount: film.guest_count,
          guestCap: film.guest_cap,
          shotsLabel,
        })}
      </Text>

      {!token && !film.is_closed ? (
        <View style={styles.form}>
          <Text style={styles.meta} accessibilityRole="text">
            {t("joinLabel")}
          </Text>
          <TextInput
            value={name}
            onChangeText={setName}
            placeholder={t("namePlaceholder")}
            placeholderTextColor="#71717a"
            autoFocus
            autoComplete="name"
            textContentType="name"
            returnKeyType="go"
            onSubmitEditing={() => void onJoin()}
            accessibilityLabel={t("namePlaceholder")}
            maxLength={80}
            style={styles.input}
          />
          {film.requires_pin ? (
            <>
              <Text style={styles.meta} accessibilityRole="text">
                {t("pinLabel")}
              </Text>
              <TextInput
                value={pin}
                onChangeText={setPin}
                placeholder={t("pinPlaceholder")}
                placeholderTextColor="#71717a"
                keyboardType="number-pad"
                autoComplete="off"
                returnKeyType="go"
                onSubmitEditing={() => void onJoin()}
                accessibilityLabel={t("pinPlaceholder")}
                maxLength={20}
                style={[styles.input, styles.pinInput]}
              />
            </>
          ) : null}
          {error ? (
            <Text style={styles.error} accessibilityRole="alert">
              {error}
            </Text>
          ) : null}
          <Pressable
            style={[styles.primary, !canJoin && styles.disabled]}
            disabled={!canJoin}
            onPress={() => void onJoin()}
            accessibilityRole="button"
            accessibilityState={{ disabled: !canJoin, busy: joining }}
            accessibilityLabel={t("joinFilm")}
          >
            <Text style={styles.primaryLabel}>
              {joining ? t("joining") : t("joinFilm")}
            </Text>
          </Pressable>
        </View>
      ) : null}

      {token && !film.is_closed ? (
        <CameraScreen
          code={code}
          token={token}
          film={film}
          remaining={remaining}
          onRemainingChange={setRemaining}
          clipsRemaining={clipsRemaining}
          onClipsRemainingChange={setClipsRemaining}
          onUnauthorized={() => {
            void clearGuestToken(code);
            setToken(null);
            setError(t("cameraExpired"));
          }}
        />
      ) : null}

      {film.is_closed ? (
        <Text style={styles.meta}>
          {film.is_developed ? t("shootingEndedLive") : t("shootingEnded")}
        </Text>
      ) : null}

      {gallery}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: 24, gap: 12, paddingBottom: 48 },
  topRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12 },
  kicker: {
    color: "#71717a",
    letterSpacing: 4,
    fontSize: 11,
    textTransform: "uppercase",
  },
  title: { color: "#fff", fontSize: 32, fontFamily: "Georgia" },
  meta: { color: "#a1a1aa", fontSize: 15 },
  section: { color: "#fff", fontSize: 22, marginTop: 8 },
  link: { color: "#d4d4d8", fontSize: 16 },
  form: { gap: 12, marginTop: 8 },
  input: {
    borderWidth: 1,
    borderColor: "#27272a",
    borderRadius: 10,
    color: "#fff",
    paddingHorizontal: 12,
    paddingVertical: 14,
    fontSize: 16,
  },
  pinInput: { letterSpacing: 6 },
  shotFooter: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  shotActions: { flexDirection: "row", alignItems: "center", gap: 20 },
  actionLabel: { color: "#fff", fontSize: 13 },
  reportLabel: { color: "#a1a1aa", fontSize: 13 },
  reportedLabel: { color: "#71717a", fontSize: 13 },
  primary: {
    backgroundColor: "#fff",
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
  },
  primaryLabel: { color: "#000", fontWeight: "600" },
  disabled: { opacity: 0.4 },
  error: { color: "#f87171" },
  gallery: { gap: 12 },
  shot: { gap: 4 },
  image: { width: "100%", aspectRatio: 3 / 4, borderRadius: 12, backgroundColor: "#18181b" },
  caption: { color: "#a1a1aa", fontSize: 12 },
});
