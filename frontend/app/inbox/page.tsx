"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Navbar } from "@/components/shared/Navbar";
import { Sidebar } from "@/components/shared/Sidebar";
import { apiRequest } from "@/lib/api";
import { getActiveTenant, getAuthToken } from "@/lib/auth";
import {
  MessageSquare,
  Bot,
  UserCheck,
  Send,
  RefreshCw,
  PauseCircle,
  PlayCircle,
  AlertCircle,
} from "lucide-react";

interface ConversationSession {
  id: string;
  channel: string;
  external_user_id: string;
  contact_name: string;
  status: string;
  human_takeover: boolean;
  takeover_at: string | null;
  last_message_at: string | null;
  last_message_preview: string;
  message_count: number;
}

interface InboxMessage {
  id: string;
  direction: "inbound" | "outbound";
  sender_id: string | null;
  content: string;
  timestamp: string | null;
}

export default function LiveInboxPage() {
  const [conversations, setConversations] = useState<ConversationSession[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeSession, setActiveSession] = useState<ConversationSession | null>(null);
  const [messages, setMessages] = useState<InboxMessage[]>([]);
  const [filterMode, setFilterMode] = useState<"all" | "takeover" | "ai">("all");
  const [replyText, setReplyText] = useState("");
  const [loadingList, setLoadingList] = useState(true);
  const [loadingThread, setLoadingThread] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [sending, setSending] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadConversations = useCallback(async () => {
    setLoadingList(true);
    setErrorMsg(null);
    const param =
      filterMode === "takeover"
        ? "?takeover_only=true"
        : filterMode === "ai"
        ? "?takeover_only=false"
        : "";
    try {
      const res = await apiRequest<ConversationSession[]>(`/api/v1/inbox/conversations${param}`);
      if (res.success && Array.isArray(res.data)) {
        setConversations(res.data);
        setSelectedId((prev) => prev || (res.data && res.data.length > 0 ? res.data[0].id : null));
      } else if (res.error) {
        setErrorMsg(res.error.message || "Failed to load conversations.");
      }
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to load CRM inbox.");
    } finally {
      setLoadingList(false);
    }
  }, [filterMode]);

  const loadThread = useCallback(async (sessionId: string) => {
    setLoadingThread(true);
    try {
      const res = await apiRequest<{ session: ConversationSession; messages: InboxMessage[] }>(
        `/api/v1/inbox/conversations/${sessionId}/messages`
      );
      if (res.success && res.data) {
        setActiveSession(res.data.session);
        setMessages(res.data.messages || []);
      }
    } finally {
      setLoadingThread(false);
    }
  }, []);

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }
    const tenant = getActiveTenant();
    if (!tenant?.id) {
      window.location.href = "/onboarding";
      return;
    }
    loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    if (selectedId) {
      loadThread(selectedId);
    } else {
      setActiveSession(null);
      setMessages([]);
    }
  }, [selectedId, loadThread]);

  const handleToggleTakeover = async (enable: boolean) => {
    if (!selectedId) return;
    setToggling(true);
    setErrorMsg(null);
    try {
      const res = await apiRequest<ConversationSession>(
        `/api/v1/inbox/conversations/${selectedId}/takeover`,
        {
          method: "POST",
          body: JSON.stringify({ enabled: enable }),
        }
      );
      if (res.success && res.data) {
        setActiveSession(res.data);
        setConversations((prev) => prev.map((c) => (c.id === res.data!.id ? res.data! : c)));
      } else {
        setErrorMsg(res.error?.message || "Could not update takeover status.");
      }
    } finally {
      setToggling(false);
    }
  };

  const handleSendReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedId || !replyText.trim()) return;
    setSending(true);
    setErrorMsg(null);
    try {
      const res = await apiRequest<any>(`/api/v1/inbox/conversations/${selectedId}/reply`, {
        method: "POST",
        body: JSON.stringify({
          message_body: replyText.trim(),
          enable_takeover: true,
        }),
      });
      if (res.success && res.data) {
        setReplyText("");
        if (res.data.session) {
          setActiveSession(res.data.session);
          setConversations((prev) =>
            prev.map((c) => (c.id === res.data.session.id ? res.data.session : c))
          );
        }
        await loadThread(selectedId);
      } else {
        setErrorMsg(res.error?.message || "Failed to send WhatsApp reply.");
      }
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar />
      <div className="flex flex-1">
        <Sidebar currentPath="/inbox" />

        <main className="flex-1 min-w-0 p-4 sm:p-6 md:p-8 max-w-7xl mx-auto w-full space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-5">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
                  Unified CRM Live Inbox (HITL Takeover)
                </h1>
                <span className="rounded-full bg-emerald-100 text-emerald-800 px-2.5 py-0.5 text-xs font-semibold">
                  WhatsApp &amp; Social
                </span>
              </div>
              <p className="mt-1 text-xs sm:text-sm text-slate-500">
                Inspect live customer chats and click Take Over to pause AI replies immediately when staff wants to chat.
              </p>
            </div>

            <button
              type="button"
              onClick={loadConversations}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loadingList ? "animate-spin" : ""}`} />
              <span>Refresh Inbox</span>
            </button>
          </div>

          {errorMsg && (
            <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 p-3.5 text-xs text-red-800">
              <AlertCircle className="h-4 w-4 shrink-0 text-red-600" />
              <span>{errorMsg}</span>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Conversations Sidebar */}
            <div className="lg:col-span-4 rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col">
              <div className="p-3 border-b border-slate-100 flex items-center gap-1.5">
                {(["all", "takeover", "ai"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setFilterMode(mode)}
                    className={`flex-1 rounded-lg px-2.5 py-1.5 text-[11px] font-semibold capitalize transition ${
                      filterMode === mode
                        ? "bg-slate-900 text-white"
                        : "bg-slate-100 text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {mode === "takeover" ? "Human Takeover" : mode === "ai" ? "AI Active" : "All Chats"}
                  </button>
                ))}
              </div>

              <div className="divide-y divide-slate-100 max-h-[540px] overflow-y-auto">
                {conversations.length === 0 ? (
                  <div className="p-8 text-center text-xs text-slate-400 space-y-2">
                    <MessageSquare className="h-7 w-7 mx-auto text-slate-300" />
                    <p>No customer conversations yet. Inbound WhatsApp chats appear here automatically.</p>
                  </div>
                ) : (
                  conversations.map((conv) => {
                    const isSelected = conv.id === selectedId;
                    return (
                      <button
                        key={conv.id}
                        type="button"
                        onClick={() => setSelectedId(conv.id)}
                        className={`w-full text-left p-3.5 transition space-y-1 ${
                          isSelected ? "bg-emerald-50/80 border-l-4 border-emerald-600" : "hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-bold text-slate-900 truncate">
                            {conv.contact_name || conv.external_user_id}
                          </span>
                          <span
                            className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                              conv.human_takeover
                                ? "bg-amber-100 text-amber-800"
                                : "bg-emerald-100 text-emerald-800"
                            }`}
                          >
                            {conv.human_takeover ? "Human" : "AI"}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500 font-mono truncate">{conv.external_user_id}</p>
                        {conv.last_message_preview && (
                          <p className="text-[11px] text-slate-600 truncate">{conv.last_message_preview}</p>
                        )}
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            {/* Thread View & HITL Takeover Controls */}
            <div className="lg:col-span-8 rounded-xl border border-slate-200 bg-white shadow-sm flex flex-col min-h-[540px]">
              {activeSession ? (
                <>
                  <div className="p-4 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-sm font-bold text-slate-900">
                          {activeSession.contact_name || activeSession.external_user_id}
                        </h2>
                        <span className="font-mono text-xs text-slate-500">
                          {activeSession.external_user_id}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        {activeSession.human_takeover
                          ? "AI auto-reply is PAUSED — human staff owns this conversation."
                          : "AI Concierge is actively replying using your RAG knowledge base."}
                      </p>
                    </div>

                    {activeSession.human_takeover ? (
                      <button
                        type="button"
                        disabled={toggling}
                        onClick={() => handleToggleTakeover(false)}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition"
                      >
                        <PlayCircle className="h-4 w-4" />
                        <span>Resume AI Auto-Reply</span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        disabled={toggling}
                        onClick={() => handleToggleTakeover(true)}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500 px-3.5 py-2 text-xs font-bold text-slate-950 hover:bg-amber-400 disabled:opacity-50 transition"
                      >
                        <PauseCircle className="h-4 w-4" />
                        <span>Take Over (Pause AI)</span>
                      </button>
                    )}
                  </div>

                  <div className="flex-1 p-4 space-y-3 overflow-y-auto max-h-[380px] bg-slate-50/50">
                    {loadingThread ? (
                      <p className="text-xs text-slate-400 text-center py-10">Loading conversation...</p>
                    ) : messages.length === 0 ? (
                      <p className="text-xs text-slate-400 text-center py-10">No messages logged in thread.</p>
                    ) : (
                      messages.map((m) => {
                        const isInbound = m.direction === "inbound";
                        const isHumanOut = !isInbound && (m.sender_id || "").startsWith("human:");
                        return (
                          <div
                            key={m.id}
                            className={`flex ${isInbound ? "justify-start" : "justify-end"}`}
                          >
                            <div
                              className={`max-w-[80%] rounded-xl px-3.5 py-2.5 text-xs space-y-1 shadow-sm ${
                                isInbound
                                  ? "bg-white border border-slate-200 text-slate-800"
                                  : isHumanOut
                                  ? "bg-slate-900 text-white"
                                  : "bg-emerald-600 text-white"
                              }`}
                            >
                              <div className="flex items-center gap-1.5 text-[10px] opacity-80 font-semibold">
                                {!isInbound && (isHumanOut ? <UserCheck className="h-3 w-3" /> : <Bot className="h-3 w-3" />)}
                                <span>
                                  {isInbound ? "Customer" : isHumanOut ? "Human Staff" : "AI Concierge"}
                                </span>
                                {m.timestamp && (
                                  <span>• {new Date(m.timestamp).toLocaleTimeString()}</span>
                                )}
                              </div>
                              <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>

                  <form
                    onSubmit={handleSendReply}
                    className="p-3.5 border-t border-slate-200 bg-white flex items-center gap-2.5 rounded-b-xl"
                  >
                    <input
                      type="text"
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                      placeholder="Type a direct human reply via WhatsApp (auto-pauses AI)..."
                      className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:border-emerald-500 focus:outline-none"
                    />
                    <button
                      type="submit"
                      disabled={sending || !replyText.trim()}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-2 text-xs font-bold text-white hover:bg-slate-800 disabled:opacity-50 transition"
                    >
                      <Send className="h-3.5 w-3.5" />
                      <span>{sending ? "Sending..." : "Send"}</span>
                    </button>
                  </form>
                </>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-xs text-slate-400 space-y-2">
                  <MessageSquare className="h-10 w-10 text-slate-300" />
                  <p className="font-semibold text-slate-600">Select a conversation on the left</p>
                  <p>View incoming WhatsApp messages, pause AI auto-replies, or reply directly as staff.</p>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
