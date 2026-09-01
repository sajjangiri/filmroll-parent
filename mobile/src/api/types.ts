/**
 * Shapes returned by the Filmroll API. Field names match the backend.
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
  storage_until: string;
  guest_count: number;
  shot_count: number;
  join_url: string;
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
  photos: GalleryPhoto[];
};
