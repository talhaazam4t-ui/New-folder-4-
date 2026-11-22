import Link from "next/link";
import type { ReactNode } from "react";
import { SUPPORT_WHATSAPP_LINK, SUPPORT_WHATSAPP_NUMBER } from "@/lib/auth";

export function LegalPage({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: ReactNode;
}) {
  return (
    <main className="min-h-screen bg-slate-50 px-4 py-10 text-slate-800">
      <div className="mx-auto max-w-3xl rounded-xl bg-white p-6 shadow-sm sm:p-10">
        <Link href="/" className="text-sm font-semibold text-emerald-700 hover:underline">
          ← Teloxtech
        </Link>
        <h1 className="mt-4 text-3xl font-bold">{title}</h1>
        <p className="mt-1 text-xs text-slate-500">Last updated: {updated}</p>
        <div className="mt-6 space-y-5 text-sm leading-relaxed [&_h2]:mt-6 [&_h2]:text-lg [&_h2]:font-bold [&_ul]:list-disc [&_ul]:pl-5">
          {children}
          <h2>Contact</h2>
          <p>
            Teloxtech (https://teloxtech.stream). Questions or requests: WhatsApp{" "}
            <a className="text-emerald-700 underline" href={SUPPORT_WHATSAPP_LINK}>
              {SUPPORT_WHATSAPP_NUMBER}
            </a>
            .
          </p>
        </div>
        <div className="mt-8 flex gap-4 border-t pt-4 text-xs text-slate-500">
          <Link href="/privacy/" className="hover:underline">Privacy Policy</Link>
          <Link href="/terms/" className="hover:underline">Terms of Service</Link>
        </div>
      </div>
    </main>
  );
}
