import type { Metadata } from "next";
import "./globals.css";
import { ClientChatbotMount } from "@/components/shared/ClientChatbotMount";

export const metadata: Metadata = {
  title: "Teloxtech SaaS | Autonomous Multi-Tenant AI Platform",
  description: "Enterprise Multi-Tenant SaaS with Independent Client & Admin Portals",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen bg-slate-50 text-slate-900">
        {children}
        <ClientChatbotMount />
      </body>
    </html>
  );
}
