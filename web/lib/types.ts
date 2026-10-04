/**
 * Shapes returned by the Filmroll API.
 *
 * Field names are snake_case because they mirror the backend responses exactly
 * rather than being remapped on the way in. One less place for the two sides to
 * drift apart.
 */

export type FilmPublic = {
  code: string;
  title: string;
  event_type: string;
  closes_at: string;
  reveal_at: string;
  is_developed: boolean;
  is_closed: boolean;
  shot_limit: number;
  guest_cap: number;
  entitled_guest_cap: number;
  keep_forever: boolean;
  unlimited_shots: boolean;
  /** Paid add-on. Guests can record clips only when true. */
  video_pack: boolean;
  /** Clips each guest may record; 0 without the video pack. */
  clips_per_guest: number;
  clip_max_seconds: number;
  /** Live gallery: shots are visible as they land. Fixed at creation. */
  instant_reveal: boolean;
  /** False: gallery URLs are minted only for the calling guest's own shots. */
  shared_gallery: boolean;
  storage_until: string;
  guest_count: number;
  shot_count: number;
  /** Whether joining needs a PIN. The digits themselves are never sent. */
  requires_pin: boolean;
  join_url: string;
};

export type FilmCreated = {
  film: FilmPublic;
  host_token: string;
};

export type JoinResponse = {
  guest_id: string;
  guest_token: string;
  display_name: string;
  shots_remaining: number;
  clips_remaining: number;
};

export type ReserveResponse = {
  shot_id: string;
  upload_url: string;
  storage_key: string;
  expires_in: number;
  already_reserved: boolean;
  shots_remaining: number;
  clips_remaining: number;
  /** The type the upload URL was signed for; PUT with exactly this. */
  content_type: string;
};

export type CommitResponse = {
  shot_id: string;
  state: string;
  shots_remaining: number;
  clips_remaining: number;
};

export type ShotKind = "photo" | "clip";

export type GalleryPhoto = {
  shot_id: string;
  guest_name: string;
  uploaded_at: string | null;
  /** For a clip, the transcoded MP4. */
  url: string;
  kind: ShotKind;
  poster_url: string | null;
  duration_ms: number | null;
  /** Screen-sized photo once the worker has made it; null until then and for clips. */
  display_url: string | null;
};

export type GalleryResponse = {
  is_developed: boolean;
  shot_count: number;
  /** Always empty until the film develops; the server mints no URLs before then. */
  photos: GalleryPhoto[];
};

export type ReviewPhoto = {
  shot_id: string;
  guest_name: string;
  uploaded_at: string | null;
  hidden: boolean;
  /** How many guests flagged this. Never who. */
  report_count: number;
  url: string;
  kind: ShotKind;
  poster_url: string | null;
  duration_ms: number | null;
};

export type ReviewResponse = {
  shot_count: number;
  hidden_count: number;
  /** Reported and still visible, i.e. what is waiting on the host. */
  reported_count: number;
  photos: ReviewPhoto[];
};

export type ExportResponse = {
  status: "idle" | "pending" | "ready" | "failed" | string;
  shot_count: number;
  download_url: string | null;
};

export type BillingTier = {
  id: string;
  guest_cap: number;
  amount_cents: number;
  currency: string;
  label: string;
};

export type BillingAddon = {
  id: string;
  amount_cents: number;
  currency: string;
  label: string;
};

export type CatalogResponse = {
  free_guest_cap: number;
  storage_days: number;
  currency: string;
  tiers: BillingTier[];
  addons: BillingAddon[];
};

export type CheckoutResponse = {
  url: string;
  fake: boolean;
  amount_cents: number;
};

export type HostAccount = {
  email: string | null;
  unlimited_shots: boolean;
};

/** `amount_cents` is the catalog price; `total_cents` is what Stripe captured. */
export type PaymentReceipt = {
  id: string;
  kind: string;
  label: string;
  status: "paid" | "refunded";
  amount_cents: number;
  tax_cents: number;
  total_cents: number;
  refunded_cents: number;
  currency: string;
  receipt_url: string | null;
  customer_email: string | null;
  created_at: string;
  paid_at: string | null;
  refunded_at: string | null;
};

export type ReportReason = "inappropriate" | "private" | "other";

export type ReportResponse = {
  shot_id: string;
  report_count: number;
};

export type FilmDeleted = {
  code: string;
  deleted_at: string | null;
  /** After this the photos are gone for good and restore returns 410. */
  purge_at: string;
};

/** `host` is the film creator, who holds no seat and cannot be removed. */
export type StaffRole = "host" | "cohost" | "photographer";

export type SeatPublic = {
  id: string;
  role: Exclude<StaffRole, "host">;
  label: string;
  created_at: string;
  claimed_at: string | null;
};

export type SeatCreated = {
  seat: SeatPublic;
  invite_token: string;
  invite_url: string;
};

export type SeatsResponse = {
  seats: SeatPublic[];
};

export type SeatClaimed = {
  token: string;
  role: Exclude<StaffRole, "host">;
  label: string;
  film: FilmPublic;
};

export type PaymentsResponse = {
  payments: PaymentReceipt[];
  total_paid_cents: number;
  total_tax_cents: number;
  total_refunded_cents: number;
  currency: string;
};
