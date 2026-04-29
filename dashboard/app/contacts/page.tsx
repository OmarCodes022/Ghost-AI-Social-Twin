import Link from "next/link";
import sql from "@/lib/db";

export const revalidate = 30;

export default async function ContactsPage() {
  const rows = await sql`
    SELECT c.phone_number, c.name, c.relationship_tier, c.last_interaction,
           COUNT(kc.id)::int AS memory_count
    FROM contacts c
    LEFT JOIN knowledge_chunks kc ON kc.contact_phone = c.phone_number
    GROUP BY c.phone_number, c.name, c.relationship_tier, c.last_interaction
    ORDER BY c.last_interaction DESC NULLS LAST
  `;

  return (
    <div className="max-w-2xl">
      <h1 className="text-lg font-semibold text-zinc-200 mb-4">Contacts</h1>
      <div className="space-y-1.5">
        {rows.map((c) => (
          <Link
            key={c.phone_number}
            href={`/contacts/${encodeURIComponent(c.phone_number)}`}
            className="flex items-center gap-4 px-4 py-3 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-zinc-700 transition-colors"
          >
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-zinc-200">
                  {c.name ?? c.phone_number}
                </span>
                {c.name && (
                  <span className="text-xs text-zinc-600 font-mono">{c.phone_number}</span>
                )}
                <span className="text-xs text-violet-400 font-mono">tier {c.relationship_tier}</span>
              </div>
            </div>
            <div className="text-right text-xs">
              <div className="text-zinc-500">{c.memory_count} {c.memory_count === 1 ? "memory" : "memories"}</div>
              {c.last_interaction && (
                <div className="text-zinc-700 mt-0.5">
                  {new Date(c.last_interaction).toLocaleDateString()}
                </div>
              )}
            </div>
          </Link>
        ))}
        {rows.length === 0 && <p className="text-zinc-600 text-sm">No contacts yet.</p>}
      </div>
    </div>
  );
}
