import { AbsoluteFill } from "remotion";

/**
 * BrandWatermark — a small branded badge pinned bottom-right (logo glyph + wordmark).
 * `opacity` lets the parent fade it in/out; `sub` is an optional secondary line.
 */
export const BrandWatermark: React.FC<{
  brand?: string;
  sub?: string;
  opacity?: number;
}> = ({ brand = "OPENMONTAGE", sub = "AI FILM", opacity = 0.85 }) => {
  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "flex-end",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          opacity,
          margin: 36,
          display: "flex",
          alignItems: "center",
          gap: 10,
          background: "rgba(0,0,0,0.45)",
          border: "1px solid rgba(255,255,255,0.18)",
          borderRadius: 999,
          padding: "8px 16px",
        }}
      >
        <div
          style={{
            width: 22,
            height: 22,
            borderRadius: 6,
            background: "linear-gradient(135deg,#22d3ee,#a855f7)",
          }}
        />
        <div style={{ color: "white", fontWeight: 800, letterSpacing: 2, fontSize: 16 }}>
          {brand}
        </div>
        <div style={{ color: "rgba(255,255,255,0.6)", fontWeight: 600, fontSize: 12 }}>
          {sub}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export default BrandWatermark;
