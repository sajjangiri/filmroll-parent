import { CreateFilmForm } from "@/components/CreateFilmForm";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-full w-full max-w-5xl flex-col gap-16 px-6 py-16">
      <header className="flex flex-col gap-4">
        <p className="text-xs uppercase tracking-[0.25em] text-zinc-500">
          Filmroll
        </p>
        <h1 className="max-w-xl font-serif text-5xl leading-tight text-white">
          Capture the day through everyone’s eyes.
        </h1>
        <p className="max-w-lg text-zinc-400">
          A disposable camera for your event. Guests join with a QR, shoot a
          limited roll, and the album develops after the night.
        </p>
      </header>
      <CreateFilmForm />
    </main>
  );
}
