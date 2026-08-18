import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import {
  Linking,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { filmCodeFromUrl } from "./src/api";
import { FilmScreen } from "./src/FilmScreen";

export default function App() {
  const [code, setCode] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    function apply(url: string | null) {
      if (!url) return;
      const found = filmCodeFromUrl(url);
      if (found) setOpen(found);
    }

    void Linking.getInitialURL().then(apply);
    const sub = Linking.addEventListener("url", (event) => apply(event.url));
    return () => sub.remove();
  }, []);

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />
      {open ? (
        <FilmScreen code={open} onLeave={() => setOpen(null)} />
      ) : (
        <View style={styles.home}>
          <Text style={styles.kicker}>Filmroll</Text>
          <Text style={styles.title}>A disposable camera for the people at your event.</Text>
          <Text style={styles.copy}>
            Hosts create and pay on the web. Guests join here, or by scanning the
            same QR that opens the PWA on Android.
          </Text>
          <TextInput
            value={code}
            onChangeText={(value) => setCode(value.toUpperCase())}
            placeholder="Film code"
            placeholderTextColor="#71717a"
            autoCapitalize="characters"
            autoCorrect={false}
            maxLength={12}
            style={styles.input}
          />
          <Pressable
            style={[styles.primary, code.trim().length < 4 && styles.disabled]}
            disabled={code.trim().length < 4}
            onPress={() => setOpen(code.trim().toUpperCase())}
          >
            <Text style={styles.primaryLabel}>Open film</Text>
          </Pressable>
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#000" },
  home: { flex: 1, padding: 24, gap: 16, justifyContent: "center" },
  kicker: {
    color: "#71717a",
    letterSpacing: 4,
    fontSize: 11,
    textTransform: "uppercase",
  },
  title: { color: "#fff", fontSize: 32, fontFamily: "Georgia", lineHeight: 38 },
  copy: { color: "#a1a1aa", fontSize: 16, lineHeight: 22 },
  input: {
    borderWidth: 1,
    borderColor: "#27272a",
    borderRadius: 10,
    color: "#fff",
    paddingHorizontal: 12,
    paddingVertical: 12,
    letterSpacing: 2,
  },
  primary: {
    backgroundColor: "#fff",
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
  },
  primaryLabel: { color: "#000", fontWeight: "600" },
  disabled: { opacity: 0.4 },
});
