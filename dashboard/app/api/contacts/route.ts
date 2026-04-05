import { NextResponse } from "next/server";
import sql from "@/lib/db";

export async function GET() {
  const rows = await sql`
    SELECT
      c.phone_number, c.name, c.relationship_tier,
      c.last_interaction, c.notes, c.voice_profile,
      COUNT(kc.id)::int AS memory_count
    FROM contacts c
    LEFT JOIN knowledge_chunks kc ON kc.contact_phone = c.phone_number
    GROUP BY c.phone_number
    ORDER BY c.last_interaction DESC NULLS LAST
  `;
  return NextResponse.json(rows);
}
