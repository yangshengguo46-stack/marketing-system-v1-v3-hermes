# Faceless Video Pipeline Evaluation

> Evaluated: 2026-07-14
> Product lane: Marketing OS `faceless_video`

## Decision

The production owner remains native Hermes. A video method, CLI, React renderer,
browser agent, or prompt Skill never becomes the owner of account identity,
rights, EDL state, approvals, outputs, receipts, or learning.

The frozen pipeline is:

1. Hermes plans the content, evidence, audience-reaction hypotheses, material
   requirements, sound plan, rights gates, and immutable ContentAsset revision.
2. Hermes materializes account-scoped media assets and records source, rights,
   provider, content hash, local path, and references.
3. `VideoProductionRepository` validates and persists
   `marketing.faceless_video.edl.v1` idempotently.
4. A human approves that exact EDL. Paid generation and paid TTS require their
   own later approval and provider receipt; local rendering approval does not
   authorize paid calls.
5. `ffmpeg_timeline_v1` is the enabled baseline renderer. It normalizes video
   GOP/frame rate, crops or scales visuals, concatenates scenes, burns captions,
   mixes voice and music, probes the result, and validates duration and size.
6. Hermes imports the output as a derived, rights-inherited MediaAsset, creates
   an immutable ContentAsset revision, and settles a render Receipt.
7. Electron displays the material list, EDL, render state, output and human
   review controls. It does not render or own production truth.

The next renderer contract is not "choose Remotion or HyperFrames for the whole
video". Hermes will compile one approved Marketing Video IR and route each scene
to the cheapest renderer that preserves the intended design:

- FFmpeg for normalization, straight cuts, captions, audio mixing and delivery.
- Remotion for reusable React components, typography, charts, data-driven layout
  and programmatic brand systems.
- HyperFrames for fast HTML/CSS motion compositions and design-heavy inserts.
- A generated-video provider only for a missing source shot, after a separate
  cost and provenance approval.

All scene outputs return to FFmpeg for deterministic assembly and technical QC.
Renderer selection is execution metadata; it never changes the approved content,
rights, asset, receipt or learning owner.

## Tool Disposition

| Tool or project | Tested use | Product disposition |
|---|---|---|
| Video Use | Shared-material EDL, 30 ms audio fades, FFmpeg render and timeline QC | Keep editing and QC methods; do not create a second state owner. Its full conversational transcription path requires an external transcription provider. |
| Claude Video `watch` | 71 upstream tests and local 12-second HyperFrames/Remotion analysis with bounded frame extraction | Keep its scene-selection and review method as reference. Hermes `video_analyze` is the native owner and now exposes direct and timestamped sampled modes; external transcription remains optional. |
| HyperFrames | Vertical Chinese composition, lint, snapshots, contact sheet and final render | Keep as a fast designed-composition scene renderer after pinning its version and packaging its browser and licensed fonts. Never execute a floating `npx` dependency at runtime. |
| Official Remotion Skills | Same-material 12-second vertical composition, TypeScript check, still/contact-sheet review and full render | Keep the composition, captions, rendering and QA methods. Remotion is the preferred scene renderer for component/data/typography-heavy work, subject to license review. |
| AI HOT | Live selected-feed and version API smoke test | Optional Chinese AI market-signal source. Returned summaries are untrusted candidate evidence, not account truth, primary-source proof or a replacement for public-content natural experiments. |
| Generative Media Skills | Rights, provenance, storyboard, finishing and QA methods | Retain methods and gates; native Hermes remains the owner. |
| OpenMontage | End-to-end Remotion testbed | Research only. AGPL-3.0 code must not be copied into the product runtime. |
| Seedance 2 Skill | Shot prompt and continuity method | Optional missing-shot generator only, with explicit cost approval and generated-media provenance. Not a timeline owner. |
| UI-TARS Desktop | CLI and architecture inspection | Excluded from the core video path. A general GUI agent is only a future controlled fallback when no stable provider API exists. |
| Cheat on Content | Blind prediction, publish metadata, T+3d retro and rubric evolution | Keep methods as reference. Marketing OS Preflight, Receipt, Retro and learning candidates remain canonical. |
| DBSkill | Hook, script, spread, AI-check and benchmark research methods | Personal research only under CC BY-NC 4.0. Do not productize its code or content. |

## Executable Evidence

