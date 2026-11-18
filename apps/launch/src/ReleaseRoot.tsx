import { Composition } from "remotion";
import { SpatialLaunch, spatialFrames } from "./product/SpatialLaunch";
import { LiveFilmV8 } from "./v8/LiveFilm";
import capture from "./v8/source.json";
import type { VerifiedSourceV8 } from "./v8/types";

export function Root() {
  return (
    <>
      <Composition
        id="CapyChemSpatialLaunch"
        component={SpatialLaunch}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={spatialFrames}
      />
      <Composition
        id="CapyChemV8Live"
        component={LiveFilmV8}
        width={capture.width}
        height={capture.height}
        fps={capture.fps}
        durationInFrames={capture.durationFrames}
        defaultProps={{ source: capture as unknown as VerifiedSourceV8 }}
      />
    </>
  );
}
