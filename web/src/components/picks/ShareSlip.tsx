"use client";

import { useEffect, useState } from "react";
import { Check, Copy, MessageCircle } from "lucide-react";
import { formatSlipText, type ShareLeg } from "@/lib/share";
import { Button } from "@/components/ui/Button";

/**
 * `navigator.clipboard` only exists on secure origins. `localhost` counts, but
 * opening the app from a phone at `http://192.168.x.x:3000` does not, so fall
 * back to the old select-and-copy trick there.
 */
async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Permission denied; try the fallback below.
    }
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  const ok = document.execCommand("copy");
  area.remove();
  return ok;
}

/**
 * Sends a slip as text, not a link: the app runs locally, so a link wouldn't
 * open for anyone else, and text is what a friend needs to rebuild the bet.
 */
export function ShareSlip({ title, legs }: { title: string; legs: ShareLeg[] }) {
  const [copied, setCopied] = useState<boolean | null>(null);

  useEffect(() => {
    if (copied === null) return;
    const timer = setTimeout(() => setCopied(null), 2000);
    return () => clearTimeout(timer);
  }, [copied]);

  if (legs.length === 0) return null;

  // Built on click so "prices as of" is the moment it was sent.
  const text = () => formatSlipText(`Oddsmith · ${title}`, legs);

  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-widest text-faint">Share with friends</p>
      <div className="grid grid-cols-2 gap-2">
        <Button
          variant="secondary"
          size="lg"
          onClick={() =>
            window.open(`https://wa.me/?text=${encodeURIComponent(text())}`, "_blank", "noopener,noreferrer")
          }
        >
          <MessageCircle size={16} />
          WhatsApp
        </Button>
        <Button variant="secondary" size="lg" onClick={async () => setCopied(await copyText(text()))}>
          {copied ? <Check size={16} className="text-success" /> : <Copy size={16} />}
          {copied ? "Copied" : "Copy text"}
        </Button>
      </div>
      {copied === false && (
        <p className="text-[11px] text-danger">Couldn&apos;t copy. Your browser blocked clipboard access.</p>
      )}
    </div>
  );
}
