import { NextResponse } from "next/server";
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";
import sql from "@/lib/db";
import { randomUUID } from "crypto";

const lambda = new LambdaClient({ region: process.env.AWS_REGION ?? "eu-west-1" });
const ENV = process.env.GHOST_ENV ?? "dev";

export async function POST(req: Request) {
  const { conversation_id, text } = await req.json();
  if (!conversation_id || !text?.trim()) {
    return NextResponse.json({ error: "missing conversation_id or text" }, { status: 400 });
  }

  const [conv] = await sql`
    SELECT contact_phone FROM conversations WHERE id = ${conversation_id}
  `;
  if (!conv) return NextResponse.json({ error: "conversation not found" }, { status: 404 });

  const phone = conv.contact_phone;
  const msgId = randomUUID();

  await sql`
    INSERT INTO messages
      (id, conversation_id, role, content, sent_at, was_delayed, delay_seconds, confidence_score, escalated)
    VALUES
      (${msgId}, ${conversation_id}, 'agent', ${text.trim()}, NOW(), false, 0, 1.0, false)
  `;
  await sql`
    UPDATE conversations
    SET last_message_at = NOW(), message_count = message_count + 1
    WHERE id = ${conversation_id}
  `;

  const parts = text.trim().split("\n").filter((p: string) => p.trim());
  for (let i = 0; i < parts.length; i++) {
    await lambda.send(new InvokeCommand({
      FunctionName: `ghost-whatsapp-sender-${ENV}`,
      InvocationType: "Event",
      Payload: Buffer.from(JSON.stringify({
        to_phone_number: phone,
        message: parts[i].trim(),
        message_id: i === 0 ? msgId : null,
        part_index: i,
      })),
    }));
  }

  return NextResponse.json({ ok: true, parts: parts.length });
}
