"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { ClipTile } from "@/components/guest/ClipTile";
import {
  API_URL,
  ApiError,
  cardsPdfUrl,
  claimSeat,
  clearDeleted,
  clearJoinPin,
  consumeMagicSession,
  createSeat,
  deleteFilm,
  getCatalog,
  getExport,
  getFilm,
  getHostAccount,
  getPayments,
  getReview,
  hideShot,
  listSeats,
  loadDeleted,
  loadHostToken,
  loadStaffRole,
  recoverHost,
  restoreFilm,
  revealFilm,
  revokeSeat,
  saveDeleted,
  saveHostToken,
  saveStaffRole,
  setJoinPin,
  startCheckout,
  startExport,
  unhideShot,
  updateFilm,
} from "@/lib/api";
import type {
  CatalogResponse,
  ExportResponse,
  FilmDeleted,
  FilmPublic,
  PaymentsResponse,
  ReviewPhoto,
  SeatCreated,
  SeatPublic,
  StaffRole,
} from "@/lib/types";

const neverChanges = () => () => {};
const readOrigin = () => window.location.origin;
const originOnServer = () => "";

function usd(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

/** Receipts need the cents that catalog prices never have, and tax creates. */
function money(cents: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(cents / 100);
}

function goTo(url: string): void {
  window.location.assign(url);
}

function paidForCap(catalog: CatalogResponse, cap: number): number {
  let paid = 0;
  for (const tier of catalog.tiers) {
    if (tier.guest_cap <= cap) paid = tier.amount_cents;
  }
  return paid;
}

// Mirrors DELETED_FILM_GRACE_DAYS on the API. Used only as copy before the film
// is deleted; afterwards the real deadline comes back on the response.
const GRACE_DAYS = 30;

export function HostDashboard({ code }: { code: string }) {
  const [film, setFilm] = useState<FilmPublic | null>(null);
  const [photos, setPhotos] = useState<ReviewPhoto[]>([]);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [codeCopied, setCodeCopied] = useState(false);
  const [revealing, setRevealing] = useState(false);
  const [exportState, setExportState] = useState<ExportResponse | null>(null);
  const [guestCap, setGuestCap] = useState(25);
  const [shotLimit, setShotLimit] = useState(8);
  const [hasHostKey, setHasHostKey] = useState(false);
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null);
  const [checkingOut, setCheckingOut] = useState<string | null>(null);
  const [hostEmail, setHostEmail] = useState("");
  const [recoverEmail, setRecoverEmail] = useState("");
  const [recoverBusy, setRecoverBusy] = useState(false);
  const [recoverSent, setRecoverSent] = useState(false);
  const [receipts, setReceipts] = useState<PaymentsResponse | null>(null);
  const [checkoutResult, setCheckoutResult] = useState<"success" | "cancel" | null>(null);
  const [role, setRole] = useState<StaffRole>("host");
  const [seats, setSeats] = useState<SeatPublic[]>([]);
  const [seatRole, setSeatRole] = useState<"cohost" | "photographer">("cohost");
  const [seatLabel, setSeatLabel] = useState("");
  const [newSeat, setNewSeat] = useState<SeatCreated | null>(null);
  const [inviteCopied, setInviteCopied] = useState(false);
  const [pinDraft, setPinDraft] = useState("");
  const [pinNote, setPinNote] = useState("");
  const [deleted, setDeleted] = useState<FilmDeleted | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [savingVisibility, setSavingVisibility] = useState(false);

  const origin = useSyncExternalStore(neverChanges, readOrigin, originOnServer);
  const joinUrl = film?.join_url || (origin ? `${origin}/f/${code}` : "");
  const qrSrc = `${API_URL}/v1/films/${code}/qr.svg`;

  const refresh = useCallback(async () => {
    try {
      const loaded = await getFilm(code);
      setFilm(loaded);
      setGuestCap(loaded.guest_cap);
      setShotLimit(loaded.shot_limit);
      setDeleted(null);
    } catch (err) {
      // A deleted film is a 404 to everyone, including the host who deleted it.
      // The restore deadline was stashed at delete time so this device can still
      // offer a way back during the grace period.
      const stashed = err instanceof ApiError && err.status === 404 && loadDeleted(code);
      if (stashed) setDeleted(stashed);
      else setError("Film not found");
      return;
    }
    const token = loadHostToken(code);
    setHasHostKey(Boolean(token));
    if (!token) return;
    const seat = loadStaffRole(code);
    setRole(seat);
    try {
      const review = await getReview(code, token);
      setPhotos(review.photos);
      const exp = await getExport(code, token);
      setExportState(exp);
      // Receipts, the recovery email, and the guest list of who else has access
      // are the owner's alone, so a co-host must not even request them.
      if (seat === "host") {
        const account = await getHostAccount(code, token);
        setHostEmail(account.email ?? "");
        setReceipts(await getPayments(code, token));
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
  }, [code]);

  useEffect(() => {
    const id = window.setInterval(() => {
      void refresh();
    }, 8000);
    const first = window.setTimeout(() => {
      void refresh();
    }, 0);
    const catalogLoad = window.setTimeout(() => {
      void getCatalog().then(setCatalog).catch(() => {
        // Catalog is public; a failure here should not block host tools.
      });
    }, 0);
    const magicLoad = window.setTimeout(() => {
      const magic = new URLSearchParams(window.location.search).get("magic");
      if (!magic) return;
      void consumeMagicSession(code, magic)
        .then((created) => {
          saveHostToken(code, created.host_token);
          // A magic link always restores the owner, even on a device that had
          // only ever held a seat before.
          saveStaffRole(code, "host");
          setRole("host");
          window.history.replaceState({}, "", window.location.pathname);
          setHasHostKey(true);
          void refresh();
        })
        .catch(() => {
          setError("That recovery link is invalid or expired.");
        });
    }, 0);
    const seatLoad = window.setTimeout(() => {
      const invite = new URLSearchParams(window.location.search).get("seat");
      if (!invite) return;
      void claimSeat(code, invite)
        .then((claimed) => {
          saveHostToken(code, claimed.token);
          saveStaffRole(code, claimed.role);
          setRole(claimed.role);
          setHasHostKey(true);
          window.history.replaceState({}, "", window.location.pathname);
          void refresh();
        })
        .catch(() => {
          setError("That invite is invalid, expired, or has been revoked.");
        });
    }, 0);
    const checkoutLoad = window.setTimeout(() => {
      const params = new URLSearchParams(window.location.search);
      const outcome = params.get("checkout");
      if (!outcome) return;
      // Stripe sends the host back here; without this the page looked identical
      // whether the card went through or they hit cancel.
      setCheckoutResult(outcome === "success" ? "success" : "cancel");
      params.delete("checkout");
      const qs = params.toString();
      window.history.replaceState(
        {},
        "",
        qs ? `${window.location.pathname}?${qs}` : window.location.pathname,
      );
    }, 0);
    return () => {
      window.clearInterval(id);
      window.clearTimeout(first);
      window.clearTimeout(catalogLoad);
      window.clearTimeout(magicLoad);
      window.clearTimeout(seatLoad);
      window.clearTimeout(checkoutLoad);
    };
  }, [refresh, code]);

  async function reveal() {
    const token = loadHostToken(code);
    if (!token) {
      setError("Host key missing. Open this from the device that created the film.");
      return;
    }
    setError("");
    setRevealing(true);
    try {
      setFilm(await revealFilm(code, token));
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
    const token = loadHostToken(code);
    if (!token) return;
    setPhotos((current) =>
      current.map((item) =>
        item.shot_id === photo.shot_id ? { ...item, hidden: !item.hidden } : item,
      ),
    );
    try {
      if (photo.hidden) await unhideShot(code, photo.shot_id, token);
      else await hideShot(code, photo.shot_id, token);
    } catch {
      setPhotos((current) =>
        current.map((item) =>
          item.shot_id === photo.shot_id ? { ...item, hidden: photo.hidden } : item,
        ),
      );
      setError("Could not update that photo.");
    }
  }

  async function saveVisibility(shared: boolean) {
    const token = loadHostToken(code);
    if (!token) return;
    setSavingVisibility(true);
    try {
      setFilm(await updateFilm(code, token, { shared_gallery: shared }));
      setError("");
    } catch {
      setError("Could not update the film.");
    } finally {
      setSavingVisibility(false);
    }
  }

  async function saveCaps() {
    const token = loadHostToken(code);
    if (!token) return;
    try {
      setFilm(await updateFilm(code, token, { guest_cap: guestCap, shot_limit: shotLimit }));
      setError("");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "That cap is below people who already joined."
          : err instanceof ApiError && err.status === 402
            ? "Pay for a larger room to raise the guest cap."
            : "Could not update the film.",
      );
    }
  }

  async function requestZip() {
    const token = loadHostToken(code);
    if (!token) return;
    try {
      setExportState(await startExport(code, token));
      for (let attempt = 0; attempt < 20; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        const next = await getExport(code, token);
        setExportState(next);
        if (next.status === "ready" && next.download_url) {
          goTo(next.download_url);
          return;
        }
        if (next.status === "failed") {
          setError("The ZIP could not be built.");
          return;
        }
      }
    } catch {
      setError("Could not start the download.");
    }
  }

  async function pay(body: { tier_id?: string; addon_id?: string }) {
    const token = loadHostToken(code);
    if (!token) return;
    const key = body.tier_id ?? body.addon_id ?? "pay";
    setCheckingOut(key);
    setError("");
    try {
      const session = await startCheckout(code, token, body);
      goTo(session.url);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "That is already included."
          : "Could not start checkout.",
      );
      setCheckingOut(null);
    }
  }

  async function savePin() {
    const token = loadHostToken(code);
    if (!token) return;
    try {
      setFilm(await setJoinPin(code, token, pinDraft.trim()));
      setPinDraft("");
      setPinNote("Guests now need this PIN to join.");
      setError("");
    } catch {
      setError("A PIN must be 4 to 8 digits.");
    }
  }

  async function removePin() {
    const token = loadHostToken(code);
    if (!token) return;
    try {
      setFilm(await clearJoinPin(code, token));
      setPinNote("Anyone with the code can join again.");
      setError("");
    } catch {
      setError("Could not remove the PIN.");
    }
  }

  async function removeFilm() {
    const token = loadHostToken(code);
    if (!token) return;
    setDeleting(true);
    try {
      const result = await deleteFilm(code, token);
      saveDeleted(code, result);
      setDeleted(result);
      setFilm(null);
      setDeleteConfirm("");
      setError("");
    } catch {
      setError("Could not delete this film.");
    } finally {
      setDeleting(false);
    }
  }

  async function undoDelete() {
    const token = loadHostToken(code);
    if (!token) return;
    try {
      const restored = await restoreFilm(code, token);
      clearDeleted(code);
      setDeleted(null);
      setFilm(restored);
      setError("");
      void refresh();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 410
          ? "The grace period has passed and these photos are gone."
          : "Could not restore this film.",
      );
    }
  }

  async function inviteSeat() {
    const token = loadHostToken(code);
    if (!token || !seatLabel.trim()) return;
    try {
      const created = await createSeat(code, token, {
        role: seatRole,
        label: seatLabel.trim(),
      });
      setNewSeat(created);
      setSeatLabel("");
      setSeats((current) => [...current, created.seat]);
      setError("");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "This film already has as many people as it can hold."
          : "Could not create that invite.",
      );
    }
  }

  async function removeSeat(seat: SeatPublic) {
    const token = loadHostToken(code);
    if (!token) return;
    setSeats((current) => current.filter((row) => row.id !== seat.id));
    if (newSeat?.seat.id === seat.id) setNewSeat(null);
    try {
      await revokeSeat(code, seat.id, token);
    } catch {
      setSeats((current) => [...current, seat]);
      setError("Could not remove that person.");
    }
  }

  async function copyInvite() {
    if (!newSeat) return;
    await navigator.clipboard.writeText(newSeat.invite_url);
    setInviteCopied(true);
    setTimeout(() => setInviteCopied(false), 1500);
  }

  async function saveEmail() {
    const token = loadHostToken(code);
    if (!token) return;
    try {
      await updateFilm(code, token, { host_email: hostEmail.trim() });
      setError("");
    } catch {
      setError("Could not save that email.");
    }
  }

  async function sendRecovery() {
    if (!recoverEmail.trim()) return;
    setRecoverBusy(true);
    setError("");
    try {
      await recoverHost(code, recoverEmail.trim());
      setRecoverSent(true);
    } catch {
      setError("Could not send a recovery email.");
    } finally {
      setRecoverBusy(false);
    }
  }

  async function copy() {
    if (!joinUrl) return;
    await navigator.clipboard.writeText(joinUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  async function copyCode() {
    await navigator.clipboard.writeText(code);
    setCodeCopied(true);
    setTimeout(() => setCodeCopied(false), 1500);
  }

  if (error && !film) return <p className="text-red-400">{error}</p>;
  if (deleted) {
    const purgeAt = new Date(deleted.purge_at);
    return (
      <div className="mx-auto flex w-full max-w-xl flex-col gap-4">
        <h1 className="font-serif text-4xl text-white">Film deleted</h1>
        <p className="text-sm text-zinc-400">
          <span className="font-mono">{code}</span> is gone for your guests and
          anyone you gave access to. The photos themselves are kept until{" "}
          {purgeAt.toLocaleDateString(undefined, {
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
          , and are permanently destroyed after that.
        </p>
        <p className="text-sm text-zinc-500">
          Restoring only works from this browser, so keep this page if you are
          not sure.
        </p>
        {error ? (
          <p className="text-sm text-red-400" role="alert">
            {error}
          </p>
        ) : null}
        <button
          type="button"
          onClick={() => void undoDelete()}
          className="self-start rounded-full bg-white px-5 py-2 text-sm font-medium text-black"
        >
          Restore this film
        </button>
      </div>
    );
  }

  if (!film) return <p className="text-zinc-400">Loading host tools…</p>;

  const hiddenCount = photos.filter((photo) => photo.hidden).length;
  // Reported but still visible: the only thing in the inbox actually waiting on
  // a decision, so it is counted separately and floated to the top.
  const reportedCount = photos.filter(
    (photo) => photo.report_count > 0 && !photo.hidden,
  ).length;
  const inboxPhotos = [...photos].sort((a, b) => {
    const needsAttention = (photo: ReviewPhoto) =>
      photo.report_count > 0 && !photo.hidden ? 0 : 1;
    return needsAttention(a) - needsAttention(b);
  });
  const waiting = exportState?.status === "pending";
  const isOwner = role === "host";
  // A photographer may look and take the originals, nothing else.
  const canWrite = role !== "photographer";

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
      <header className="flex flex-col gap-2">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Host</p>
        <h1 className="font-serif text-4xl text-white">{film.title}</h1>
        <p className="text-sm text-zinc-400">
          {film.guest_count}/{film.guest_cap} guests · {film.shot_count} shots ·{" "}
          {film.unlimited_shots ? "unlimited shots" : `${film.shot_limit} per camera`}
          {hiddenCount ? ` · ${hiddenCount} hidden` : ""}
          {film.keep_forever ? " · kept forever" : ""}
          {film.video_pack ? ` · ${film.clips_per_guest} clips each` : ""}
        </p>
      </header>

      {hasHostKey && !isOwner ? (
        <p className="rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-3 text-sm text-zinc-300">
          {role === "cohost"
            ? "You are a co-host on this film. You can moderate, develop, and change the room, but billing stays with whoever created it."
            : "You have photographer access: you can see every shot and download the originals, but you cannot change the film."}
        </p>
      ) : null}

      {checkoutResult ? (
        <p
          role="status"
          className={
            checkoutResult === "success"
              ? "rounded-xl border border-emerald-800 bg-emerald-950/50 px-4 py-3 text-sm text-emerald-300"
              : "rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-3 text-sm text-zinc-300"
          }
        >
          {checkoutResult === "success"
            ? "Payment received. Your receipt is below and a copy is on its way by email."
            : "Checkout cancelled. Nothing was charged."}
        </p>
      ) : null}

      <section className="flex flex-col items-center gap-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-6">
        <div className="flex flex-col items-center gap-2">
          <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Film code</p>
          <p className="font-mono text-3xl tracking-[0.3em] text-white">{code}</p>
          <button
            type="button"
            onClick={copyCode}
            className="rounded-full border border-zinc-600 px-4 py-1.5 text-xs text-zinc-300"
          >
            {codeCopied ? "Copied" : "Copy code"}
          </button>
          <p className="max-w-sm text-center text-xs text-zinc-500">
            Type this in the iOS app, or scan the QR to use the browser camera.
          </p>
        </div>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={qrSrc}
          alt="Join QR code"
          width={240}
          height={240}
          className="rounded-lg bg-white p-2"
        />
        <p className="break-all text-center text-sm text-zinc-400">{joinUrl}</p>
        <div className="flex flex-wrap justify-center gap-3">
          <button
            type="button"
            onClick={copy}
            className="rounded-full bg-white px-5 py-2 text-sm font-medium text-black"
          >
            {copied ? "Copied" : "Copy join link"}
          </button>
          <a
            href={cardsPdfUrl(code)}
            className="rounded-full border border-zinc-600 px-5 py-2 text-sm"
          >
            Download table cards (PDF)
          </a>
          <a href={`/f/${code}/print`} className="rounded-full px-5 py-2 text-sm text-zinc-400">
            Print from browser
          </a>
        </div>
      </section>

      <section className="flex flex-col gap-3 text-sm text-zinc-300">
        <p>Closes {new Date(film.closes_at).toLocaleString()}</p>
        <p>
          {film.instant_reveal
            ? "Gallery is live. Shots appear as guests take them."
            : film.is_developed
              ? "Gallery is open."
              : `Develops ${new Date(film.reveal_at).toLocaleString()}`}
          {film.shared_gallery
            ? " Everyone at the event sees every shot."
            : " Each guest only sees their own shots; this inbox and the ZIP still have the whole roll."}
        </p>
        {error ? <p className="text-red-400">{error}</p> : null}
        <div className="flex flex-wrap gap-3">
          {!film.is_developed ? (
            canWrite ? (
              <button
                type="button"
                onClick={reveal}
                disabled={revealing}
                className="rounded-full border border-zinc-600 px-5 py-2 text-sm disabled:opacity-40"
              >
                {revealing ? "Developing…" : "Develop now"}
              </button>
            ) : null
          ) : (
            <a
              href={`/f/${code}/gallery`}
              className="rounded-full bg-white px-5 py-2 text-sm font-medium text-black"
            >
              Open gallery
            </a>
          )}
          <button
            type="button"
            onClick={requestZip}
            disabled={waiting || !hasHostKey}
            className="rounded-full border border-zinc-600 px-5 py-2 text-sm disabled:opacity-40"
          >
            {waiting
              ? "Building ZIP…"
              : exportState?.status === "ready"
                ? "Download originals ZIP"
                : "Export originals"}
          </button>
          <a href={`/f/${code}`} className="rounded-full px-5 py-2 text-sm text-zinc-400">
            Open guest camera
          </a>
          {film.shared_gallery ? (
            <a
              href={`/f/${code}/slideshow`}
              target="_blank"
              rel="noopener"
              className="rounded-full px-5 py-2 text-sm text-zinc-400"
            >
              Open slideshow
            </a>
          ) : null}
        </div>
        {!film.shared_gallery ? (
          <p className="text-xs text-zinc-500">
            The guest gallery only shows each person their own shots. Use this
            inbox for the whole roll. The venue slideshow is off for the same
            reason; make the gallery shared to put shots on a screen.
          </p>
        ) : null}
      </section>

      {hasHostKey && isOwner ? (
        <section className="flex flex-col gap-3 rounded-2xl border border-zinc-800 p-4">
          <p className="text-sm text-zinc-400">
            Room size. Paid for {film.entitled_guest_cap} guests
            {film.keep_forever
              ? "; photos stay forever."
              : `; originals stay until ${new Date(film.storage_until).toLocaleDateString()}. The ZIP is always free.`}
          </p>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1 text-sm">
              Guest cap
              <input
                type="number"
                min={film.guest_count}
                max={film.entitled_guest_cap}
                value={guestCap}
                onChange={(e) => setGuestCap(Number(e.target.value))}
                className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Shots per guest
              <input
                type="number"
                min={1}
                max={500}
                value={shotLimit}
                onChange={(e) => setShotLimit(Number(e.target.value))}
                className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
              />
            </label>
          </div>
          <button
            type="button"
            onClick={saveCaps}
            className="self-start rounded-full border border-zinc-600 px-5 py-2 text-sm"
          >
            Save
          </button>
          {catalog ? (
            <div className="flex flex-col gap-2 pt-2">
              <p className="text-sm text-zinc-400">Need a larger room?</p>
              <div className="flex flex-wrap gap-2">
                {catalog.tiers
                  .filter((tier) => tier.guest_cap > film.entitled_guest_cap)
                  .map((tier) => {
                    const charge = tier.amount_cents - paidForCap(catalog, film.entitled_guest_cap);
                    return (
                      <button
                        key={tier.id}
                        type="button"
                        disabled={checkingOut !== null}
                        onClick={() => void pay({ tier_id: tier.id })}
                        className="rounded-full border border-zinc-600 px-4 py-2 text-sm disabled:opacity-40"
                      >
                        {checkingOut === tier.id
                          ? "Redirecting…"
                          : `${tier.label} · ${usd(charge)}`}
                      </button>
                    );
                  })}
              </div>
              {!film.keep_forever || !film.unlimited_shots || !film.video_pack
                ? catalog.addons
                    .filter((addon) => {
                      if (addon.id === "keep_forever") return !film.keep_forever;
                      if (addon.id === "unlimited_shots") return !film.unlimited_shots;
                      if (addon.id === "video_pack") return !film.video_pack;
                      return true;
                    })
                    .map((addon) => (
                    <button
                      key={addon.id}
                      type="button"
                      disabled={checkingOut !== null}
                      onClick={() => void pay({ addon_id: addon.id })}
                      className="self-start rounded-full px-4 py-2 text-sm text-zinc-400 disabled:opacity-40"
                    >
                      {checkingOut === addon.id
                        ? "Redirecting…"
                        : `${addon.label} · ${usd(addon.amount_cents)}`}
                    </button>
                  ))
                : null}
            </div>
          ) : null}
          <div className="flex flex-col gap-2 pt-2">
            <p className="text-sm text-zinc-400">
              Recovery email. If this phone is lost, we send a host link here.
            </p>
            <div className="flex flex-wrap gap-2">
              <input
                type="email"
                value={hostEmail}
                onChange={(e) => setHostEmail(e.target.value)}
                placeholder="you@example.com"
                className="min-w-48 flex-1 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
              />
              <button
                type="button"
                onClick={() => void saveEmail()}
                className="rounded-full border border-zinc-600 px-4 py-2 text-sm"
              >
                Save email
              </button>
            </div>
          </div>
        </section>
      ) : hasHostKey ? null : (
        <section className="flex flex-col gap-3 rounded-2xl border border-zinc-800 p-4">
          <p className="text-sm text-zinc-500">
            Moderation and export need the host key from the device that created
            this film. If you saved an email, we can send a new link.
          </p>
          <div className="flex flex-wrap gap-2">
            <input
              type="email"
              value={recoverEmail}
              onChange={(e) => setRecoverEmail(e.target.value)}
              placeholder="Host email"
              className="min-w-48 flex-1 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
            />
            <button
              type="button"
              onClick={() => void sendRecovery()}
              disabled={recoverBusy}
              className="rounded-full border border-zinc-600 px-4 py-2 text-sm disabled:opacity-40"
            >
              {recoverBusy ? "Sending…" : "Email me a host link"}
            </button>
          </div>
          {recoverSent ? (
            <p className="text-sm text-zinc-400">
              If that email is on this film, a link is on its way.
            </p>
          ) : null}
        </section>
      )}

      {hasHostKey && canWrite ? (
        <section className="flex flex-col gap-3 rounded-2xl border border-zinc-800 p-4">
          <h2 className="font-serif text-2xl text-white">Guest gallery</h2>
          <p className="text-sm text-zinc-400">
            {film.shared_gallery
              ? "The default: one album everyone at the event can see after develop."
              : "Private: each guest only sees their own shots. You still have every photo here and in the ZIP."}
          </p>
          <label className="flex items-start gap-3 text-sm text-zinc-300">
            <input
              type="checkbox"
              checked={!film.shared_gallery}
              disabled={savingVisibility}
              onChange={(e) => void saveVisibility(!e.target.checked)}
              className="mt-1 h-4 w-4 accent-white"
            />
            <span>
              Keep each guest&apos;s photos private from the others. Unlike live
              reveal, this can be turned off later.
            </span>
          </label>
        </section>
      ) : null}

      {hasHostKey && canWrite ? (
        <section className="flex flex-col gap-3 rounded-2xl border border-zinc-800 p-4">
          <h2 className="font-serif text-2xl text-white">Join PIN</h2>
          <p className="text-sm text-zinc-400">
            {film.requires_pin
              ? "Guests need this PIN to pick up a camera. Anyone already shooting stays in."
              : "Anyone who photographs your QR card can join. A PIN stops that: read it out at the door instead of printing it."}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={pinDraft}
              onChange={(e) => setPinDraft(e.target.value)}
              placeholder={film.requires_pin ? "New PIN" : "4–8 digits"}
              inputMode="numeric"
              autoComplete="off"
              maxLength={20}
              aria-label={film.requires_pin ? "New join PIN" : "Join PIN"}
              className="w-36 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm tracking-[0.2em]"
            />
            <button
              type="button"
              onClick={() => void savePin()}
              disabled={!/^[\d\s-]{4,20}$/.test(pinDraft.trim())}
              className="rounded-full border border-zinc-600 px-4 py-2 text-sm disabled:opacity-40"
            >
              {film.requires_pin ? "Change PIN" : "Require a PIN"}
            </button>
            {film.requires_pin ? (
              <button
                type="button"
                onClick={() => void removePin()}
                className="rounded-full border border-zinc-700 px-4 py-2 text-sm text-zinc-300"
              >
                Remove PIN
              </button>
            ) : null}
          </div>
          {pinNote ? <p className="text-sm text-zinc-300">{pinNote}</p> : null}
        </section>
      ) : null}

      {hasHostKey && isOwner ? (
        <section className="flex flex-col gap-3 rounded-2xl border border-zinc-800 p-4">
          <h2 className="font-serif text-2xl text-white">People</h2>
          <p className="text-sm text-zinc-400">
            A co-host can moderate, develop, and resize the room. A photographer
            can see every shot and download the originals, and nothing else.
            Neither can see your receipts or invite anyone themselves.
          </p>

          {seats.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {seats.map((seat) => (
                <li
                  key={seat.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-zinc-800 px-4 py-3"
                >
                  <div className="flex flex-col">
                    <span className="text-sm text-white">{seat.label}</span>
                    <span className="text-xs text-zinc-500">
                      {seat.role === "cohost" ? "Co-host" : "Photographer"}
                      {seat.claimed_at ? "" : " · invite not opened yet"}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => void removeSeat(seat)}
                    className="rounded-full border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <select
              value={seatRole}
              onChange={(e) => setSeatRole(e.target.value as "cohost" | "photographer")}
              aria-label="Access level"
              className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
            >
              <option value="cohost">Co-host</option>
              <option value="photographer">Photographer</option>
            </select>
            <input
              value={seatLabel}
              onChange={(e) => setSeatLabel(e.target.value)}
              placeholder="Their name"
              maxLength={80}
              aria-label="Their name"
              className="min-w-40 flex-1 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
            />
            <button
              type="button"
              onClick={() => void inviteSeat()}
              disabled={!seatLabel.trim()}
              className="rounded-full border border-zinc-600 px-4 py-2 text-sm disabled:opacity-40"
            >
              Create invite
            </button>
          </div>

          {newSeat ? (
            <div className="flex flex-col gap-2 rounded-xl border border-zinc-700 bg-zinc-900 p-3">
              <p className="text-sm text-zinc-300">
                Send this link to {newSeat.seat.label}. It works once opened and
                expires in a week — this is the only time it is shown.
              </p>
              <p className="break-all font-mono text-xs text-zinc-400">
                {newSeat.invite_url}
              </p>
              <button
                type="button"
                onClick={copyInvite}
                className="self-start rounded-full bg-white px-4 py-1.5 text-xs font-medium text-black"
              >
                {inviteCopied ? "Copied" : "Copy invite link"}
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      {hasHostKey && isOwner && receipts && receipts.payments.length > 0 ? (
        <section className="flex flex-col gap-3">
          <h2 className="font-serif text-2xl text-white">Receipts</h2>
          <p className="text-sm text-zinc-400">
            Everything charged for this film. Refunds are recorded here and never
            take away seats from guests who already joined.
          </p>
          <ul className="flex flex-col gap-2">
            {receipts.payments.map((row) => (
              <li
                key={row.id}
                className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 rounded-xl border border-zinc-800 px-4 py-3"
              >
                <div className="flex flex-col">
                  <span className="text-sm text-white">{row.label}</span>
                  <span className="text-xs text-zinc-500">
                    {new Date(row.paid_at ?? row.created_at).toLocaleDateString()}
                    {row.tax_cents > 0
                      ? ` · incl. ${money(row.tax_cents, row.currency)} tax`
                      : ""}
                    {row.customer_email ? ` · ${row.customer_email}` : ""}
                  </span>
                </div>
                <div className="flex items-baseline gap-3">
                  {row.refunded_cents > 0 ? (
                    <span className="text-xs text-amber-400">
                      {row.status === "refunded"
                        ? "Refunded"
                        : `${money(row.refunded_cents, row.currency)} refunded`}
                    </span>
                  ) : null}
                  <span
                    className={
                      row.status === "refunded"
                        ? "text-sm text-zinc-500 line-through"
                        : "text-sm text-white tabular-nums"
                    }
                  >
                    {money(row.total_cents, row.currency)}
                  </span>
                  {row.receipt_url ? (
                    <a
                      href={row.receipt_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-zinc-400 underline"
                    >
                      Receipt
                    </a>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
          <p className="text-sm text-zinc-400">
            Paid {money(receipts.total_paid_cents, receipts.currency)}
            {receipts.total_tax_cents > 0
              ? `, including ${money(receipts.total_tax_cents, receipts.currency)} tax`
              : ""}
            {receipts.total_refunded_cents > 0
              ? ` · ${money(receipts.total_refunded_cents, receipts.currency)} refunded`
              : ""}
          </p>
        </section>
      ) : null}

      {hasHostKey ? (
        <section className="flex flex-col gap-3">
          <h2 className="font-serif text-2xl text-white">Inbox</h2>
          <p className="text-sm text-zinc-400">
            {canWrite
              ? "Hide a shot here and it will never appear in the gallery, even after the film develops."
              : "Every shot taken so far, including ones the host has hidden from the gallery."}
          </p>
          {reportedCount > 0 ? (
            <p className="rounded-xl border border-amber-800/70 bg-amber-950/30 px-4 py-3 text-sm text-amber-200">
              {reportedCount === 1
                ? "A guest reported a photo. It is still visible until you hide it."
                : `Guests reported ${reportedCount} photos. They are still visible until you hide them.`}
            </p>
          ) : null}
          {photos.length === 0 ? (
            <p className="text-zinc-500">No shots yet. This list refreshes on its own.</p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {inboxPhotos.map((photo) => (
                <figure key={photo.shot_id} className="relative">
                  {photo.kind === "clip" ? (
                    <ClipTile
                      url={photo.url}
                      posterUrl={photo.poster_url}
                      label={`Clip by ${photo.guest_name}`}
                      className={`aspect-[3/4] w-full rounded-lg bg-black object-cover ${photo.hidden ? "opacity-30" : ""} ${photo.report_count > 0 && !photo.hidden ? "ring-2 ring-amber-500" : ""}`}
                    />
                  ) : (
                    <>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={photo.url}
                        alt={`Shot by ${photo.guest_name}`}
                        className={`aspect-[3/4] w-full rounded-lg object-cover ${photo.hidden ? "opacity-30" : ""} ${photo.report_count > 0 && !photo.hidden ? "ring-2 ring-amber-500" : ""}`}
                      />
                    </>
                  )}
                  {photo.report_count > 0 ? (
                    <span className={`absolute right-1 rounded-full bg-amber-500 ${photo.kind === "clip" ? "top-7" : "top-1"} px-2 py-0.5 text-xs font-medium text-black`}>
                      {photo.report_count === 1
                        ? "Reported"
                        : `Reported ×${photo.report_count}`}
                    </span>
                  ) : null}
                  <figcaption
                    className={`absolute inset-x-0 flex items-center justify-between bg-black/60 px-2 py-1 text-xs text-white ${
                      photo.kind === "clip" ? "top-0" : "bottom-0"
                    }`}
                  >
                    <span>{photo.guest_name}</span>
                    {canWrite ? (
                      <button
                        type="button"
                        onClick={() => void toggleHidden(photo)}
                        className="rounded-full bg-white/20 px-2 py-0.5"
                      >
                        {photo.hidden ? "Unhide" : "Hide"}
                      </button>
                    ) : photo.hidden ? (
                      <span className="text-zinc-300">Hidden</span>
                    ) : null}
                  </figcaption>
                </figure>
              ))}
            </div>
          )}
        </section>
      ) : null}

      {hasHostKey && isOwner ? (
        <section className="flex flex-col gap-3 rounded-2xl border border-red-900/60 p-4">
          <h2 className="font-serif text-2xl text-white">Delete this film</h2>
          <p className="text-sm text-zinc-400">
            The film disappears for your guests straight away. The photos are
            kept for {GRACE_DAYS} days in case this was a mistake, then destroyed
            for good. For most events these are the only copies that exist.
          </p>
          <label htmlFor="delete-confirm" className="text-sm text-zinc-500">
            Type <span className="font-mono text-zinc-300">{code}</span> to
            confirm.
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <input
              id="delete-confirm"
              value={deleteConfirm}
              onChange={(e) => setDeleteConfirm(e.target.value)}
              autoComplete="off"
              className="w-40 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-sm"
            />
            <button
              type="button"
              onClick={() => void removeFilm()}
              disabled={deleteConfirm.trim().toUpperCase() !== code.toUpperCase() || deleting}
              className="rounded-full border border-red-800 px-5 py-2 text-sm text-red-300 disabled:opacity-40"
            >
              {deleting ? "Deleting…" : "Delete film"}
            </button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
