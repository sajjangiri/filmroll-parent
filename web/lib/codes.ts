const ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

export function randomId(length = 12) {
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  return Array.from(bytes, (b) => ALPHABET[b % ALPHABET.length]).join("");
}

export function filmCode() {
  return randomId(6);
}
