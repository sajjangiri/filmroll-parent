import { useCallback, useEffect, useState } from "react";
import {
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
  saveGuestToken,
} from "./api";
import { CameraScreen } from "./CameraScreen";
import type { FilmPublic, GalleryPhoto } from "./types";

export function FilmScreen({
  code,
  onLeave,
}: {
  code: string;
  onLeave: () => void;
}) {
  const [film, setFilm] = useState<FilmPublic | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState(false);
  const [photos, setPhotos] = useState<GalleryPhoto[]>([]);

  const refresh = useCallback(async () => {
    try {
      const loaded = await getFilm(code);
      setFilm(loaded);
      if (loaded.is_developed) {
        const gallery = await getGallery(code);
        setPhotos(gallery.photos);
      }
    } catch {
      setError("Film not found");
      setFilm(null);
    }
    const saved = await loadGuestToken(code);
    setToken(saved);
    setLoading(false);
  }, [code]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onJoin() {
    const trimmed = name.trim();
    if (!trimmed) return;
    setJoining(true);
    setError("");
    try {
      const joined = await joinFilm(code, trimmed);
      await saveGuestToken(code, joined.guest_token);
      setToken(joined.guest_token);
      setRemaining(joined.shots_remaining);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "This film is full."
          : err instanceof ApiError && err.status === 410
            ? "This film has closed."
            : "Could not join.",
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
        <Text style={styles.error}>{error || "Film not found"}</Text>
        <Pressable onPress={onLeave}>
          <Text style={styles.link}>Back</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Pressable onPress={onLeave}>
        <Text style={styles.link}>← Films</Text>
      </Pressable>
      <Text style={styles.kicker}>Filmroll</Text>
      <Text style={styles.title}>{film.title}</Text>
      <Text style={styles.meta}>
        {film.guest_count}/{film.guest_cap} guests ·{" "}
        {film.unlimited_shots ? "unlimited shots" : `${film.shot_limit} shots each`}
      </Text>

      {film.is_developed ? (
        <View style={styles.gallery}>
          <Text style={styles.section}>Gallery</Text>
          {photos.length === 0 ? (
            <Text style={styles.meta}>No photos yet.</Text>
          ) : (
            photos.map((photo) => (
              <View key={photo.shot_id} style={styles.shot}>
                <Image source={{ uri: photo.url }} style={styles.image} />
                <Text style={styles.caption}>{photo.guest_name}</Text>
              </View>
            ))
          )}
        </View>
      ) : !token ? (
        <View style={styles.form}>
          <Text style={styles.meta}>Enter your name to pick up a camera. No account needed.</Text>
          <TextInput
            value={name}
            onChangeText={setName}
            placeholder="Your name"
            placeholderTextColor="#71717a"
            maxLength={80}
            style={styles.input}
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <Pressable
            style={[styles.primary, (film.is_closed || joining) && styles.disabled]}
            disabled={film.is_closed || joining}
            onPress={() => void onJoin()}
          >
            <Text style={styles.primaryLabel}>
              {film.is_closed ? "This film is closed" : joining ? "Joining…" : "Join the film"}
            </Text>
          </Pressable>
        </View>
      ) : film.is_closed ? (
        <Text style={styles.meta}>Shooting has ended. Come back when the film develops.</Text>
      ) : (
        <CameraScreen
          code={code}
          token={token}
          film={film}
          remaining={remaining}
          onRemainingChange={setRemaining}
          onUnauthorized={() => {
            void clearGuestToken(code);
            setToken(null);
          }}
        />
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: 24, gap: 12, paddingBottom: 48 },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12 },
  kicker: {
    color: "#71717a",
    letterSpacing: 4,
    fontSize: 11,
    textTransform: "uppercase",
  },
  title: { color: "#fff", fontSize: 32, fontFamily: "Georgia" },
  meta: { color: "#a1a1aa", fontSize: 14 },
  section: { color: "#fff", fontSize: 22, marginTop: 8 },
  link: { color: "#a1a1aa", fontSize: 14 },
  form: { gap: 12, marginTop: 8 },
  input: {
    borderWidth: 1,
    borderColor: "#27272a",
    borderRadius: 10,
    color: "#fff",
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
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
