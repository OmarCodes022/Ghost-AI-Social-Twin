import { NextResponse } from "next/server";
import sql from "@/lib/db";

export async function GET() {
  const [row] = await sql`
    SELECT energy, social_battery, emotional_load, availability, notes, updated_at
    FROM ghost_state WHERE id = 1
  `;
  return NextResponse.json(row ?? null);
}

export async function POST(req: Request) {
  const body = await req.json();
  const allowed = ["energy", "social_battery", "emotional_load", "availability", "notes"];

  const updates = Object.entries(body).filter(([k]) => allowed.includes(k));
  if (!updates.length) return NextResponse.json({ error: "no valid fields" }, { status: 400 });

  for (const [field, value] of updates) {
    await sql`UPDATE ghost_state SET ${sql(field)} = ${value as string}, updated_at = NOW() WHERE id = 1`;
  }

  const [row] = await sql`
    SELECT energy, social_battery, emotional_load, availability, notes, updated_at
    FROM ghost_state WHERE id = 1
  `;
  return NextResponse.json(row);
}
