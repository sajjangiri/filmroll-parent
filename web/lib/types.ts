export type Guest = {
  id: string;
  name: string;
  joinedAt: string;
  shotsTaken: number;
};

export type Shot = {
  id: string;
  guestId: string;
  guestName: string;
  createdAt: string;
  url: string;
};

export type Film = {
  id: string;
  code: string;
  hostSecret: string;
  title: string;
  createdAt: string;
  closesAt: string;
  revealAt: string;
  revealed: boolean;
  shotLimit: number;
  guestCap: number;
  guests: Guest[];
  shots: Shot[];
};

export type PublicFilm = Omit<Film, "hostSecret">;
