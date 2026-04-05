import Link from "next/link";
import sql from "@/lib/db";
import MoodPanel from "@/components/MoodPanel";

export const revalidate = 10;

export default async function Home() {
  const [mood] = await sql`
    SELECT energy, social_battery, emotional_load, availability, notes, updated_at
    FROM ghost_state WHERE id = 1
  `;

  const conversations = await sql`
    SELECT c.id, c.contact_phone, c.arc_state, c.last_message_at,
           ct.name AS contact_name,
           (SELECT content FROM messages WHERE conversation_id = c.id ORDER BY sent_at DESC LIMIT 1) AS last_message,
           (SELECT role FROM messages WHERE conversation_id = c.id ORDER BY sent_at DESC LIMIT 1) AS last_role
    FROM conversations c
    LEFT JOIN contacts ct ON ct.phone_number = c.contact_phone
    ORDER BY c.last_message_at DESC
    LIMIT 10
  `;

  const [stats] = await sql`
    SELECT
      (SELECT COUNT(*) FROM contacts)::int AS contacts,
      (SELECT COUNT(*) FROM conversations)::int AS conversations,
      (SELECT COUNT(*) FROM knowledge_chunks)::int AS memories,
      (SELECT COUNT(*) FROM agent_traces)::int AS traces
  `;

  const arcColor: Record<string, string> = {
    open: "text-emerald-400",
    flowing: "text-blue-400",
    winding_down: "text-yellow-400",
    dormant: "text-zinc-600",
  };

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-lg font-semibold text-zinc-200">Dashboard</h1>

      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Contacts", value: stats.contacts },
          { label: "Conversations", value: stats.conversations },
          { label: "Memories", value: stats.memories },
          { label: "Agent traces", value: stats.traces },
        ].map((s) => (
          <div key={s.label} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
            <div className="text-xl font-mono font-semibold text-zinc-200">{s.value}</div>
            <div className="text-xs text-zinc-500 mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>

      {mood && <MoodPanel mood={mood} />}

      <div>
        <h2 className="text-sm font-semibold text-zinc-400 mb-3">Recent conversations</h2>
        <div className="space-y-1">
          {conversations.map((c) => (
            <Link
              key={c.id}
              href={`/conversations/${c.id}`}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-zinc-700 transition-colors group"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-zinc-200 font-medium">
                    {c.contact_name ?? c.contact_phone}
                  </span>
                  <span className={`text-xs font-mono ${arcColor[c.arc_state] ?? "text-zinc-600"}`}>
                    {c.arc_state}
                  </span>
                </div>
                {c.last_message && (
                  <p className="text-xs text-zinc-500 truncate mt-0.5">
                    {c.last_role === "agent" ? "Ghost: " : ""}
                    {c.last_message}
                  </p>
                )}
              </div>
              <span className="text-xs text-zinc-600 shrink-0">
                {new Date(c.last_message_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
