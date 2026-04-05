"use client";

import { useEffect, useState } from "react";

interface GhostState {
  energy: number;
  social_battery: number;
  emotional_load: number;
  availability: string;
  notes: string | null;
  updated_at: string;
}

function Bar({ value, color }: { value: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-32 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${value * 100}%` }} />
      </div>
      <span className="text-xs text-zinc-500 font-mono">{value.toFixed(2)}</span>
    </div>
  );
}

function SliderField({
  label,
  field,
  value,
  onChange,
}: {
  label: string;
  field: string;
  value: number;
  onChange: (field: string, v: number) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-zinc-500 w-32">{label}</span>
      <input
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={value}
        onChange={(e) => onChange(field, parseFloat(e.target.value))}
        className="w-32 accent-violet-500"
      />
      <span className="text-xs text-zinc-500 font-mono w-10">{value.toFixed(2)}</span>
    </div>
  );
}

export default function MoodPage() {
  const [state, setState] = useState<GhostState | null>(null);
  const [draft, setDraft] = useState<Partial<GhostState>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function load() {
    const res = await fetch("/api/mood");
    if (res.ok) {
      const data = await res.json();
      setState(data);
      setDraft({
        energy: data.energy,
        social_battery: data.social_battery,
        emotional_load: data.emotional_load,
        availability: data.availability,
        notes: data.notes ?? "",
      });
    }
  }

  useEffect(() => { load(); }, []);

  function setField(field: string, value: number | string) {
    setDraft((d) => ({ ...d, [field]: value }));
  }

  async function save() {
    setSaving(true);
    const res = await fetch("/api/mood", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    });
    if (res.ok) {
      const data = await res.json();
      setState(data);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    }
    setSaving(false);
  }

  if (!state || !draft) return <p className="text-zinc-600 text-sm">Loading…</p>;

  const availColor =
    state.availability === "deep" ? "text-emerald-400" :
    state.availability === "light" ? "text-yellow-400" : "text-red-400";

  return (
    <div className="max-w-lg space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-zinc-200">Ghost state</h1>
        <span className={`text-xs font-mono font-semibold ${availColor}`}>
          {state.availability}
        </span>
      </div>

      {/* Current bars */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-3">
        <p className="text-xs text-zinc-500 uppercase tracking-wider">current</p>
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <span className="text-xs text-zinc-500 w-32">energy</span>
            <Bar value={state.energy} color="bg-violet-500" />
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-zinc-500 w-32">social battery</span>
            <Bar value={state.social_battery} color="bg-blue-500" />
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-zinc-500 w-32">emotional load</span>
            <Bar value={state.emotional_load} color="bg-orange-500" />
          </div>
        </div>
        {state.notes && (
          <p className="text-xs text-zinc-400 border-t border-zinc-800 pt-2 italic">
            &ldquo;{state.notes}&rdquo;
          </p>
        )}
        <p className="text-[11px] text-zinc-700">
          updated {new Date(state.updated_at).toLocaleString()}
        </p>
      </div>

      {/* Edit form */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-4">
        <p className="text-xs text-zinc-500 uppercase tracking-wider">edit</p>

        <SliderField label="energy" field="energy" value={draft.energy ?? 0.6} onChange={setField} />
        <SliderField label="social battery" field="social_battery" value={draft.social_battery ?? 1.0} onChange={setField} />
        <SliderField label="emotional load" field="emotional_load" value={draft.emotional_load ?? 0.0} onChange={setField} />

        <div className="flex items-center gap-3">
          <span className="text-xs text-zinc-500 w-32">availability</span>
          <select
            value={draft.availability ?? "deep"}
            onChange={(e) => setField("availability", e.target.value)}
            className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500"
          >
            <option value="deep">deep</option>
            <option value="light">light</option>
            <option value="off">off</option>
          </select>
        </div>

        <div className="flex items-start gap-3">
          <span className="text-xs text-zinc-500 w-32 pt-1">notes</span>
          <textarea
            value={draft.notes ?? ""}
            onChange={(e) => setField("notes", e.target.value)}
            rows={2}
            placeholder="how ghost is feeling…"
            className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 resize-none"
          />
        </div>

        <div className="flex items-center gap-3 pt-1">
          <button
            onClick={save}
            disabled={saving}
            className="px-3 py-1.5 rounded bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-xs font-medium text-white transition-colors"
          >
            {saving ? "saving…" : "save"}
          </button>
          {saved && <span className="text-xs text-emerald-400">saved</span>}
        </div>
      </div>
    </div>
  );
}
