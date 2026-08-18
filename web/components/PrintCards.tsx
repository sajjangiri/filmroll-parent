"use client";

import { API_URL } from "@/lib/api";

export function PrintCards({ code, title }: { code: string; title: string }) {
  const qrSrc = `${API_URL}/v1/films/${code}/qr.svg`;
  const cards = Array.from({ length: 8 }, (_, index) => index);

  return (
    <div className="bg-white p-6 text-black print:p-0">
      <div className="mb-6 flex items-center justify-between print:hidden">
        <p className="text-sm text-zinc-600">
          Print this page for table cards. Cut along the light borders.
        </p>
        <button
          type="button"
          onClick={() => window.print()}
          className="rounded-full bg-black px-5 py-2 text-sm text-white"
        >
          Print
        </button>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {cards.map((index) => (
          <article
            key={index}
            className="flex break-inside-avoid flex-col items-center gap-3 rounded-lg border border-zinc-300 p-6"
          >
            <p className="text-xs tracking-[0.25em] text-zinc-500">FILMROLL</p>
            <h1 className="text-center font-serif text-2xl">{title}</h1>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={qrSrc} alt="" width={180} height={180} className="bg-white" />
            <p className="font-mono text-xl tracking-widest">{code}</p>
            <p className="text-center text-xs text-zinc-500">
              Scan to pick up a camera. No app needed.
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}
