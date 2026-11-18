# CapyChem launch films

The [28-second product film](../../assets/demo/v10/capychem-studio-launch.mp4?raw=1) follows a molecular edit from a local calculation to a downloadable pose. The camera moves from the molecular structure into the actual workspace. The [42-second CDK2 case study](../../assets/demo/v8/capychem-launch-silent.mp4?raw=1) follows the same experiment in detail, including the contact with Asp86 and both exports.

## Edit or render

Install the root workspace dependencies with pnpm. Run these commands from the repository root.

```sh
pnpm install --frozen-lockfile
pnpm --dir apps/launch check
pnpm launch:studio
pnpm launch:render
pnpm --dir apps/launch render:case
```

Remotion Studio includes two compositions. `CapyChemSpatialLaunch` renders the [product edit](src/product/SpatialLaunch.tsx) to `apps/launch/out/capychem-studio-launch.mp4`. `CapyChemV8Live` renders the [case study](src/v8/LiveFilm.tsx) to `apps/launch/out/cdk2-case.mp4`. Both use local assets and produce a silent 1920 × 1080 H.264 video at 30 fps. [Storyboard and editing references](../../docs/launch-v10/cut-notes.md)

## Verify the published files

With Node.js, FFmpeg, and ffprobe available, run `pnpm --dir apps/launch verify`. The check reads the original film exports, saved browser footage and selected pose. It checks their SHA-256 hashes, inspects the video streams, compares the held input frame with the browser footage, and reconstructs the distance between the two atoms in the case study. The reported 23 seconds is the observed run time. The edit shortens the wait on screen.

[Product-film verification](../../assets/demo/v10/verification.json) · [Case-study verification](../../assets/demo/v8/verification.json) · [Selected pose](public/v8/selected-pose.sdf)
