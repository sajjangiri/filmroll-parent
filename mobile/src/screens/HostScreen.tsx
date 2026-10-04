import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Linking,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  API_URL,
  ApiError,
  WEB_URL,
  consumeMagicSession,
  getExport,
  getFilm,
  getHostAccount,
  getReview,
  hideShot,
  loadHostToken,
  recoverHost,
  revealFilm,
  saveHostToken,
  setJoinPin,
  clearJoinPin,
  claimSeat,
  clearDeleted,
  createSeat,
  deleteFilm,
  listSeats,
  loadDeleted,
  loadStaffRole,
  rememberHostedFilm,
  restoreFilm,
  revokeSeat,
  saveDeleted,
  saveStaffRole,
  startExport,
  unhideShot,
  updateFilm,
} from "../api/client";
import { ClipTile } from "../components/ClipTile";
import type {
  ExportResponse,
  FilmDeleted,
  FilmPublic,
  ReviewPhoto,
  SeatCreated,
  SeatPublic,
  StaffRole,
} from "../api/types";

// Mirrors DELETED_FILM_GRACE_DAYS on the API. Only used as copy before the film
// is deleted; afterwards the real deadline comes back on the response.
const GRACE_DAYS = 30;

type Props = {
  code: string;
  magicToken?: string;
  seatInvite?: string;
  onBack: () => void;
  onTakePhotos: () => void;
};

type Tab = "photos" | "invite" | "settings";

