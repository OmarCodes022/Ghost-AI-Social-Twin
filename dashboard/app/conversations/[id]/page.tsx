"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import TraceBlock from "@/components/TraceBlock";

interface ToolCall {
  tool: string;
  input: Record<string, unknown>;
  output?: string;
  error?: string;
}

interface Message {
  id: string;
  role: "user" | "agent";
  content: string;
  sent_at: string;
  whatsapp_message_id: string | null;
  trace_id: string | null;
  trace_tool_calls: ToolCall[] | null;
  input_tokens: number | null;
  output_tokens: number | null;
  iterations: number | null;
  trace_action: string | null;
}

interface Conversation {
  id: string;
  contact_phone: string;
  contact_name: string | null;
  relationship_tier: number;
  arc_state: string;
  message_count: number;
  started_at: string;
  last_message_at: string;
}

const arcColor: Record<string, string> = {
  open: "text-emerald-400",
  flowing: "text-blue-400",
  winding_down: "text-yellow-400",
  dormant: "text-zinc-600",
};

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDateSep(iso: string) {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
}

function dayKey(iso: string) {
  return new Date(iso).toDateString();
}

export default function ConversationPage() {
  const { id } = useParams<{ id: string }>();
  const [conv, setConv] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const firstLoad = useRef(true);

  async function fetchData() {
    const res = await fetch(`/api/conversations/${id}`);
    if (!res.ok) { setError("Not found"); return; }
    const data = await res.json();
    setConv(data.conversation);
    setMessages((prev) => {
      // only scroll on new messages
      if (prev.length !== data.messages.length && !firstLoad.current) {
        setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
      }
      return data.messages;
    });
    if (firstLoad.current) {
      firstLoad.current = false;
      setTimeout(() => bottomRef.current?.scrollIntoView(), 50);
    }
  }

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function handleSend() {
    if (!draft.trim() || sending) return;
    setSending(true);
    const text = draft.trim();
    setDraft("");
    await fetch("/api/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: id, text }),
    });
    await fetchData();
    setSending(false);
  }

  if (error) return <p className="text-red-400 text-sm">{error}</p>;
  if (!conv) return <p className="text-zinc-600 text-sm">Loading…</p>;

  const displayName = conv.contact_name ?? conv.contact_phone;

  return (
    <div className="max-w-2xl flex flex-col h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="shrink-0 mb-4">
        <div className="flex items-center gap-2 mb-1">
          <Link href="/conversations" className="text-zinc-600 hover:text-zinc-400 text-xs">← conversations</Link>
        </div>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-zinc-200">{displayName}</h1>
          {conv.contact_name && (
            <span className="text-xs text-zinc-600 font-mono">{conv.contact_phone}</span>
          )}
          <span className={`text-xs font-mono ${arcColor[conv.arc_state] ?? "text-zinc-600"}`}>
            {conv.arc_state}
          </span>
          <span className="text-xs text-violet-400 font-mono">tier {conv.relationship_tier}</span>
        </div>
        <p className="text-xs text-zinc-600 mt-0.5">
          {conv.message_count} messages · started {new Date(conv.started_at).toLocaleDateString()}
        </p>
      </div>

      {/* Message thread */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {messages.map((msg, idx) => {
          const isAgent = msg.role === "agent";
          const parts = msg.content.split("\n").filter(Boolean);
          const showDateSep = idx === 0 || dayKey(msg.sent_at) !== dayKey(messages[idx - 1].sent_at);
          return (
            <div key={msg.id} className="space-y-1.5">
              {showDateSep && (
                <div className="flex items-center gap-3 py-1">
                  <div className="flex-1 h-px bg-zinc-800" />
                  <span className="text-[11px] text-zinc-600 font-mono">{formatDateSep(msg.sent_at)}</span>
                  <div className="flex-1 h-px bg-zinc-800" />
                </div>
              )}
              {/* Bubble row */}
              <div className={`flex ${isAgent ? "justify-end" : "justify-start"}`}>
                <div className={`flex flex-col gap-0.5 max-w-[70%] ${isAgent ? "items-end" : "items-start"}`}>
                  {parts.map((part, i) => (
                    <div key={i} className={`rounded-2xl px-3.5 py-2 text-sm ${
                      isAgent
                        ? "bg-violet-600/30 text-zinc-200 rounded-br-sm"
                        : "bg-zinc-800 text-zinc-200 rounded-bl-sm"
                    }`}>
                      {part}
                    </div>
                  ))}
                  <span className="text-[11px] text-zinc-700 font-mono px-1">{formatTime(msg.sent_at)}</span>
                </div>
              </div>

              {/* Agent trace — full-width debug card below the bubbles */}
              {isAgent && msg.trace_id && (
                <div className="bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2">
                  <TraceBlock
                    toolCalls={msg.trace_tool_calls ?? []}
                    inputTokens={msg.input_tokens ?? 0}
                    outputTokens={msg.output_tokens ?? 0}
                    iterations={msg.iterations ?? 0}
                    action={msg.trace_action ?? "reply"}
                  />
                </div>
              )}
            </div>
          );
        })}

        {messages.length === 0 && (
          <p className="text-zinc-600 text-sm text-center mt-12">No messages yet.</p>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Compose box */}
      <div className="shrink-0 pt-2 border-t border-zinc-800 mt-2">
        <div className="flex gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
            }}
            placeholder="send as ghost… (shift+enter for new line)"
            rows={1}
            className="flex-1 bg-zinc-900 border border-zinc-700 rounded-xl px-3.5 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 resize-none"
          />
          <button
            onClick={handleSend}
            disabled={sending || !draft.trim()}
            className="px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-sm font-medium text-white transition-colors"
          >
            {sending ? "…" : "send"}
          </button>
        </div>
        <p className="text-[11px] text-zinc-700 text-center mt-1.5">polling every 5s</p>
      </div>
    </div>
  );
}
