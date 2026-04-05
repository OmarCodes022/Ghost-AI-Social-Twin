"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

interface Contact {
  phone_number: string;
  name: string | null;
  relationship_tier: number;
  notes: string | null;
  voice_profile: Record<string, unknown> | null;
  last_interaction: string | null;
  created_at: string;
}

interface Memory {
  id: string;
  category: string;
  content: string;
  source: string | null;
  created_at: string;
}

interface Conversation {
  id: string;
  arc_state: string;
  message_count: number;
  started_at: string;
  last_message_at: string;
}

const categoryColor: Record<string, string> = {
  identity: "text-violet-400",
  behavioral: "text-blue-400",
  factual: "text-emerald-400",
  emotional: "text-orange-400",
  preference: "text-yellow-400",
  relationship: "text-pink-400",
  opinion: "text-cyan-400",
};

const arcColor: Record<string, string> = {
  open: "text-emerald-400",
  flowing: "text-blue-400",
  winding_down: "text-yellow-400",
  dormant: "text-zinc-600",
};

const tierLabel = ["", "closest", "close", "friend", "acquaintance", "stranger"];

export default function ContactDetailPage() {
  const { phone } = useParams<{ phone: string }>();
  const decoded = decodeURIComponent(phone);
  const router = useRouter();

  const [contact, setContact] = useState<Contact | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);

  // Edit state
  const [editName, setEditName] = useState("");
  const [editTier, setEditTier] = useState(2);
  const [editNotes, setEditNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // New memory state
  const [memText, setMemText] = useState("");
  const [memCategory, setMemCategory] = useState("relationship");
  const [addingMem, setAddingMem] = useState(false);

  async function load() {
    const res = await fetch(`/api/contacts/${encodeURIComponent(decoded)}`);
    if (!res.ok) return;
    const data = await res.json();
    setContact(data.contact);
    setMemories(data.memories);
    setConversations(data.conversations);
    setEditName(data.contact.name ?? "");
    setEditTier(data.contact.relationship_tier ?? 2);
    setEditNotes(data.contact.notes ?? "");
  }

  useEffect(() => { load(); }, [decoded]);

  async function saveProfile() {
    setSaving(true);
    await fetch(`/api/contacts/${encodeURIComponent(decoded)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: editName || null, relationship_tier: editTier, notes: editNotes || null }),
    });
    await load();
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
    setSaving(false);
  }

  async function deleteMemory(id: string) {
    await fetch(`/api/contacts/${encodeURIComponent(decoded)}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "memory", id }),
    });
    setMemories((m) => m.filter((x) => x.id !== id));
  }

  async function addMemory() {
    if (!memText.trim()) return;
    setAddingMem(true);
    const res = await fetch(`/api/contacts/${encodeURIComponent(decoded)}/memories`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: memText.trim(), category: memCategory }),
    });
    const row = await res.json();
    setMemories((m) => [row, ...m]);
    setMemText("");
    setAddingMem(false);
  }

  if (!contact) return <p className="text-zinc-600 text-sm">Loading…</p>;

  return (
    <div className="max-w-2xl space-y-5">
      <div>
        <Link href="/contacts" className="text-zinc-600 hover:text-zinc-400 text-xs">← contacts</Link>
      </div>

      {/* Profile editor */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-xs text-zinc-500 uppercase tracking-wider">profile</p>
          <span className="text-xs text-zinc-700 font-mono">{contact.phone_number}</span>
        </div>

        <div className="flex gap-3">
          <div className="flex-1">
            <label className="text-xs text-zinc-500 block mb-1">name</label>
            <input
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              placeholder="unknown"
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-500 block mb-1">tier</label>
            <select
              value={editTier}
              onChange={(e) => setEditTier(Number(e.target.value))}
              className="bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-sm text-zinc-200 focus:outline-none focus:border-zinc-500"
            >
              {[1, 2, 3, 4, 5].map((t) => (
                <option key={t} value={t}>{t} — {tierLabel[t]}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="text-xs text-zinc-500 block mb-1">notes</label>
          <textarea
            value={editNotes}
            onChange={(e) => setEditNotes(e.target.value)}
            rows={2}
            placeholder="anything worth knowing about this person…"
            className="w-full bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 resize-none"
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={saveProfile}
            disabled={saving}
            className="px-3 py-1.5 rounded bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-xs font-medium text-white transition-colors"
          >
            {saving ? "saving…" : "save"}
          </button>
          {saved && <span className="text-xs text-emerald-400">saved</span>}
          {contact.last_interaction && (
            <span className="text-xs text-zinc-700 ml-auto">
              last seen {new Date(contact.last_interaction).toLocaleDateString()}
            </span>
          )}
        </div>

        {contact.voice_profile && (
          <div className="pt-2 border-t border-zinc-800">
            <p className="text-xs text-zinc-500 mb-1">voice profile</p>
            <pre className="text-xs text-zinc-400 font-mono whitespace-pre-wrap">
              {JSON.stringify(contact.voice_profile, null, 2)}
            </pre>
          </div>
        )}
      </div>

      {/* Memories */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <h2 className="text-sm font-semibold text-zinc-400">Memories</h2>
          <span className="text-zinc-600 font-mono text-xs">({memories.length})</span>
        </div>

        {/* Add memory */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 mb-2 space-y-2">
          <div className="flex gap-2">
            <input
              value={memText}
              onChange={(e) => setMemText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") addMemory(); }}
              placeholder="add a memory…"
              className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
            />
            <select
              value={memCategory}
              onChange={(e) => setMemCategory(e.target.value)}
              className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-zinc-500"
            >
              {["relationship", "behavioral", "opinion", "factual", "preference"].map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <button
              onClick={addMemory}
              disabled={addingMem || !memText.trim()}
              className="px-3 py-1.5 rounded bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40 text-xs text-zinc-200 transition-colors"
            >
              add
            </button>
          </div>
        </div>

        {/* Memory list */}
        <div className="space-y-1.5">
          {memories.map((m) => (
            <div key={m.id} className="group bg-zinc-900 border border-zinc-800 rounded-lg px-3.5 py-2.5 flex items-start gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className={`text-[11px] font-mono ${categoryColor[m.category] ?? "text-zinc-500"}`}>
                    {m.category}
                  </span>
                  {m.source && <span className="text-[11px] text-zinc-700 font-mono">{m.source}</span>}
                  <span className="text-[11px] text-zinc-700 ml-auto">{new Date(m.created_at).toLocaleDateString()}</span>
                </div>
                <p className="text-xs text-zinc-300">{m.content}</p>
              </div>
              <button
                onClick={() => deleteMemory(m.id)}
                className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 text-xs transition-opacity shrink-0 pt-0.5"
              >
                ✕
              </button>
            </div>
          ))}
          {memories.length === 0 && <p className="text-zinc-600 text-sm">No memories yet.</p>}
        </div>
      </div>

      {/* Conversations */}
      <div>
        <h2 className="text-sm font-semibold text-zinc-400 mb-2">Conversations</h2>
        <div className="space-y-1.5">
          {conversations.map((c) => (
            <Link
              key={c.id}
              href={`/conversations/${c.id}`}
              className="flex items-center gap-3 px-3.5 py-2.5 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-zinc-700 transition-colors"
            >
              <span className={`text-xs font-mono ${arcColor[c.arc_state] ?? "text-zinc-600"}`}>{c.arc_state}</span>
              <span className="text-xs text-zinc-500">{c.message_count} msgs</span>
              <span className="text-xs text-zinc-700 ml-auto">
                {new Date(c.last_message_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              </span>
            </Link>
          ))}
          {conversations.length === 0 && <p className="text-zinc-600 text-sm">No conversations.</p>}
        </div>
      </div>
    </div>
  );
}
