"use client";

import React from "react";
import { usePathname } from "next/navigation";
import { ClientServicesChatbot } from "./ClientServicesChatbot";

export function ClientChatbotMount() {
  const pathname = usePathname();

  // Enforce strict Portal Separation: Do not display Client chatbot in Admin Portal
  if (pathname?.startsWith("/admin")) {
    return null;
  }

  return <ClientServicesChatbot />;
}
