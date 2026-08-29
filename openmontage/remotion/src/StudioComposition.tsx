import { AbsoluteFill, Series, useCurrentFrame, interpolate, Easing, Video, staticFile } from "remotion";
import { RepCounter } from "./RepCounter";
import { ExerciseNameCard } from "./ExerciseNameCard";
import { BrandWatermark } from "./BrandWatermark";
import { KineticCaptions, CaptionTheme } from "./FitnessHUD";

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
  caption_theme?: CaptionTheme;
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
  // When rendered via studio-entry, `input` is supplied through defaultProps.
  const data = input as StudioInput;
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

      {/* Kinetic captions — theme selectable via studio_input.caption_theme
          ("default" | "caption"); defaults to the v1.1 look. */}
      <KineticCaptions
        words={data.words || []}
        frame_schedule={data.frame_schedule || []}
        fps={data.fps || 30}
        theme={data.caption_theme || "default"}
      />
    </AbsoluteFill>
  );
};

export default StudioComposition;
