import { AbsoluteFill, useCurrentFrame, interpolate, spring } from "remotion";

/**
 * ExerciseNameCard — slides in from the left with the exercise name + a set/duration chip.
 * Pure presentational card; the parent composition supplies animated values.
 */
export const ExerciseNameCard: React.FC<{
  name: string;
  detail?: string;
  accent?: string;
}> = ({ name, detail, accent = "#f472b6" }) => {
  const frame = useCurrentFrame();
  const inX = spring({ frame, fps: 30, config: { damping: 14 } });
  const x = interpolate(inX, [0, 1], [-420, 0]);
  const opacity = interpolate(inX, [0, 1], [0, 1]);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "flex-start",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          transform: `translateX(${x}px)`,
          opacity,
          background: "rgba(10,12,20,0.72)",
          backdropFilter: "blur(8px)",
          borderLeft: `6px solid ${accent}`,
          borderRadius: 14,
          padding: "18px 28px",
          marginLeft: 48,
          boxShadow: "0 10px 40px rgba(0,0,0,0.5)",
        }}
      >
        <div style={{ fontSize: 40, fontWeight: 900, color: "white" }}>{name}</div>
        {detail ? (
          <div style={{ fontSize: 20, fontWeight: 600, color: accent, marginTop: 4 }}>
            {detail}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

export default ExerciseNameCard;
