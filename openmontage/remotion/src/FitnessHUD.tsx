import { AbsoluteFill, Series, useCurrentFrame, interpolate, Easing } from "remotion";
import { RepCounter } from "./RepCounter";
import { ExerciseNameCard } from "./ExerciseNameCard";
import { BrandWatermark } from "./BrandWatermark";

/**
 * FitnessHUD — composes rep counter + exercise name card + branded watermark over a
 * (transparent or video) background. `reps` can be driven per-segment via `segments`.
 */
export const FitnessHUD: React.FC<{
  exercise?: string;
  detail?: string;
  target?: number;
  reps?: number;
  bg?: string;
}> = ({
  exercise = "GOBLET SQUAT",
  detail = "3 SETS · 12 REPS",
  target = 12,
  reps = 8,
  bg = "transparent",
}) => {
  return (
    <AbsoluteFill style={{ background: bg }}>
      <ExerciseNameCard name={exercise} detail={detail} />
      <RepCounter reps={reps} target={target} />
      <BrandWatermark />
    </AbsoluteFill>
  );
};

/**
 * KineticCaptions — word-highlight subtitle layer driven by the kinetic_word_sync
 * frame_schedule. `words` + `frame_schedule` come straight from the Python tool's JSON.
 * The currently-spoken word (schedule[frame]>=0) is highlighted; others are dimmed.
 */
export const KineticCaptions: React.FC<{
  words: { word: string; start: number; end: number; index: number }[];
  frame_schedule: number[];
  fps?: number;
}> = ({ words, frame_schedule, fps = 30 }) => {
  const frame = useCurrentFrame();
  const active = frame < frame_schedule.length ? frame_schedule[frame] : -1;
  // show a small window of words around the active one
  const lo = Math.max(0, active - 3);
  const hi = Math.min(words.length, active + 4);
  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 90,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: 8,
          maxWidth: "80%",
          background: "rgba(0,0,0,0.4)",
          borderRadius: 16,
          padding: "14px 22px",
        }}
      >
        {words.slice(lo, hi).map((w) => {
          const isActive = w.index === active;
          return (
            <span
              key={w.index}
              style={{
                fontSize: 34,
                fontWeight: isActive ? 900 : 600,
                color: isActive ? "#fde047" : "rgba(255,255,255,0.55)",
                transform: isActive ? "scale(1.08)" : "scale(1)",
                transition: "transform 80ms linear",
              }}
            >
              {w.word}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

export default FitnessHUD;
