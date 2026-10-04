import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { listHostedFilms } from "../api/client";
import type { HostedFilm } from "../api/client";
import { LanguagePicker } from "../components/LanguagePicker";
import { useI18n } from "../i18n/I18nProvider";

type Props = {
  code: string;
  onCodeChange: (value: string) => void;
  onCreate: () => void;
  onOpenHost: (code: string) => void;
  onOpenGuest: (code: string) => void;
};

export function HomeScreen({
  code,
  onCodeChange,
  onCreate,
  onOpenHost,
  onOpenGuest,
}: Props) {
  const { t } = useI18n();
  const ready = code.trim().length >= 4;
  const [hosted, setHosted] = useState<HostedFilm[]>([]);

  useEffect(() => {
    void listHostedFilms().then(setHosted);
  }, []);

  return (
    <ScrollView contentContainerStyle={styles.home}>
      <View style={styles.header}>
        <Text style={styles.kicker}>{t("brand")}</Text>
        <LanguagePicker />
      </View>
      <Text style={styles.title}>{t("homeTitle")}</Text>
      <Text style={styles.copy}>{t("homeCopy")}</Text>

      <Pressable
        style={styles.primary}
        onPress={onCreate}
        accessibilityRole="button"
        accessibilityLabel={t("createFilm")}
      >
        <Text style={styles.primaryLabel}>{t("createFilm")}</Text>
      </Pressable>

      {hosted.length > 0 ? (
        <View style={styles.hosted}>
          <Text style={styles.hostedLabel}>{t("yourFilms")}</Text>
          {hosted.map((film) => (
            <Pressable
              key={film.code}
              style={styles.hostedRow}
              onPress={() => onOpenHost(film.code)}
              accessibilityRole="button"
              accessibilityLabel={`${film.title}, ${film.code}`}
            >
              <Text style={styles.hostedTitle}>{film.title}</Text>
              <Text style={styles.hostedCode}>{film.code}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      <View style={styles.divider}>
        <View style={styles.line} />
        <Text style={styles.dividerLabel}>{t("orJoin")}</Text>
        <View style={styles.line} />
      </View>

      <TextInput
        value={code}
        onChangeText={(value) => onCodeChange(value.toUpperCase())}
        placeholder={t("filmCodePlaceholder")}
        placeholderTextColor="#71717a"
        autoCapitalize="characters"
        autoCorrect={false}
        maxLength={12}
        accessibilityLabel={t("filmCodePlaceholder")}
        returnKeyType="go"
        onSubmitEditing={() => ready && onOpenGuest(code.trim().toUpperCase())}
        style={styles.input}
      />
      <Pressable
        style={[styles.secondary, !ready && styles.disabled]}
        disabled={!ready}
        onPress={() => onOpenGuest(code.trim().toUpperCase())}
        accessibilityRole="button"
        accessibilityState={{ disabled: !ready }}
        accessibilityLabel={t("joinFilm")}
      >
        <Text style={styles.secondaryLabel}>{t("joinFilm")}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  home: { flexGrow: 1, padding: 24, gap: 16, justifyContent: "center" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  kicker: {
    color: "#71717a",
    letterSpacing: 4,
    fontSize: 11,
    textTransform: "uppercase",
  },
  title: { color: "#fff", fontSize: 32, fontFamily: "Georgia", lineHeight: 38 },
  copy: { color: "#a1a1aa", fontSize: 16, lineHeight: 22 },
  hosted: { gap: 8 },
  hostedLabel: {
    color: "#71717a",
    fontSize: 11,
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  hostedRow: {
    borderWidth: 1,
    borderColor: "#27272a",
    borderRadius: 12,
    padding: 14,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  hostedTitle: { color: "#fff", fontSize: 16, flex: 1, marginRight: 12 },
  hostedCode: { color: "#71717a", fontSize: 14, letterSpacing: 2, fontFamily: "Courier" },
  divider: { flexDirection: "row", alignItems: "center", gap: 12, marginVertical: 4 },
  line: { flex: 1, height: 1, backgroundColor: "#27272a" },
  dividerLabel: { color: "#71717a", fontSize: 12, textTransform: "uppercase" },
  input: {
    borderWidth: 1,
    borderColor: "#27272a",
    borderRadius: 10,
    color: "#fff",
    paddingHorizontal: 12,
    paddingVertical: 14,
    fontSize: 18,
    letterSpacing: 2,
  },
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
  disabled: { opacity: 0.4 },
});