The evaluation used the same three four-second vertical abstract clips where a
shared-material comparison was possible.

- HyperFrames produced a 12.032 second, 1080 x 1920, 30 fps H.264/AAC output.
  Lint passed with zero errors and zero warnings; snapshots and a final contact
  sheet were visually inspected.
- Video Use's EDL helpers produced a 10.52 second, 720 x 1280, 24 fps H.264/AAC
  draft in approximately 2.5 seconds and generated a timeline QC sheet.
- OpenMontage/Remotion produced a 25.045 second, 1920 x 1080, 30 fps H.264/AAC
  code-to-screen demo. Initial setup downloaded a dedicated headless browser and
  was substantially heavier than the FFmpeg baseline.
- The native Marketing OS integration renders real image inputs through FFmpeg,
  verifies output duration and dimensions with ffprobe, creates a derived media
  asset, immutable content revision and render receipt, and returns the same
  completed production on repeat execution.

### Round 2: Same-material Remotion and video understanding

- A fresh Remotion composition used the same three four-second vertical clips as
  the HyperFrames test. It produced a 12.053 second, 1080 x 1920, 30 fps H.264/AAC
  output of 7,998,085 bytes. TypeScript passed and both stills and the final
  contact sheet were visually inspected after fixing one wipe boundary and one
  contrast defect.
- The Remotion result was richer in reusable typography, branded layout and
  data-driven composition. HyperFrames remained materially faster in this local
  run: approximately 55.6 seconds versus 138.4 seconds. This is evidence for a
  scene router, not evidence that either renderer should replace the other.
- First Remotion use downloaded a dedicated 98.4 MB Chrome Headless Shell. A
  product build must pin, package and prewarm this browser rather than downloading
  it during a user render.
- Claude Video `watch` analyzed both local renders by extracting bounded frames.
  Its upstream test suite passed 71 tests. No Whisper API key was configured, so
  no paid transcription call was made and audio was not inferred from frames.
- Hermes native `video_analyze` then extracted 12 timestamped frames from the
  Remotion output into one contact sheet. The probe reported 12.053 seconds,
  1080 x 1920 and 30 fps, proving the native sampled path against a real file.

The frozen five-layer editing Agent is documented in
[`../../current/VIDEO_EDITING_AGENT.md`](../../current/VIDEO_EDITING_AGENT.md).

### Round 3: Native IR and capability gate

- `marketing.video.ir.v1` now canonicalizes canvas, stable scenes, source
  visuals, text layers, motion intent, renderer policy, review rules, captions
  and audio references. Every scene and IR receives a deterministic SHA-256.
- `marketing.video.render_plan.v1` records the preferred renderer, selected
  renderer, capability set, fallback decision and reason per scene. FFmpeg is the
  only enabled runtime renderer in this round.
- Existing EDL requests upgrade to IR and compile back to the same EDL. Their
  historical idempotency key is preserved, and legacy database rows can receive
  derived IR/plan metadata without creating a second production.
- Render Receipts and immutable output revisions bind the IR and render-plan
  hashes. Comparing scene hashes exposes the minimal repair scope for later
  per-scene cache and rerender work.
- A fallback is accepted only when it satisfies the complete capability set.
  Kinetic typography, React/data components, layered composition and designed
  motion fail before approval while their executor is unavailable.
- The implementation borrows shot locality, capability evidence, pre-effect
  approval and minimal-repair ideas from the independent Video Studio. It does
  not import that product's blackboard, crew, continuity, provider session,
  budget or project ownership.

### Round 4: Pinned offline scene executors

- The product now pins Remotion `4.0.488`, HyperFrames `0.7.57`, GSAP `3.14.2`
  and React `19.2.4` in a standalone production lockfile. Runtime commands call
  local entrypoints directly; there is no render-time `npx`, package fetch or
  browser download.
- The pin is enforced in the manifest, source and installed lockfiles, actual
  installed packages, product staging and Hermes runtime health. Remotion 5 is
  blocked until explicit user approval, a fresh license review and full renderer
  regression are all recorded.
- Both renderers reuse the product's staged Playwright Chromium. Runtime health
  verifies exact package versions, Node 22+, browser existence and both local
  scripts before the capability router enables advanced scenes.
