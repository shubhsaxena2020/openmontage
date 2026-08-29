import { Composition, registerRoot } from "remotion";
import { FitnessHUD, KineticCaptions } from "./FitnessHUD";

const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="FitnessHUD"
        component={FitnessHUD}
        durationInFrames={300}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          exercise: "GOBLET SQUAT",
          detail: "3 SETS · 12 REPS",
          target: 12,
          reps: 8,
          bg: "transparent",
        }}
      />
      <Composition
        id="KineticCaptions"
        component={KineticCaptions}
        durationInFrames={387}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ words: [], frame_schedule: [] }}
      />
    </>
  );
};

registerRoot(RemotionRoot);
