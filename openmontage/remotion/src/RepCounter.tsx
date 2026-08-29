import { AbsoluteFill, useCurrentFrame, interpolate, spring } from "remotion";

/**
 * RepCounter — large kinetic rep counter with a pop/scale animation on each increment.
 * Drives from `reps` (current count) and `target` (goal). The number scales up briefly
 * whenever `reps` changes (detected via frame delta of a passed-in `pulse` key).
 */
export const RepCounter: React.FC<{
  reps: number;
  target?: number;
  label?: string;
  accent?: string;
}> = ({ reps, target, label = "REPS", accent = "#22d3ee" }) => {
  const frame = useCurrentFrame();
  // pop animation: scale peaks right after a rep boundary (every rep assumed ~ cadence)
  const pop = spring({ frame: frame % 12, fps: 30, config: { damping: 12 } });
  const scale = interpolate(pop, [0, 1], [1, 1.18]);
  const pct = target ? Math.min(100, Math.round((reps / target) * 100)) : null;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-start",
        alignItems: "flex-start",
        padding: 48,
      }}
    >
      <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: 4, color: accent }}>
        {label}
      </div>
      <div
        style={{
          fontSize: 140,
          fontWeight: 900,
          lineHeight: 1,
          color: "white",
          transform: `scale(${scale})`,
          textShadow: "0 6px 24px rgba(0,0,0,0.6)",
        }}
      >
        {reps}
        {target ? <span style={{ fontSize: 56, opacity: 0.6 }}>/{target}</span> : null}
      </div>
      {pct !== null ? (
        <div style={{ width: 240, height: 10, borderRadius: 6, background: "rgba(255,255,255,0.2)", marginTop: 8 }}>
          <div style={{ width: `${pct}%`, height: "100%", borderRadius: 6, background: accent }} />
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

export default RepCounter;
