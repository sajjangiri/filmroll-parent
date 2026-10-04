import { useState } from "react";
import {
  Image,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
  type ImageStyle,
  type StyleProp,
} from "react-native";
import { useVideoPlayer, VideoView } from "expo-video";

import { useI18n } from "../i18n/I18nProvider";

type Props = {
  url: string;
  posterUrl: string | null;
  guestName: string;
  durationMs: number | null;
  style: StyleProp<ImageStyle>;
};

/**
 * A clip in a gallery list: the poster frame until tapped, then a full-screen
 * player. The first signed URL is kept for the life of the tile, since
 * galleries re-poll and a swapped source would restart a clip mid-watch.
 */
export function ClipTile({ url, posterUrl, guestName, durationMs, style }: Props) {
  const { t } = useI18n();
  const [src] = useState(url);
  const [open, setOpen] = useState(false);
  const seconds = durationMs ? Math.round(durationMs / 1000) : null;

  return (
    <>
      <Pressable
        onPress={() => setOpen(true)}
        accessibilityRole="button"
        accessibilityLabel={t("playClip", { name: guestName })}
      >
        {posterUrl ? (
          <Image source={{ uri: posterUrl }} style={style} />
        ) : (
          <View style={[style as object, styles.blank]} />
        )}
        <View style={styles.badge} pointerEvents="none">
          <Text style={styles.badgeLabel}>▶{seconds ? ` ${seconds}s` : ""}</Text>
        </View>
      </Pressable>
      <Modal
        visible={open}
        animationType="fade"
        onRequestClose={() => setOpen(false)}
        supportedOrientations={["portrait", "landscape"]}
      >
        {open ? <Player url={src} onClose={() => setOpen(false)} /> : null}
      </Modal>
    </>
  );
}

function Player({ url, onClose }: { url: string; onClose: () => void }) {
  const { t } = useI18n();
  const player = useVideoPlayer(url, (created) => {
    created.play();
  });
  return (
    <View style={styles.player}>
      <VideoView player={player} style={styles.video} nativeControls contentFit="contain" />
      <Pressable
        style={styles.close}
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel={t("close")}
      >
        <Text style={styles.closeLabel}>{t("close")}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  blank: { backgroundColor: "#18181b" },
  badge: {
    position: "absolute",
    top: 8,
    right: 8,
    backgroundColor: "rgba(0,0,0,0.7)",
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  badgeLabel: { color: "#fff", fontSize: 13, fontWeight: "600" },
  player: { flex: 1, backgroundColor: "#000", justifyContent: "center" },
  video: { width: "100%", height: "100%" },
  close: {
    position: "absolute",
    top: 56,
    right: 16,
    backgroundColor: "rgba(0,0,0,0.7)",
    borderRadius: 999,
    minHeight: 44,
    paddingHorizontal: 16,
    justifyContent: "center",
  },
  closeLabel: { color: "#fff", fontSize: 15, fontWeight: "600" },
});
