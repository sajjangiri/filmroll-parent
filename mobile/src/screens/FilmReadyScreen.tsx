import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { API_URL, getFilm } from "../api/client";
import type { FilmPublic } from "../api/types";

type Props = {
  code: string;
  onStartShooting: () => void;
  onOpenFilm: () => void;
};

export function FilmReadyScreen({ code, onStartShooting, onOpenFilm }: Props) {
  const [film, setFilm] = useState<FilmPublic | null>(null);

  useEffect(() => {
    void getFilm(code)
      .then(setFilm)
      .catch(() => setFilm(null));
  }, [code]);

  async function shareInvite() {
    const link = film?.join_url ?? code;
    const title = film?.title ?? "our film";
    await Share.share({
      message: `Join ${title} on Filmroll and take a few photos with us: ${link}`,
    });
  }

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Text style={styles.kicker}>Step 2 of 3 · Invite</Text>
      <Text style={styles.title}>Your film is ready</Text>
      <Text style={styles.copy}>
        Put this QR code where people will see it, or send the link. Guests join
        with just their name — no account, no download.
      </Text>

      <View style={styles.card}>
        {film ? (
          <Image
            source={{ uri: `${API_URL}/v1/films/${code}/qr.png` }}
            style={styles.qr}
            accessibilityLabel={`QR code to join ${film.title}`}
          />
        ) : (
          <View style={[styles.qr, styles.qrLoading]}>
            <ActivityIndicator />
          </View>
        )}
        <Text style={styles.cardLabel}>Film code</Text>
        <Text style={styles.code} accessibilityLabel={code.split("").join(" ")}>
          {code}
        </Text>
      </View>

      <Pressable
        style={styles.primary}
        onPress={() => void shareInvite()}
        accessibilityRole="button"
      >
        <Text style={styles.primaryLabel}>Share invite</Text>
      </Pressable>
      <Pressable style={styles.secondary} onPress={onStartShooting} accessibilityRole="button">
        <Text style={styles.secondaryLabel}>Start shooting</Text>
      </Pressable>
      <Pressable
        style={styles.textButton}
        onPress={onOpenFilm}
        accessibilityRole="button"
        hitSlop={12}
      >
        <Text style={styles.link}>Go to your film →</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { flexGrow: 1, padding: 24, gap: 16, justifyContent: "center", paddingBottom: 48 },
  kicker: {
    color: "#71717a",
    letterSpacing: 4,
    fontSize: 11,
    textTransform: "uppercase",
  },
  title: { color: "#fff", fontSize: 32, fontFamily: "Georgia", lineHeight: 38 },
  copy: { color: "#a1a1aa", fontSize: 16, lineHeight: 22 },
  card: {
    borderWidth: 1,
    borderColor: "#27272a",
    borderRadius: 16,
    padding: 20,
    gap: 10,
    alignItems: "center",
  },
  qr: { width: 260, height: 260, backgroundColor: "#fff", borderRadius: 8 },
  qrLoading: { alignItems: "center", justifyContent: "center" },
  cardLabel: {
    color: "#71717a",
    fontSize: 11,
    letterSpacing: 2,
    textTransform: "uppercase",
    marginTop: 4,
  },
  code: { color: "#fff", fontSize: 36, letterSpacing: 8, fontFamily: "Courier" },
  primary: {
    backgroundColor: "#fff",
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
  },
  primaryLabel: { color: "#000", fontWeight: "600" },
  secondary: {
    borderWidth: 1,
    borderColor: "#52525b",
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
  },
  secondaryLabel: { color: "#fff", fontWeight: "600" },
  textButton: { alignSelf: "center" },
  link: { color: "#a1a1aa", fontSize: 14 },
});
