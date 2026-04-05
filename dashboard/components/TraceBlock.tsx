"use client";
import { useState } from "react";

interface ToolCall {
  tool: string;
  input: Record<string, unknown>;
  output?: string;
  error?: string;
}

interface TraceBlockProps {
  toolCalls: ToolCall[];
  inputTokens: number;
  outputTokens: number;
  iterations: number;
  action: string;
}

const EMOJI: Record<string, string> = {
  search_memories: "🔍",
  get_history: "📖",
  save_memory: "💾",
  get_contact_profile: "👤",
  update_contact_profile: "✏️",
  get_mood_state: "🌡",
  update_mood: "💭",
  delay_reply: "⏱",
  request_human_review: "🚨",
  update_conversation_arc: "🔄",
};

function fmtInput(tool: string, inp: Record<string, unknown>): string {
  if (tool === "search_memories") return `"${String(inp.query ?? "").slice(0, 45)}"`;
  if (tool === "get_history") return `limit=${inp.limit ?? 20}`;
  if (tool === "save_memory") return `"${String(inp.content ?? "").slice(0, 35)}…", ${inp.category}`;
  if (tool === "update_contact_profile") return `${inp.field}="${inp.value}"`;
  if (tool === "update_mood") return `${inp.aspect}=${inp.value}`;
  if (tool === "update_conversation_arc") return `→ ${inp.state}`;
  if (tool === "delay_reply") return `${inp.seconds}s`;
  if (tool === "request_human_review") return `"${String(inp.reason ?? "").slice(0, 45)}"`;
  return "";
}

export default function TraceBlock({ toolCalls, inputTokens, outputTokens, iterations, action }: TraceBlockProps) {
  const [open, setOpen] = useState(false);
  const hasErrors = toolCalls.some((t) => t.error);

  return (
    <div className="mt-1 ml-1">
      <button
        onClick={() => setOpen((o) => !o)}
        className={`text-xs flex items-center gap-1.5 ${hasErrors ? "text-red-400" : "text-zinc-600 hover:text-zinc-400"} transition-colors`}
      >
        <span className="text-[10px]">{open ? "▼" : "▶"}</span>
        <span>
          {toolCalls.length > 0
            ? `${toolCalls.length} tool${toolCalls.length !== 1 ? "s" : ""}`
            : "no tools"}
          {" · "}
          {iterations} call{iterations !== 1 ? "s" : ""}
          {" · "}
          {inputTokens + outputTokens} tok
          {hasErrors && " · ❌"}
        </span>
      </button>

      {open && (
        <div className="mt-1.5 pl-3 border-l border-zinc-800 space-y-0.5">
          {toolCalls.length === 0 && (
            <p className="text-xs text-zinc-600 font-mono">no tool calls</p>
          )}
          {toolCalls.map((tc, i) => (
            <div key={i} className="font-mono text-xs leading-5">
              <span className="mr-1">{EMOJI[tc.tool] ?? "🔧"}</span>
              <span className="text-zinc-300">{tc.tool}</span>
              {fmtInput(tc.tool, tc.input) && (
                <span className="text-zinc-600">({fmtInput(tc.tool, tc.input)})</span>
              )}
              {tc.output && !tc.error && (
                <span className="text-zinc-500"> → {tc.output}</span>
              )}
              {tc.error && (
                <span className="text-red-400"> ✗ {tc.error}</span>
              )}
            </div>
          ))}
          <div className="text-[11px] text-zinc-700 pt-0.5 font-mono">
            {iterations} Claude call{iterations !== 1 ? "s" : ""} · {inputTokens} in + {outputTokens} out · {action}
          </div>
        </div>
      )}
    </div>
  );
}
