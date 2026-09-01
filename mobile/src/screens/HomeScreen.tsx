import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

type Props = {
  code: string;
  onCodeChange: (value: string) => void;
  onOpen: (code: string) => void;
};

export function HomeScreen({ code, onCodeChange, onOpen }: Props) {
  const ready = code.trim().length >= 4;

  return (
    <View style={styles.home}>
      <Text style={styles.kicker}>Filmroll</Text>
      <Text style={styles.title}>A disposable camera for the people at your event.</Text>
      <Text style={styles.copy}>
        Hosts create and pay on the web. Guests join here, or by scanning the
        same QR that opens the PWA on Android.
      </Text>
      <TextInput
        value={code}
        onChangeText={(value) => onCodeChange(value.toUpperCase())}
        placeholder="Film code"
        placeholderTextColor="#71717a"
        autoCapitalize="characters"
        autoCorrect={false}
        maxLength={12}
        style={styles.input}
      />
      <Pressable
        style={[styles.primary, !ready && styles.disabled]}
        disabled={!ready}
        onPress={() => onOpen(code.trim().toUpperCase())}
      >
        <Text style={styles.primaryLabel}>Open film</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
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
