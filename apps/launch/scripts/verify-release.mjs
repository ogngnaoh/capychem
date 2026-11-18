import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "../../..");
const studio = resolve(root, "apps/launch");
const pub = resolve(studio, "public");
const media = resolve(root, "assets/demo");
const read = (file) => JSON.parse(readFileSync(file, "utf8"));
const sha = (file) =>
  createHash("sha256").update(readFileSync(file)).digest("hex");
const product = read(resolve(media, "v10/verification.json"));
const study = read(resolve(media, "v8/verification.json"));
const cut = read(resolve(studio, "src/v8/source.json"));

function verifyFilm(file, hash, frames) {
  assert.equal(sha(file), hash, `SHA-256 mismatch for ${file}`);
  const probe = JSON.parse(
    execFileSync(
      "ffprobe",
      [
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,nb_frames,r_frame_rate",
        "-of",
        "json",
        file,
      ],
      { encoding: "utf8" },
    ),
  );
  assert.equal(probe.streams.length, 1);
  const [video] = probe.streams;
  assert.equal(video.codec_type, "video");
  assert.equal(video.codec_name, "h264");
  assert.equal(video.width, 1920);
  assert.equal(video.height, 1080);
  assert.equal(video.r_frame_rate, "30/1");
  assert.equal(Number(video.nb_frames), frames);
}

function pixels(file, filters = []) {
  return execFileSync(
    "ffmpeg",
    [
      "-v",
      "error",
      "-i",
      file,
      ...filters,
      "-frames:v",
      "1",
      "-pix_fmt",
      "rgb24",
      "-f",
      "rawvideo",
      "pipe:1",
    ],
    { maxBuffer: 8 * 1024 * 1024 },
  );
}

verifyFilm(
  resolve(media, "v10/capychem-studio-launch.mp4"),
  product.media.sha256,
  840,
);
verifyFilm(
  resolve(media, "v8/capychem-launch-silent.mp4"),
  study.sha256,
  cut.durationFrames,
);
assert.equal(sha(resolve(media, "v10/poster.jpg")), product.edit.posterSha256);
assert.equal(
  sha(resolve(root, product.source.capture)),
  product.source.captureSha256,
);
const footage = resolve(root, product.source.capture);
assert.deepEqual(
  pixels(resolve(pub, "v8/input-hold.png")),
  pixels(footage, ["-vf", "select=eq(n\\,84)"]),
);

assert.equal(product.source.experimentId, cut.experimentId);
assert.equal(study.scientificIdentity.experimentId, cut.experimentId);
assert.equal(cut.experimentId, cut.submittedExperimentId);
assert.equal(cut.experimentId, cut.exportedExperimentId);
const evidence = cut.native.find((shot) => shot.measurement);
assert.ok(evidence, "Case cut has no measured contact");
const { record, contactId } = evidence.scene;
assert.equal(product.source.poseId, record.poseId);
assert.equal(study.scientificIdentity.poseId, record.poseId);
assert.equal(cut.candidateId, record.candidateId);
assert.equal(record.candidateSource, "supplied");
assert.equal(
  sha(resolve(pub, "v8/selected-pose.sdf")),
  product.source.exportedSdfSha256,
);
assert.equal(sha(resolve(pub, record.sdf)), product.source.exportedSdfSha256);
assert.equal(record.sdfSha256, study.scientificIdentity.sdfSha256);
assert.equal(sha(resolve(pub, record.view)), record.viewSha256);
assert.deepEqual(read(resolve(pub, record.view)), record.structure);
assert.equal(
  sha(resolve(pub, "v8/molecular/1H1S_prepared.pdb")),
  record.receptorSha256,
);

const contact = record.structure.contacts.find(
  (entry) => entry.id === contactId,
);
assert.ok(contact, "Selected 3D contact is missing");
const atoms = new Map(
  [...record.structure.ligandAtoms, ...record.structure.pocketAtoms].map(
    (atom) => [atom.id, atom],
  ),
);
const donor = atoms.get(contact.ligandAtom);
const acceptor = atoms.get(contact.proteinAtom);
assert.ok(donor && acceptor, "Selected contact atom is missing");
const distance = Math.hypot(
  ...donor.position.map((value, i) => value - acceptor.position[i]),
);
assert.ok(Math.abs(distance - contact.distance) < 1e-9);
assert.ok(
  Math.abs(distance - study.scientificIdentity.distanceAngstrom) < 1e-9,
);
assert.equal(record.poseId, cut.poseId);
console.log(
  `Verified both films, the source frame and the selected pose (${distance.toFixed(2)} Å).`,
);
