import { Composition, registerRoot } from "remotion";
import { StudioComposition } from "./StudioComposition";
import studioInput from "./studio_input.json";

/**
 * studio-entry — renders the final Kinetic Studio composite.
 *
 * IMPORTANT: the Python orchestrator writes `studio_input.json` at RUNTIME (brand,
 * caption schedule, resolved duration). Remotion statically bundles imports at `remotion
 * bundle` time, so we do NOT rely on the static import for the actual values — the
 * orchestrator passes the file in via `remotion render ... --props=studio_input.json`,
 * and `calculateMetadata` derives `durationInFrames` from those live props. The static
 * import here is only a safe fallback for `npm run studio` / build typechecking.
 *
 * On the laptop, `npm run studio` opens this in Remotion Studio at 60fps; the orchestrator
 * still drives headless renders via --props.
 */

const StudioRoot: React.FC = () => {
  return (
    <Composition
      id="StudioComposition"
      component={StudioComposition}
      defaultProps={{ input: studioInput }}
      durationInFrames={300}
      fps={studioInput.fps || 30}
      width={studioInput.width || 1080}
      height={studioInput.height || 1920}
      calculateMetadata={({ props }) => {
        const inp: any = (props && props.input) || studioInput;
        const dur =
          inp.durationInFrames ||
          (inp.frame_schedule && inp.frame_schedule.length) ||
          300;
        return {
          durationInFrames: Math.max(60, dur),
          fps: inp.fps || 30,
          width: inp.width || 1080,
          height: inp.height || 1920,
        };
      }}
    />
  );
};

registerRoot(StudioRoot);
