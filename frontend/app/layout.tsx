import type { Metadata } from "next";
import "./globals.css";
import { AnalyticsTracker } from "@/components/shared/AnalyticsTracker";
import { ClientChatbotMount } from "@/components/shared/ClientChatbotMount";

export const metadata: Metadata = {
  metadataBase: new URL("https://teloxtech.stream"),
  title: {
    default: "Teloxtech AI Automation | 24/7 AI Receptionist & Multi-Channel Lead Engine",
    template: "%s | Teloxtech AI Automation",
  },
  description:
    "Managed multi-tenant AI Voice Receptionist, WhatsApp Concierge, Cal.com appointment booking, and automated B2B outreach platform with Human-in-the-Loop approvals.",
  keywords: [
    "AI Receptionist",
    "WhatsApp Business Automation",
    "AI Voice Agent",
    "Cal.com Booking Automation",
    "B2B Lead Generation SaaS",
    "Teloxtech",
  ],
  alternates: {
    canonical: "/",
  },
  openGraph: {
    title: "Teloxtech AI Automation | 24/7 AI Receptionist & Multi-Channel Lead Engine",
    description:
      "Turn missed calls and prospects into booked appointments with managed AI Voice Agents, WhatsApp Concierge, and HITL B2B Outreach.",
    url: "https://teloxtech.stream",
    siteName: "Teloxtech Tech Stream",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Teloxtech AI Automation | Autonomous Multi-Tenant AI Platform",
    description:
      "24/7 AI Receptionist, WhatsApp Cloud API Concierge, and Tiered Global Lead Outreach with Human-in-the-Loop safety.",
  },
  robots: {
    index: true,
    follow: true,
  },
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
        <AnalyticsTracker />
        <ClientChatbotMount />
      </body>
    </html>
  );
}
