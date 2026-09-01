import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { Linking, SafeAreaView, StyleSheet } from "react-native";

import { filmCodeFromUrl } from "./src/api/client";
import { FilmScreen } from "./src/screens/FilmScreen";
import { HomeScreen } from "./src/screens/HomeScreen";

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
        <HomeScreen code={code} onCodeChange={setCode} onOpen={setOpen} />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#000" },
});
