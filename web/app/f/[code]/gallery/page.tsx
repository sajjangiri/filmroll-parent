import { getFilmByCode } from "@/lib/store";

export default async function GalleryPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  const film = await getFilmByCode(code);
  if (!film) {
    return <p className="p-8 text-red-400">Film not found.</p>;
  }

  const developed = film.revealed || Date.now() >= Date.parse(film.revealAt);
  if (!developed) {
    return (
      <main className="mx-auto flex min-h-full max-w-md flex-col justify-center gap-3 p-8">
        <h1 className="font-serif text-3xl text-white">{film.title}</h1>
        <p className="text-zinc-400">
          This film is still developing. Come back{" "}
          {new Date(film.revealAt).toLocaleString()}.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-full max-w-3xl flex-col gap-8 p-6">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">
          Developed
        </p>
        <h1 className="font-serif text-4xl text-white">{film.title}</h1>
        <p className="text-sm text-zinc-400">
          {film.shots.length} shots from {film.guests.length} people
        </p>
      </header>
      {film.shots.length === 0 ? (
        <p className="text-zinc-400">No one shot this roll.</p>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {film.shots.map((shot) => (
            <figure key={shot.id} className="relative">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={shot.url}
                alt={`Shot by ${shot.guestName}`}
                className="aspect-[3/4] w-full rounded-lg object-cover"
              />
              <figcaption className="absolute inset-x-0 bottom-0 bg-black/50 px-2 py-1 text-xs text-white">
                {shot.guestName}
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </main>
  );
}
