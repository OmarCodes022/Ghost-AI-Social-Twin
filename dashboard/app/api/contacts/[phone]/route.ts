import { NextResponse } from "next/server";
import sql from "@/lib/db";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ phone: string }> }
) {
  const { phone } = await params;
  const decoded = decodeURIComponent(phone);

  const [contact] = await sql`
    SELECT * FROM contacts WHERE phone_number = ${decoded}
  `;
  if (!contact) return NextResponse.json({ error: "not found" }, { status: 404 });

  const memories = await sql`
    SELECT id, category, content, source, created_at
    FROM knowledge_chunks
    WHERE contact_phone = ${decoded}
    ORDER BY created_at DESC
  `;

  const conversations = await sql`
    SELECT id, arc_state, message_count, started_at, last_message_at
    FROM conversations
    WHERE contact_phone = ${decoded}
    ORDER BY last_message_at DESC
    LIMIT 20
  `;

  return NextResponse.json({ contact, memories, conversations });
}

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ phone: string }> }
) {
  const { phone } = await params;
  const decoded = decodeURIComponent(phone);
  const body = await req.json();

  const allowed = ["name", "relationship_tier", "notes"];
  const updates = Object.entries(body).filter(([k]) => allowed.includes(k));
  if (!updates.length) return NextResponse.json({ error: "no valid fields" }, { status: 400 });

  for (const [field, value] of updates) {
    await sql`UPDATE contacts SET ${sql(field)} = ${value as string} WHERE phone_number = ${decoded}`;
  }

  const [updated] = await sql`SELECT * FROM contacts WHERE phone_number = ${decoded}`;
  return NextResponse.json(updated);
}

export async function DELETE(
  req: Request,
  { params }: { params: Promise<{ phone: string }> }
) {
  const { phone } = await params;
  const decoded = decodeURIComponent(phone);
  const body = await req.json().catch(() => ({}));

  if (body.type === "memory" && body.id) {
    await sql`DELETE FROM knowledge_chunks WHERE id = ${body.id} AND contact_phone = ${decoded}`;
    return NextResponse.json({ ok: true });
  }

  return NextResponse.json({ error: "specify type=memory and id" }, { status: 400 });
}
