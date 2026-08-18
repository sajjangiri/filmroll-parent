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
  guest_count: number;
  shot_count: number;
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
};

export type ReserveResponse = {
  shot_id: string;
  upload_url: string;
  storage_key: string;
  expires_in: number;
  already_reserved: boolean;
  shots_remaining: number;
};

export type CommitResponse = {
  shot_id: string;
  state: string;
  shots_remaining: number;
};

export type GalleryPhoto = {
  shot_id: string;
  guest_name: string;
  uploaded_at: string | null;
  url: string;
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
  url: string;
};

export type ReviewResponse = {
  shot_count: number;
  hidden_count: number;
  photos: ReviewPhoto[];
};

export type ExportResponse = {
  status: "idle" | "pending" | "ready" | "failed" | string;
  shot_count: number;
  download_url: string | null;
};
