import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Talox Tech Stream | Multi-Tenant AI Platform",
  description: "Custom Python Multi-Tenant SaaS Agent Platform",
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
      </body>
    </html>
  );
}
