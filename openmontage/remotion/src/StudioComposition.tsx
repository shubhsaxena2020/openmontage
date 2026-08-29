import { AbsoluteFill, Series, useCurrentFrame, interpolate, Easing, Video, staticFile } from "remotion";
import { RepCounter } from "./RepCounter";
import { ExerciseNameCard } from "./ExerciseNameCard";
import { BrandWatermark } from "./BrandWatermark";

export type StudioInput = {
  video: string;
  brand: string;
  accent: string;
  watermark_sub: string;
  exercise: string;
  exercise_detail: string;
  words: { word: string; start: number; end: number; index: number }[];
  frame_schedule: number[];
  fps: number;
  width: number;
  height: number;
};

/**
 * StudioComposition — the FINAL composite for a Kinetic Studio short:
 *   layer 0: the tempo-ramped, reframed 9:16 workout footage (background)
 *   layer 1: exercise name card + rep counter HUD (kinetic, spring-animated)
 *   layer 2: branded FBC Arena watermark
 *   layer 3: word-level kinetic captions (highlighted per active word)
 * All driven by the studio_input.json produced by the Python orchestrator.
 */
export const StudioComposition: React.FC<{ input?: StudioInput }> = ({ input }) => {
  const frame = useCurrentFrame();
  // When rendered via studio-entry, `input` is supplied through defaultProps.
  const data = input as StudioInput;

  const active = data.frame_schedule && frame < data.frame_schedule.length
    ? data.frame_schedule[frame]
    : -1;

  return (
    <AbsoluteFill style={{ backgroundColor: "#05060a" }}>
      {/* Background: the beat-synced, reframed footage */}
      <AbsoluteFill>
        <Video
          src={staticFile(data.video)}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
          startFrom={0}
        />
        {/* subtle dark vignette so HUD stays legible */}
        <AbsoluteFill
          style={{ background: "linear-gradient(180deg, rgba(0,0,0,0.35), rgba(0,0,0,0.0) 30%, rgba(0,0,0,0.55))" }}
        />
      </AbsoluteFill>

      {/* HUD layers */}
      <ExerciseNameCard name={data.exercise} detail={data.exercise_detail} accent={data.accent} />
      <RepCounter reps={0} target={12} label="REPS" accent={data.accent} />
      <BrandWatermark brand={data.brand} sub={data.watermark_sub} />

      {/* Kinetic captions */}
      <AbsoluteFill
        style={{
          justifyContent: "flex-end",
          alignItems: "center",
          paddingBottom: 120,
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: 8,
            maxWidth: "82%",
            background: "rgba(0,0,0,0.42)",
            borderRadius: 16,
            padding: "14px 22px",
          }}
        >
          {(data.words || [])
            .slice(Math.max(0, active - 3), active + 4)
            .map((w) => {
              const isActive = w.index === active;
              return (
                <span
                  key={w.index}
                  style={{
                    fontSize: 36,
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
    </AbsoluteFill>
  );
};

export default StudioComposition;
