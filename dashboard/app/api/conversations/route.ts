import { NextResponse } from "next/server";
import sql from "@/lib/db";

export async function GET() {
  const rows = await sql`
    SELECT
      c.id,
      c.contact_phone,
      c.arc_state,
      c.message_count,
      c.last_message_at,
      ct.name AS contact_name,
      ct.relationship_tier,
      (SELECT content FROM messages
       WHERE conversation_id = c.id
       ORDER BY sent_at DESC LIMIT 1) AS last_message
    FROM conversations c
    LEFT JOIN contacts ct ON ct.phone_number = c.contact_phone
    ORDER BY c.last_message_at DESC
    LIMIT 50
  `;
  return NextResponse.json(rows);
}
