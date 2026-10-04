import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { BackHandler, Linking, StyleSheet } from "react-native";
import * as Notifications from "expo-notifications";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { parseFilmrollUrl } from "./src/api/client";
import { I18nProvider } from "./src/i18n/I18nProvider";
import { filmCodeFromNotificationData } from "./src/notifications";
import { CreateFilmScreen } from "./src/screens/CreateFilmScreen";
import { FilmReadyScreen } from "./src/screens/FilmReadyScreen";
import { FilmScreen } from "./src/screens/FilmScreen";
import { HomeScreen } from "./src/screens/HomeScreen";
import { HostScreen } from "./src/screens/HostScreen";

type Screen =
  | { kind: "home" }
  | { kind: "create" }
  | { kind: "ready"; code: string }
  | { kind: "host"; code: string; magic?: string; seat?: string }
  | { kind: "guest"; code: string; asHost?: boolean };

export default function App() {
  const [code, setCode] = useState("");
  const [screen, setScreen] = useState<Screen>({ kind: "home" });

  useEffect(() => {
    function apply(url: string | null) {
      if (!url) return;
      const link = parseFilmrollUrl(url);
      if (!link) return;
      if (link.role === "host") {
        setScreen({
          kind: "host",
          code: link.code,
          magic: link.magic ?? undefined,
          seat: link.seat ?? undefined,
        });
      } else {
        setScreen({ kind: "guest", code: link.code });
      }
    }

    void Linking.getInitialURL().then(apply);
    const sub = Linking.addEventListener("url", (event) => apply(event.url));
    return () => sub.remove();
  }, []);

  useEffect(() => {
    function openFromNotification(response: Notifications.NotificationResponse) {
      const code = filmCodeFromNotificationData(
        response.notification.request.content.data,
      );
      if (code) setScreen({ kind: "guest", code });
    }

    void Notifications.getLastNotificationResponseAsync().then((response) => {
      if (response) openFromNotification(response);
    });
    const sub = Notifications.addNotificationResponseReceivedListener(openFromNotification);
    return () => sub.remove();
  }, []);

  function goHome() {
    setScreen({ kind: "home" });
    setCode("");
  }

  // Android's system back: step out one level instead of closing the app.
  useEffect(() => {
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      if (screen.kind === "home") return false;
      if (screen.kind === "guest" && screen.asHost) {
        setScreen({ kind: "host", code: screen.code });
      } else if (screen.kind === "ready") {
        setScreen({ kind: "host", code: screen.code });
      } else {
        goHome();
      }
      return true;
    });
    return () => sub.remove();
  }, [screen]);

  return (
    <SafeAreaProvider>
    <I18nProvider>
      <SafeAreaView style={styles.safe}>
        <StatusBar style="light" />
        {screen.kind === "create" ? (
        <CreateFilmScreen
          onBack={goHome}
          onCreated={(createdCode) => setScreen({ kind: "ready", code: createdCode })}
        />
      ) : screen.kind === "ready" ? (
        <FilmReadyScreen
          code={screen.code}
          onStartShooting={() => setScreen({ kind: "guest", code: screen.code, asHost: true })}
          onOpenFilm={() => setScreen({ kind: "host", code: screen.code })}
        />
      ) : screen.kind === "host" ? (
        <HostScreen
          code={screen.code}
          magicToken={screen.magic}
          seatInvite={screen.seat}
          onBack={goHome}
          onTakePhotos={() => setScreen({ kind: "guest", code: screen.code, asHost: true })}
        />
      ) : screen.kind === "guest" ? (
        <FilmScreen
          code={screen.code}
          joinAsHost={screen.asHost}
          onLeave={
            screen.asHost ? () => setScreen({ kind: "host", code: screen.code }) : goHome
          }
        />
      ) : (
        <HomeScreen
          code={code}
          onCodeChange={setCode}
          onCreate={() => setScreen({ kind: "create" })}
          onOpenHost={(hostCode) => setScreen({ kind: "host", code: hostCode })}
          onOpenGuest={(joinCode) => setScreen({ kind: "guest", code: joinCode })}
        />
      )}
      </SafeAreaView>
    </I18nProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#000" },
});
