interface MoodState {
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
      <div className="w-24 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${value * 100}%` }} />
      </div>
      <span className="text-xs text-zinc-500 font-mono">{value.toFixed(2)}</span>
    </div>
  );
}

export default function MoodPanel({ mood }: { mood: MoodState }) {
  const availColor =
    mood.availability === "deep" ? "text-emerald-400" :
    mood.availability === "light" ? "text-yellow-400" : "text-red-400";

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-300">Ghost state</h2>
        <span className={`text-xs font-mono font-semibold ${availColor}`}>
          {mood.availability}
        </span>
      </div>

      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <span className="text-xs text-zinc-500 w-28">energy</span>
          <Bar value={mood.energy} color="bg-violet-500" />
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-zinc-500 w-28">social battery</span>
          <Bar value={mood.social_battery} color="bg-blue-500" />
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-zinc-500 w-28">emotional load</span>
          <Bar value={mood.emotional_load} color="bg-orange-500" />
        </div>
      </div>

      {mood.notes && (
        <p className="text-xs text-zinc-400 border-t border-zinc-800 pt-2 italic">
          &ldquo;{mood.notes}&rdquo;
        </p>
      )}

      <p className="text-[11px] text-zinc-700">
        updated {new Date(mood.updated_at).toLocaleString()}
      </p>
    </div>
  );
}
