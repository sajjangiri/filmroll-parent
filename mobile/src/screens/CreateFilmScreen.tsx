import { useEffect, useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  createFilm,
  loadHostName,
  rememberHostedFilm,
  saveHostName,
  saveHostToken,
} from "../api/client";

type Props = {
  onCreated: (code: string) => void;
  onBack: () => void;
};

export function CreateFilmScreen({ onCreated, onBack }: Props) {
  const [title, setTitle] = useState("");
  const [hostName, setHostName] = useState("");
  const [showOptions, setShowOptions] = useState(false);
  const [hoursOpen, setHoursOpen] = useState("24");
  const [revealHours, setRevealHours] = useState("24");
  const [instantReveal, setInstantReveal] = useState(false);
  const [sharedGallery, setSharedGallery] = useState(true);
  const [shotLimit, setShotLimit] = useState("8");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void loadHostName().then((saved) => {
      if (saved) setHostName(saved);
    });
  }, []);

  async function onSubmit() {
    setBusy(true);
    setError("");
    try {
      const now = Date.now();
      const hours = Math.max(1, Number(hoursOpen) || 24);
      const reveal = Math.max(0, Number(revealHours) || 24);
      const shots = Math.max(1, Math.min(40, Number(shotLimit) || 8));

      const created = await createFilm({
        title: title.trim() || "Untitled film",
        event_type: "party",
        closes_at: new Date(now + hours * 3_600_000).toISOString(),
        ...(instantReveal
          ? { instant_reveal: true }
          : { reveal_at: new Date(now + reveal * 3_600_000).toISOString() }),
        shot_limit: shots,
        guest_cap: 5,
        shared_gallery: sharedGallery,
        ...(email.trim() ? { host_email: email.trim() } : {}),
      });

      await saveHostToken(created.film.code, created.host_token);
      await rememberHostedFilm(created.film.code, created.film.title);
      if (hostName.trim()) await saveHostName(hostName.trim());
      onCreated(created.film.code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create film");
      setBusy(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Pressable onPress={onBack}>
        <Text style={styles.link}>← Back</Text>
      </Pressable>
      <Text style={styles.kicker}>Step 1 of 3 · Create</Text>
      <Text style={styles.title}>Create a film</Text>
      <Text style={styles.copy}>
        Name it and say how long it stays open. You can invite people next.
      </Text>

      <View style={styles.field}>
        <Text style={styles.label}>Film name</Text>
        <TextInput
          value={title}
          onChangeText={setTitle}
          placeholder="Maya and Jon's wedding"
          placeholderTextColor="#71717a"
          style={styles.input}
        />
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Your name</Text>
        <TextInput
          value={hostName}
          onChangeText={setHostName}
          placeholder="Shown on the photos you take"
          placeholderTextColor="#71717a"
          autoComplete="name"
          textContentType="name"
          style={styles.input}
        />
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Open for (hours)</Text>
        <TextInput
          value={hoursOpen}
          onChangeText={setHoursOpen}
          keyboardType="number-pad"
          style={styles.input}
        />
      </View>

      <Pressable
        onPress={() => setShowOptions((current) => !current)}
        accessibilityRole="button"
        accessibilityState={{ expanded: showOptions }}
        hitSlop={12}
      >
        <Text style={styles.link}>{showOptions ? "Fewer options ▴" : "More options ▾"}</Text>
      </Pressable>

      {showOptions ? (
        <View style={styles.options}>
          {instantReveal ? null : (
            <View style={styles.field}>
              <Text style={styles.label}>Reveal after (hours)</Text>
              <TextInput
                value={revealHours}
                onChangeText={setRevealHours}
                keyboardType="number-pad"
                style={styles.input}
              />
            </View>
          )}

          <Pressable
            onPress={() => setInstantReveal((current) => !current)}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: instantReveal }}
            style={styles.checkRow}
          >
            <View style={[styles.box, instantReveal && styles.boxOn]} />
            <Text style={styles.copy}>
              Show photos as they are taken. Guests cannot un-see a shot, so this
              stays on for the life of the film.
            </Text>
          </Pressable>

          <Pressable
            onPress={() => setSharedGallery((current) => !current)}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: !sharedGallery }}
            style={styles.checkRow}
          >
            <View style={[styles.box, !sharedGallery && styles.boxOn]} />
            <Text style={styles.copy}>
              Only each guest sees their own photos. You still get every shot in
              the host inbox and the ZIP. You can change this later.
            </Text>
          </Pressable>

          <View style={styles.field}>
            <Text style={styles.label}>Shots per guest</Text>
            <TextInput
              value={shotLimit}
              onChangeText={setShotLimit}
              keyboardType="number-pad"
              style={styles.input}
            />
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>Your email (optional)</Text>
            <TextInput
              value={email}
              onChangeText={setEmail}
              placeholder="Recover host tools if this phone is cleared"
              placeholderTextColor="#71717a"
              keyboardType="email-address"
              autoCapitalize="none"
              style={styles.input}
            />
          </View>
        </View>
      ) : null}

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Pressable
        style={[styles.primary, busy && styles.disabled]}
        disabled={busy}
        onPress={() => void onSubmit()}
      >
        <Text style={styles.primaryLabel}>{busy ? "Creating…" : "Create your film"}</Text>
      </Pressable>

      <Text style={styles.hint}>
        Five guests are free. Upgrade capacity on the web host page until in-app
        purchases ship.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: 24, gap: 16, paddingBottom: 48 },
  kicker: {
    color: "#71717a",
    letterSpacing: 4,
    fontSize: 11,
    textTransform: "uppercase",
  },
  title: { color: "#fff", fontSize: 32, fontFamily: "Georgia", lineHeight: 38 },
  copy: { color: "#a1a1aa", fontSize: 16, lineHeight: 22, flex: 1 },
  checkRow: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  box: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "#52525b",
    marginTop: 2,
  },
  boxOn: { backgroundColor: "#fff", borderColor: "#fff" },
  link: { color: "#a1a1aa", fontSize: 14, marginBottom: 8 },
  field: { gap: 8 },
  options: { gap: 16 },
  label: { color: "#a1a1aa", fontSize: 14 },
  input: {
    borderWidth: 1,
    borderColor: "#27272a",
    borderRadius: 10,
    color: "#fff",
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  primary: {
    backgroundColor: "#fff",
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 8,
  },
  primaryLabel: { color: "#000", fontWeight: "600" },
  disabled: { opacity: 0.4 },
  error: { color: "#f87171", fontSize: 14 },
  hint: { color: "#71717a", fontSize: 12, lineHeight: 18 },
});
