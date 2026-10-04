"use client";

import { useSyncExternalStore } from "react";

import { useI18n } from "@/components/guest/I18nProvider";

const neverChanges = () => () => {};

function readShouldShow(): boolean {
  const standalone = window.matchMedia("(display-mode: standalone)").matches;
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent);
  return ios && !standalone;
}

export function InstallHint() {
  const { t } = useI18n();
  const show = useSyncExternalStore(neverChanges, readShouldShow, () => false);
  if (!show) return null;

  return <p className="text-sm text-zinc-400">{t("installHint")}</p>;
}
