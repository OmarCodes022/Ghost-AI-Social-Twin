import { NextResponse } from "next/server";
import sql from "@/lib/db";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  const [conv] = await sql`
    SELECT c.id, c.contact_phone, c.arc_state, c.message_count,
           c.started_at, c.last_message_at,
           ct.name AS contact_name, ct.relationship_tier, ct.voice_profile
    FROM conversations c
    LEFT JOIN contacts ct ON ct.phone_number = c.contact_phone
    WHERE c.id = ${id}
  `;
  if (!conv) return NextResponse.json({ error: "not found" }, { status: 404 });

  const messages = await sql`
    SELECT
      m.id, m.role, m.content, m.sent_at, m.whatsapp_message_id,
      at.id          AS trace_id,
      at.tool_calls  AS trace_tool_calls,
      at.input_tokens,
      at.output_tokens,
      at.iterations,
      at.action      AS trace_action
    FROM messages m
    LEFT JOIN agent_traces at ON at.message_id = m.id
    WHERE m.conversation_id = ${id}
    ORDER BY m.sent_at ASC
  `;

  return NextResponse.json({ conversation: conv, messages });
}
