import { Composition, registerRoot } from "remotion";
import { KineticCaptions } from "./FitnessHUD";
// Real caption track produced by tools/subtitle/kinetic_word_sync.py on real speech audio.
// Path is relative to this file's build location; Remotion bundles it at render time.
import captions from "../../samples/samples/captions.json";

const RemotionCaptionsRoot: React.FC = () => {
  return (
    <Composition
      id="KineticCaptionsReal"
      component={KineticCaptions}
      durationInFrames={captions.frame_schedule.length}
      fps={captions.summary.fps}
      width={1080}
      height={1920}
      defaultProps={{
        words: captions.words,
        frame_schedule: captions.frame_schedule,
      }}
    />
  );
};

registerRoot(RemotionCaptionsRoot);