export function HostScreen({ code, magicToken, seatInvite, onBack, onTakePhotos }: Props) {
  const [tab, setTab] = useState<Tab>("photos");
  const [role, setRole] = useState<StaffRole>("host");
  const [seats, setSeats] = useState<SeatPublic[]>([]);
  const [seatRole, setSeatRole] = useState<"cohost" | "photographer">("cohost");
  const [seatLabel, setSeatLabel] = useState("");
  const [newSeat, setNewSeat] = useState<SeatCreated | null>(null);
  const [invitingSeat, setInvitingSeat] = useState(false);
  const [film, setFilm] = useState<FilmPublic | null>(null);
  const [photos, setPhotos] = useState<ReviewPhoto[]>([]);
  const [exportState, setExportState] = useState<ExportResponse | null>(null);
  const [guestCap, setGuestCap] = useState("5");
  const [shotLimit, setShotLimit] = useState("8");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [hasHostKey, setHasHostKey] = useState(false);
  const [hostToken, setHostToken] = useState<string | null>(null);
  const [revealing, setRevealing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [savingCaps, setSavingCaps] = useState(false);
  const [savingVisibility, setSavingVisibility] = useState(false);
  const [hostEmail, setHostEmail] = useState("");
  const [recoverEmail, setRecoverEmail] = useState("");
  const [recoverBusy, setRecoverBusy] = useState(false);
  const [recoverSent, setRecoverSent] = useState(false);
  const [savingEmail, setSavingEmail] = useState(false);
  const [pinDraft, setPinDraft] = useState("");
  const [pinNote, setPinNote] = useState("");
  const [savingPin, setSavingPin] = useState(false);
  const [deleted, setDeleted] = useState<FilmDeleted | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const magicHandled = useRef(false);
  const seatHandled = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const loaded = await getFilm(code);
      setFilm(loaded);
      setGuestCap(String(loaded.guest_cap));
      setShotLimit(String(loaded.shot_limit));
      setDeleted(null);
      setError("");
    } catch (err) {
      const stashed =
        err instanceof ApiError && err.status === 404 ? await loadDeleted(code) : null;
      setDeleted(stashed);
      if (!stashed) setError("Film not found");
      setFilm(null);
      setLoading(false);
      return;
    }

    const token = await loadHostToken(code);
    setHostToken(token);
    setHasHostKey(Boolean(token));

    if (token) {
      const seat = await loadStaffRole(code);
      setRole(seat);
      try {
        const review = await getReview(code, token);
        setPhotos(review.photos);
        setExportState(await getExport(code, token));
        // The recovery email and who else has access are the owner's alone, so a
        // co-host must not even request them.
        if (seat === "host") {
          const account = await getHostAccount(code, token);
          setHostEmail(account.email ?? "");
          setSeats((await listSeats(code, token)).seats);
        }
      } catch (err) {
        if (err instanceof ApiError && err.status === 403) {
          setError(
            seat === "host"
              ? "This device does not have the host key for this film."
              : "Your access to this film was removed.",
          );
        }
      }
    }

    setLoading(false);
  }, [code]);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => {
      void refresh();
    }, 8000);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (!magicToken || magicHandled.current) return;
    magicHandled.current = true;
    void (async () => {
      try {
        const session = await consumeMagicSession(code, magicToken);
        await saveHostToken(code, session.host_token);
        // A magic link always restores the owner, even on a phone that had only
        // ever held a seat before.
        await saveStaffRole(code, "host");
        setRole("host");
        setHostToken(session.host_token);
        setHasHostKey(true);
        void refresh();
      } catch {
        setError("That recovery link is invalid or expired.");
      }
    })();
  }, [code, magicToken, refresh]);

  useEffect(() => {
    if (!seatInvite || seatHandled.current) return;
    seatHandled.current = true;
    void (async () => {
      try {
        const claimed = await claimSeat(code, seatInvite);
        await saveHostToken(code, claimed.token);
        await saveStaffRole(code, claimed.role);
        await rememberHostedFilm(code, claimed.film.title);
        setRole(claimed.role);
        setHostToken(claimed.token);
        setHasHostKey(true);
        void refresh();
      } catch {
        setError("That invite is invalid, expired, or has been revoked.");
      }
    })();
  }, [code, seatInvite, refresh]);

  async function inviteSeat() {
    if (!hostToken || !seatLabel.trim()) return;
    setInvitingSeat(true);
    setError("");
    try {
      const created = await createSeat(code, hostToken, {
        role: seatRole,
        label: seatLabel.trim(),
      });
      setNewSeat(created);
      setSeatLabel("");
      setSeats((current) => [...current, created.seat]);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "This film already has as many people as it can hold."
          : "Could not create that invite.",
      );
    } finally {
      setInvitingSeat(false);
    }
  }

  async function removeSeat(seat: SeatPublic) {
    if (!hostToken) return;
    setSeats((current) => current.filter((row) => row.id !== seat.id));
    if (newSeat?.seat.id === seat.id) setNewSeat(null);
    try {
      await revokeSeat(code, seat.id, hostToken);
    } catch {
      setSeats((current) => [...current, seat]);
      setError("Could not remove that person.");
    }
  }

  async function shareSeatInvite() {
    if (!newSeat || !film) return;
    const what = newSeat.seat.role === "cohost" ? "co-host" : "photographer";
    await Share.share({
      message: `You're a ${what} on ${film.title}. Open this to get access: ${newSeat.invite_url}`,
    });
  }

  async function onRecover() {
    const trimmed = recoverEmail.trim();
    if (!trimmed) return;
    setRecoverBusy(true);
    setError("");
    try {
      await recoverHost(code, trimmed);
      setRecoverSent(true);
    } catch {
      setError("Could not send a recovery email.");
    } finally {
      setRecoverBusy(false);
    }
  }

  async function onSaveEmail() {
    if (!hostToken) return;
    const trimmed = hostEmail.trim();
    if (!trimmed) return;
    setSavingEmail(true);
    setError("");
    try {
      await updateFilm(code, hostToken, { host_email: trimmed });
    } catch {
      setError("Could not save that email.");
    } finally {
      setSavingEmail(false);
    }
  }

  async function shareInvite() {
    if (!film) return;
    await Share.share({
      message: `Join ${film.title} on Filmroll and take a few photos with us: ${film.join_url ?? code}`,
    });
  }

  async function onReveal() {
    if (!hostToken) {
      setError("Host key missing. Open this from the device that created the film.");
      return;
    }
    setRevealing(true);
    setError("");
    try {
      setFilm(await revealFilm(code, hostToken));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? "That host key is not valid for this film."
          : "Could not develop the film.",
      );
    } finally {
      setRevealing(false);
    }
  }

  async function toggleHidden(photo: ReviewPhoto) {
    if (!hostToken) return;
    setPhotos((current) =>
      current.map((item) =>
        item.shot_id === photo.shot_id ? { ...item, hidden: !item.hidden } : item,
      ),
    );
    try {
      if (photo.hidden) await unhideShot(code, photo.shot_id, hostToken);
      else await hideShot(code, photo.shot_id, hostToken);
    } catch {
      setPhotos((current) =>
        current.map((item) =>
          item.shot_id === photo.shot_id ? { ...item, hidden: photo.hidden } : item,
        ),
      );
      setError("Could not update that photo.");
    }
  }

  async function toggleSharedGallery() {
    if (!hostToken || !film) return;
    setSavingVisibility(true);
    setError("");
    try {
      setFilm(
        await updateFilm(code, hostToken, { shared_gallery: !film.shared_gallery }),
      );
    } catch {
      setError("Could not update the film.");
    } finally {
      setSavingVisibility(false);
    }
  }

  async function savePin() {
    if (!hostToken) return;
    setSavingPin(true);
    setError("");
    try {
      setFilm(await setJoinPin(code, hostToken, pinDraft.trim()));
      setPinDraft("");
      setPinNote("Guests now need this PIN to join. Anyone already shooting stays in.");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 422
          ? "A PIN must be 4 to 8 digits."
          : "Could not set the PIN.",
      );
    } finally {
      setSavingPin(false);
    }
  }

  async function removePin() {
    if (!hostToken) return;
    setSavingPin(true);
    setError("");
    try {
      setFilm(await clearJoinPin(code, hostToken));
      setPinNote("Anyone with the code can join again.");
    } catch {
      setError("Could not remove the PIN.");
    } finally {
      setSavingPin(false);
    }
  }

  async function onSaveCaps() {
    if (!hostToken || !film) return;
    setSavingCaps(true);
    setError("");
    try {
      const cap = Math.max(film.guest_count, Number(guestCap) || film.guest_cap);
      const shots = Math.max(1, Math.min(500, Number(shotLimit) || film.shot_limit));
      setFilm(await updateFilm(code, hostToken, { guest_cap: cap, shot_limit: shots }));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "That cap is below people who already joined."
          : err instanceof ApiError && err.status === 402
            ? "Pay for a larger room to raise the guest cap."
            : "Could not update the film.",
      );
    } finally {
      setSavingCaps(false);
    }
  }

  async function onExport() {
    if (!hostToken) return;
    if (exportState?.status === "ready" && exportState.download_url) {
      await Share.share({ url: exportState.download_url, message: exportState.download_url });
      return;
    }
    setExporting(true);
    setError("");
    try {
      setExportState(await startExport(code, hostToken));
      for (let attempt = 0; attempt < 20; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        const next = await getExport(code, hostToken);
        setExportState(next);
        if (next.status === "ready" && next.download_url) {
          await Share.share({ url: next.download_url, message: next.download_url });
          break;
        }
        if (next.status === "failed") {
          setError("Export failed. Try again.");
          break;
        }
      }
    } catch {
      setError("Could not start the export.");
    } finally {
      setExporting(false);
    }
  }

  async function onDelete() {
    if (!hostToken) return;
    setDeleting(true);
    setError("");
    try {
      const result = await deleteFilm(code, hostToken);
      await saveDeleted(code, result);
      setDeleted(result);
      setFilm(null);
      setDeleteConfirm("");
    } catch {
      setError("Could not delete this film.");
    } finally {
      setDeleting(false);
    }
  }

  async function onRestore() {
    if (!hostToken) return;
    setRestoring(true);
    setError("");
    try {
      const restored = await restoreFilm(code, hostToken);
      await clearDeleted(code);
      setDeleted(null);
      setFilm(restored);
      void refresh();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 410
          ? "The grace period has passed and these photos are gone."
          : "Could not restore this film.",
      );
    } finally {
      setRestoring(false);
    }
  }

  function openWebHost() {
    void Linking.openURL(`${WEB_URL}/f/${code}/host`);
  }

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color="#fff" />
      </View>
    );
  }

  if (deleted) {
    const purgeDate = new Date(deleted.purge_at).toLocaleDateString(undefined, {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
    return (
      <ScrollView contentContainerStyle={styles.page}>
        <Pressable onPress={onBack} hitSlop={12}>
          <Text style={styles.link}>← Films</Text>
        </Pressable>
        <Text style={styles.title}>Film deleted</Text>
        <Text style={styles.hint}>
          {code} is gone for your guests. The photos themselves are kept until{" "}
          {purgeDate}, and are permanently destroyed after that.
        </Text>
        <Text style={styles.meta}>Restoring only works from this phone.</Text>
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <Pressable
          style={[styles.primary, (restoring || !hostToken) && styles.disabled]}
          disabled={restoring || !hostToken}
          onPress={() => void onRestore()}
          accessibilityRole="button"
        >
          <Text style={styles.primaryLabel}>
            {restoring ? "Restoring…" : "Restore this film"}
          </Text>
        </Pressable>
      </ScrollView>
    );
  }

  if (!film) {
    return (
      <View style={styles.centered}>
        <Text style={styles.error}>{error || "Film not found"}</Text>
        <Pressable onPress={onBack}>
          <Text style={styles.link}>Back</Text>
        </Pressable>
      </View>
    );
  }

  const qrSrc = `${API_URL}/v1/films/${code}/qr.png`;
  const waiting = exportState?.status === "pending" || exporting;
  const hiddenCount = photos.filter((photo) => photo.hidden).length;
  const pinReady = /^[\d\s-]{4,20}$/.test(pinDraft.trim());
  const isOwner = role === "host";
  // A photographer may look and take the originals, nothing else.
  const canWrite = role !== "photographer";

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Pressable onPress={onBack} hitSlop={12}>
        <Text style={styles.link}>← Films</Text>
      </Pressable>
      <Text style={styles.kicker}>
        {!hasHostKey || isOwner ? "Your film" : role === "cohost" ? "Co-host" : "Photographer"}
      </Text>
      <Text style={styles.title}>{film.title}</Text>
      <Text style={styles.meta}>
        {film.guest_count}/{film.guest_cap} guests · {film.shot_count} shots
        {hiddenCount ? ` · ${hiddenCount} hidden` : ""}
      </Text>
      <Text style={styles.meta}>
        {film.is_closed
          ? "Closed. "
          : `Open until ${new Date(film.closes_at).toLocaleString()}. `}
        {film.instant_reveal
          ? "Gallery is live."
          : film.is_developed
            ? "Gallery is open."
            : `Develops ${new Date(film.reveal_at).toLocaleString()}.`}
      </Text>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {hasHostKey && !isOwner ? (
        <Text style={styles.notice}>
          {role === "cohost"
            ? "You are a co-host on this film. You can moderate, develop, and change the room, but billing stays with whoever created it."
            : "You have photographer access: you can see every shot and download the originals, but you cannot change the film."}
        </Text>
      ) : null}

      <Pressable style={styles.primary} onPress={onTakePhotos} accessibilityRole="button">
        <Text style={styles.primaryLabel}>
          {film.is_closed ? "See the gallery" : "Take photos"}
        </Text>
      </Pressable>

      {hasHostKey ? (
        <View style={styles.tabs} accessibilityRole="tablist">
          {(
            [
              ["photos", photos.length ? `Photos (${photos.length})` : "Photos"],
              ["invite", "Invite"],
              ["settings", "Settings"],
            ] as const
          ).map(([key, label]) => (
            <Pressable
              key={key}
              onPress={() => setTab(key)}
              accessibilityRole="tab"
              accessibilityState={{ selected: tab === key }}
              style={[styles.tab, tab === key && styles.tabOn]}
            >
              <Text style={[styles.tabLabel, tab === key && styles.tabLabelOn]}>{label}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      {!hasHostKey || tab === "invite" ? (
        <View style={styles.card}>
          <Image source={{ uri: qrSrc }} style={styles.qr} />
          <Text style={styles.cardLabel}>Film code</Text>
          <Text style={styles.code}>{code}</Text>
          <Text style={styles.joinUrl}>{film.join_url}</Text>
          <Pressable style={styles.secondary} onPress={() => void shareInvite()}>
            <Text style={styles.secondaryLabel}>Share invite</Text>
          </Pressable>
        </View>
      ) : null}

      {hasHostKey && tab === "settings" ? (
        <View style={styles.tabBody}>
        {canWrite ? (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Gallery</Text>
          <Text style={styles.hint}>
            {film.shared_gallery
              ? "Everyone at the event sees every shot."
              : "Each guest only sees their own shots; your Photos tab and the ZIP still have the whole roll."}
          </Text>
          <Pressable
            onPress={() => void toggleSharedGallery()}
            disabled={savingVisibility}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: !film.shared_gallery, busy: savingVisibility }}
            style={styles.checkRow}
          >
            <View style={[styles.box, !film.shared_gallery && styles.boxOn]} />
            <Text style={styles.hint}>
              Keep each guest's photos private from the others. Unlike live
              reveal, this can be turned off later.
            </Text>
          </Pressable>
        </View>
        ) : null}

      <View style={styles.actions}>
        {!film.is_developed && canWrite ? (
          <Pressable
            style={[styles.secondary, (revealing || !hasHostKey) && styles.disabled]}
            disabled={revealing || !hasHostKey}
            onPress={() => void onReveal()}
          >
            <Text style={styles.secondaryLabel}>
              {revealing ? "Developing…" : "Develop now"}
            </Text>
          </Pressable>
        ) : null}
        {film.shared_gallery ? (
          <Pressable
            style={styles.secondary}
            onPress={() => void Linking.openURL(`${WEB_URL}/f/${code}/slideshow`)}
            accessibilityRole="button"
            accessibilityLabel="Open slideshow"
          >
            <Text style={styles.secondaryLabel}>Open slideshow</Text>
          </Pressable>
        ) : (
          <Text style={styles.hint}>
            The venue slideshow is off while the gallery is private. Turn sharing
            back on to put shots on a screen.
          </Text>
        )}
        <Pressable
          style={[styles.secondary, (waiting || !hasHostKey) && styles.disabled]}
          disabled={waiting || !hasHostKey}
          onPress={() => void onExport()}
        >
          <Text style={styles.secondaryLabel}>
            {waiting
              ? "Building ZIP…"
              : exportState?.status === "ready"
                ? "Share originals ZIP"
                : "Export originals"}
          </Text>
        </Pressable>
      </View>

        {canWrite ? (
        <>
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Join PIN</Text>
          <Text style={styles.hint}>
            {film.requires_pin
              ? "Guests need this PIN to pick up a camera. Anyone already shooting stays in."
              : "Anyone who photographs your QR card can join. A PIN stops that: read it out at the door instead of printing it."}
          </Text>
          <TextInput
            value={pinDraft}
            onChangeText={setPinDraft}
            placeholder={film.requires_pin ? "New PIN" : "4–8 digits"}
            placeholderTextColor="#71717a"
            keyboardType="number-pad"
            autoComplete="off"
            maxLength={20}
            accessibilityLabel={film.requires_pin ? "New join PIN" : "Join PIN"}
            style={[styles.input, styles.pinInput]}
          />
          <Pressable
            style={[styles.secondary, (!pinReady || savingPin) && styles.disabled]}
            disabled={!pinReady || savingPin}
            onPress={() => void savePin()}
            accessibilityRole="button"
            accessibilityState={{ disabled: !pinReady || savingPin, busy: savingPin }}
          >
            <Text style={styles.secondaryLabel}>
              {savingPin
                ? "Saving…"
                : film.requires_pin
                  ? "Change PIN"
                  : "Require a PIN"}
            </Text>
          </Pressable>
          {film.requires_pin ? (
            <Pressable
              style={[styles.secondary, savingPin && styles.disabled]}
              disabled={savingPin}
              onPress={() => void removePin()}
              accessibilityRole="button"
            >
              <Text style={styles.secondaryLabel}>Remove PIN</Text>
            </Pressable>
          ) : null}
          {pinNote ? <Text style={styles.meta}>{pinNote}</Text> : null}
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Room size</Text>
          <Text style={styles.hint}>
            Paid for {film.entitled_guest_cap} guests. Need more? Upgrade on the web.
          </Text>
          <View style={styles.row}>
            <View style={styles.field}>
              <Text style={styles.label}>Guest cap</Text>
              <TextInput
                value={guestCap}
                onChangeText={setGuestCap}
                keyboardType="number-pad"
                style={styles.input}
              />
            </View>
            <View style={styles.field}>
              <Text style={styles.label}>Shots per guest</Text>
              <TextInput
                value={shotLimit}
                onChangeText={setShotLimit}
                keyboardType="number-pad"
                style={styles.input}
              />
            </View>
          </View>
          <Pressable
            style={[styles.secondary, savingCaps && styles.disabled]}
            disabled={savingCaps}
            onPress={() => void onSaveCaps()}
          >
            <Text style={styles.secondaryLabel}>{savingCaps ? "Saving…" : "Save limits"}</Text>
          </Pressable>
          <Pressable style={styles.textButton} onPress={openWebHost}>
            <Text style={styles.link}>Upgrade capacity on web →</Text>
          </Pressable>
        </View>
        </>
        ) : null}

        {isOwner ? (
        <>
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Recovery email</Text>
          <Text style={styles.hint}>Get host tools back if this phone is cleared.</Text>
          <TextInput
            value={hostEmail}
            onChangeText={setHostEmail}
            placeholder="you@example.com"
            placeholderTextColor="#71717a"
            keyboardType="email-address"
            autoCapitalize="none"
            style={styles.input}
          />
          <Pressable
            style={[styles.secondary, savingEmail && styles.disabled]}
            disabled={savingEmail}
            onPress={() => void onSaveEmail()}
          >
            <Text style={styles.secondaryLabel}>{savingEmail ? "Saving…" : "Save email"}</Text>
          </Pressable>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>People</Text>
          <Text style={styles.hint}>
            A co-host can moderate, develop, and resize the room. A photographer
            can see every shot and download the originals, and nothing else.
            Neither can see your recovery email or invite anyone themselves.
          </Text>

          {seats.map((seat) => (
            <View key={seat.id} style={styles.seatRow}>
              <View style={styles.seatText}>
                <Text style={styles.seatName}>{seat.label}</Text>
                <Text style={styles.hint}>
                  {seat.role === "cohost" ? "Co-host" : "Photographer"}
                  {seat.claimed_at ? "" : " · invite not opened yet"}
                </Text>
              </View>
              <Pressable
                style={styles.smallButton}
                onPress={() => void removeSeat(seat)}
                accessibilityRole="button"
                accessibilityLabel={`Remove ${seat.label}`}
              >
                <Text style={styles.smallButtonLabel}>Remove</Text>
              </Pressable>
            </View>
          ))}

          <View style={styles.tabs} accessibilityRole="radiogroup">
            {(
              [
                ["cohost", "Co-host"],
                ["photographer", "Photographer"],
              ] as const
            ).map(([key, label]) => (
              <Pressable
                key={key}
                onPress={() => setSeatRole(key)}
                accessibilityRole="radio"
                accessibilityState={{ checked: seatRole === key }}
                style={[styles.tab, seatRole === key && styles.tabOn]}
              >
                <Text style={[styles.tabLabel, seatRole === key && styles.tabLabelOn]}>
                  {label}
                </Text>
              </Pressable>
            ))}
          </View>
          <TextInput
            value={seatLabel}
            onChangeText={setSeatLabel}
            placeholder="Their name"
            placeholderTextColor="#71717a"
            maxLength={80}
            accessibilityLabel="Their name"
            style={styles.input}
          />
          <Pressable
            style={[styles.secondary, (!seatLabel.trim() || invitingSeat) && styles.disabled]}
            disabled={!seatLabel.trim() || invitingSeat}
            onPress={() => void inviteSeat()}
            accessibilityRole="button"
          >
            <Text style={styles.secondaryLabel}>
              {invitingSeat ? "Creating…" : "Create invite"}
            </Text>
          </Pressable>

          {newSeat ? (
            <View style={styles.inviteBox}>
              <Text style={styles.hint}>
                Send this link to {newSeat.seat.label}. It works once opened and
                expires in a week — this is the only time it is shown.
              </Text>
              <Text style={styles.joinUrl} selectable>
                {newSeat.invite_url}
              </Text>
              <Pressable style={styles.primary} onPress={() => void shareSeatInvite()}>
                <Text style={styles.primaryLabel}>Send invite</Text>
              </Pressable>
            </View>
          ) : null}
        </View>

        <View style={[styles.section, styles.danger]}>
          <Text style={styles.sectionTitle}>Delete this film</Text>
          <Text style={styles.hint}>
            The film disappears for your guests straight away. The photos are kept
            for {GRACE_DAYS} days in case this was a mistake, then destroyed for
            good. For most events these are the only copies that exist.
          </Text>
          <Text style={styles.label}>Type {code} to confirm.</Text>
          <TextInput
            value={deleteConfirm}
            onChangeText={setDeleteConfirm}
            autoCapitalize="characters"
            autoCorrect={false}
            autoComplete="off"
            accessibilityLabel={`Type ${code} to confirm deleting this film`}
            style={[styles.input, styles.pinInput]}
          />
          <Pressable
            style={[
              styles.dangerButton,
              (deleteConfirm.trim().toUpperCase() !== code.toUpperCase() || deleting) &&
                styles.disabled,
            ]}
            disabled={deleteConfirm.trim().toUpperCase() !== code.toUpperCase() || deleting}
            onPress={() => void onDelete()}
            accessibilityRole="button"
          >
            <Text style={styles.dangerLabel}>{deleting ? "Deleting…" : "Delete film"}</Text>
          </Pressable>
        </View>
        </>
        ) : null}
        </View>
      ) : null}

      {!hasHostKey ? (
        <View style={styles.section}>
          <Text style={styles.hint}>
            Host tools need the key from the device that created this film. If you
            saved an email, we can send a new link.
          </Text>
          <TextInput
            value={recoverEmail}
            onChangeText={setRecoverEmail}
            placeholder="Host email"
            placeholderTextColor="#71717a"
            keyboardType="email-address"
            autoCapitalize="none"
            style={styles.input}
          />
          <Pressable
            style={[styles.secondary, recoverBusy && styles.disabled]}
            disabled={recoverBusy}
            onPress={() => void onRecover()}
          >
            <Text style={styles.secondaryLabel}>
              {recoverBusy ? "Sending…" : "Email me a host link"}
            </Text>
          </Pressable>
          {recoverSent ? (
            <Text style={styles.hint}>If that email is on this film, a link is on its way.</Text>
          ) : null}
          <Pressable style={styles.textButton} onPress={openWebHost}>
            <Text style={styles.link}>Open web host page →</Text>
          </Pressable>
        </View>
      ) : null}

      {hasHostKey && tab === "photos" ? (
        <View style={styles.section}>
          <Text style={styles.hint}>
            Hide a shot here and it will never appear in the gallery.
          </Text>
          {photos.length === 0 ? (
            <Text style={styles.meta}>No shots yet. This list refreshes on its own.</Text>
          ) : (
            photos.map((photo) => (
              <View key={photo.shot_id} style={styles.shot}>
                {photo.kind === "clip" ? (
                  <ClipTile
                    url={photo.url}
                    posterUrl={photo.poster_url}
                    guestName={photo.guest_name}
                    durationMs={photo.duration_ms}
                    style={[styles.shotImage, photo.hidden && styles.hiddenShot]}
                  />
                ) : (
                  <Image
                    source={{ uri: photo.url }}
                    style={[styles.shotImage, photo.hidden && styles.hiddenShot]}
                  />
                )}
                <View style={styles.shotBar}>
                  <Text style={styles.shotName}>{photo.guest_name}</Text>
                  {canWrite ? (
                    <Pressable
                      style={styles.hideButton}
                      onPress={() => void toggleHidden(photo)}
                    >
                      <Text style={styles.hideLabel}>{photo.hidden ? "Unhide" : "Hide"}</Text>
                    </Pressable>
                  ) : null}
                </View>
              </View>
            ))
          )}
        </View>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: 24, gap: 16, paddingBottom: 48 },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12 },
  kicker: {
    color: "#71717a",
    letterSpacing: 4,
    fontSize: 11,
    textTransform: "uppercase",
  },
  title: { color: "#fff", fontSize: 32, fontFamily: "Georgia" },
  meta: { color: "#a1a1aa", fontSize: 14 },
  link: { color: "#a1a1aa", fontSize: 14 },
  card: {
    borderWidth: 1,
    borderColor: "#27272a",
    borderRadius: 16,
    padding: 20,
    gap: 12,
    alignItems: "center",
  },
  cardLabel: {
    color: "#71717a",
    fontSize: 11,
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  code: {
    color: "#fff",
    fontSize: 36,
    letterSpacing: 8,
    fontFamily: "Courier",
  },
  qr: { width: 240, height: 240, backgroundColor: "#fff", borderRadius: 8 },
  joinUrl: { color: "#a1a1aa", fontSize: 13, textAlign: "center" },
  hint: { color: "#71717a", fontSize: 12, lineHeight: 18 },
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
  actions: { gap: 10 },
  tabs: {
    flexDirection: "row",
    borderWidth: 1,
    borderColor: "#27272a",
    borderRadius: 999,
    padding: 4,
    marginTop: 8,
  },
  tab: { flex: 1, alignItems: "center", paddingVertical: 8, borderRadius: 999 },
  tabOn: { backgroundColor: "#27272a" },
  tabLabel: { color: "#a1a1aa", fontSize: 13, fontWeight: "600" },
  tabLabelOn: { color: "#fff" },
  tabBody: { gap: 16 },
  section: { gap: 12, marginTop: 8 },
  sectionTitle: { color: "#fff", fontSize: 24, fontFamily: "Georgia" },
  row: { flexDirection: "row", gap: 12 },
  field: { flex: 1, gap: 6 },
  label: { color: "#a1a1aa", fontSize: 13 },
  input: {
    borderWidth: 1,
    borderColor: "#27272a",
    borderRadius: 10,
    color: "#fff",
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  pinInput: { letterSpacing: 6 },
  primary: {
    backgroundColor: "#fff",
    borderRadius: 999,
    paddingVertical: 12,
    paddingHorizontal: 24,
    alignItems: "center",
  },
  primaryLabel: { color: "#000", fontWeight: "600" },
  secondary: {
    borderWidth: 1,
    borderColor: "#52525b",
    borderRadius: 999,
    paddingVertical: 12,
    paddingHorizontal: 24,
    alignItems: "center",
  },
  secondaryLabel: { color: "#fff", fontWeight: "600" },
  textButton: { alignSelf: "flex-start" },
  disabled: { opacity: 0.4 },
  danger: {
    borderWidth: 1,
    borderColor: "rgba(127, 29, 29, 0.6)",
    borderRadius: 16,
    padding: 16,
  },
  dangerButton: {
    borderWidth: 1,
    borderColor: "#991b1b",
    borderRadius: 999,
    paddingVertical: 12,
    paddingHorizontal: 24,
    alignItems: "center",
  },
  dangerLabel: { color: "#fca5a5", fontWeight: "600" },
  notice: {
    borderWidth: 1,
    borderColor: "#3f3f46",
    backgroundColor: "#18181b",
    borderRadius: 12,
    padding: 12,
    color: "#d4d4d8",
    fontSize: 13,
    lineHeight: 19,
  },
  seatRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderWidth: 1,
    borderColor: "#27272a",
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  seatText: { flex: 1, gap: 2 },
  seatName: { color: "#fff", fontSize: 14 },
  smallButton: {
    borderWidth: 1,
    borderColor: "#3f3f46",
    borderRadius: 999,
    paddingHorizontal: 16,
    minHeight: 44,
    justifyContent: "center",
  },
  smallButtonLabel: { color: "#d4d4d8", fontSize: 12 },
  inviteBox: {
    borderWidth: 1,
    borderColor: "#3f3f46",
    backgroundColor: "#18181b",
    borderRadius: 12,
    padding: 12,
    gap: 10,
  },
  error: { color: "#f87171", fontSize: 14 },
  shot: { gap: 4 },
  shotImage: { width: "100%", aspectRatio: 3 / 4, borderRadius: 12, backgroundColor: "#18181b" },
  hiddenShot: { opacity: 0.3 },
  shotBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.6)",
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
    marginTop: -36,
  },
  shotName: { color: "#fff", fontSize: 12 },
  hideButton: {
    backgroundColor: "rgba(255,255,255,0.2)",
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  hideLabel: { color: "#fff", fontSize: 12 },
});
