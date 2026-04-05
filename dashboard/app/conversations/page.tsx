import Link from "next/link";
import sql from "@/lib/db";

export const revalidate = 5;

const arcColor: Record<string, string> = {
  open: "bg-emerald-500/20 text-emerald-400",
  flowing: "bg-blue-500/20 text-blue-400",
  winding_down: "bg-yellow-500/20 text-yellow-400",
  dormant: "bg-zinc-800 text-zinc-600",
};

export default async function ConversationsPage() {
  const rows = await sql`
    SELECT c.id, c.contact_phone, c.arc_state, c.message_count, c.last_message_at,
           ct.name AS contact_name, ct.relationship_tier,
           (SELECT content FROM messages WHERE conversation_id = c.id ORDER BY sent_at DESC LIMIT 1) AS last_message
    FROM conversations c
    LEFT JOIN contacts ct ON ct.phone_number = c.contact_phone
    ORDER BY c.last_message_at DESC
  `;

  return (
    <div className="max-w-2xl">
      <h1 className="text-lg font-semibold text-zinc-200 mb-4">Conversations</h1>
      <div className="space-y-1.5">
        {rows.map((c) => (
          <Link
            key={c.id}
            href={`/conversations/${c.id}`}
            className="flex items-center gap-3 px-4 py-3 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-zinc-700 transition-colors"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-sm font-medium text-zinc-200">
                  {c.contact_name ?? c.contact_phone}
                </span>
                <span className="text-xs text-zinc-600 font-mono">{c.contact_phone}</span>
                <span className={`text-[11px] px-1.5 py-0.5 rounded font-mono ${arcColor[c.arc_state] ?? arcColor.dormant}`}>
                  {c.arc_state}
                </span>
              </div>
              {c.last_message && (
                <p className="text-xs text-zinc-500 truncate">{c.last_message}</p>
              )}
            </div>
            <div className="text-right shrink-0">
              <div className="text-xs text-zinc-600">
                {new Date(c.last_message_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              </div>
              <div className="text-xs text-zinc-700 mt-0.5">{c.message_count} msgs</div>
            </div>
          </Link>
        ))}
        {rows.length === 0 && (
          <p className="text-zinc-600 text-sm">No conversations yet.</p>
        )}
      </div>
    </div>
  );
}
