import { NextResponse } from "next/server";
import sql from "@/lib/db";
import { randomUUID } from "crypto";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ phone: string }> }
) {
  const { phone } = await params;
  const decoded = decodeURIComponent(phone);
  const { content, category } = await req.json();

  const valid = ["relationship", "behavioral", "opinion", "identity", "factual", "preference"];
  const cat = valid.includes(category) ? category : "relationship";

  const [row] = await sql`
    INSERT INTO knowledge_chunks (id, category, content, contact_phone, source, created_at)
    VALUES (${randomUUID()}, ${cat}, ${content}, ${decoded}, 'manual', NOW())
    RETURNING id, category, content, source, created_at
  `;

  return NextResponse.json(row);
}