- A real native integration rendered one Remotion scene and one HyperFrames
  scene from the same Video IR, normalized both with FFmpeg, assembled a 1.2
  second 360 x 640, 24 fps H.264/AAC output, persisted the result and Receipt,
  then proved both scenes were cache hits on a second render.
- Renderer source files and the lockfile produce a runtime fingerprint included
  in each cache key. A scene edit invalidates its scene hash; a template or
  dependency edit invalidates the renderer fingerprint. Unchanged scenes remain
  reusable.
- Contact-sheet inspection caught a HyperFrames wipe that obscured the complete
  second scene at short durations. The wipe now has a deterministic completion
  state and a post-fix four-frame sheet shows the title and background through
  the remainder of the scene.
- The staged renderer closure contains 292 production packages and is about
  647 MB on this macOS x64 machine. The largest item is HyperFrames' hard
  `onnxruntime-node` dependency. This is a delivery-size risk to measure on a
  clean install, not a package to remove outside the upstream dependency graph.

Evaluation artifacts are intentionally kept outside the product repository at
`~/.codex/labs/video-pipeline-eval/`; they are test evidence, not runtime assets.

## Operational Rules

- Pin renderer versions in the product. Concurrent floating `npx` execution was
  observed to corrupt a temporary npm cache and hang checks.
- Package and prewarm the renderer browser. Do not silently download a browser
  during a user render.
- Package licensed fonts and reference them explicitly. System-font fallback is
  not a reproducible Chinese caption strategy.
- Normalize source clips to a fixed frame rate and one-second GOP before concat.
- Clamp visual-QC sample timestamps below `duration - 1/fps`; a sample exactly at
  stream duration can fail even when the render is valid.
- Keep original media immutable and place subtitles after picture edits.
- Store provider, model, prompt or request, cost, source, rights, hashes and
  output IDs for every generated or transformed asset.

## Material Intelligence Audit

The current repository has strong provenance and finishing methods but does not
yet have a production-ready multi-provider stock search owner. The installed
`media-use` resolver found FFmpeg, ffprobe and Node, but its HeyGen CLI dependency
was unavailable and unauthenticated. That resolver is therefore an optional
provider, not the material owner.

The native provider order should be:

1. User-owned and account-owned assets, because rights and brand fit are strongest.
2. Platform first-party captures and public evidence with explicit use limits.
3. Pexels/Pixabay for stock video; Unsplash for still photography.
4. Openverse/Wikimedia Commons for license-oriented image/audio discovery.
5. Freesound for sound effects, with per-asset license capture.
6. Generated shots only when the approved shot requirement remains unresolved.

Every candidate enters one native `MaterialCandidate` contract with provider,
source URL, creator, source license, retrieved-at time, content hash, semantic
shot tags, visual-quality score and account-fit score. Search-result URLs and
aggregated summaries are not rights evidence. The selected binary must be
materialized, deduplicated and rights-gated before it can enter an EDL.

## Source And License Pointers

- Video Use: <https://github.com/browser-use/video-use> (MIT)
- Claude Video: <https://github.com/bradautomates/claude-video> (MIT)
- HyperFrames: <https://github.com/heygen-com/hyperframes> (Apache-2.0)
- Remotion: <https://github.com/remotion-dev/remotion> (special commercial license)
- Official Remotion Skills: <https://github.com/remotion-dev/skills>
- AI HOT Skill: <https://github.com/KKKKhazix/khazix-skills/tree/main/aihot> (MIT)
- Generative Media Skills: <https://github.com/calesthio/generative-media-skills> (MIT)
- OpenMontage: <https://github.com/calesthio/OpenMontage> (AGPL-3.0)
- Seedance 2 Skill: <https://github.com/dexhunter/seedance2-skill> (MIT)
- UI-TARS Desktop: <https://github.com/bytedance/UI-TARS-desktop> (Apache-2.0)
- Cheat on Content: <https://github.com/XBuilderLAB/cheat-on-content> (MIT)
- DBSkill: <https://github.com/dontbesilent2025/dbskill> (CC BY-NC 4.0)
- Pexels API: <https://www.pexels.com/api/documentation/>
- Pixabay API: <https://pixabay.com/api/docs/>
- Unsplash API: <https://unsplash.com/documentation>
- Openverse API: <https://api.openverse.org/>
- Wikimedia Commons API: <https://commons.wikimedia.org/wiki/Commons:API>
- Freesound API: <https://freesound.org/docs/api/>
