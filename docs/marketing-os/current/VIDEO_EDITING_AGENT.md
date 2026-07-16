# Native Video Editing Agent

> Status: native understanding, renderer-neutral Video IR, capability routing,
> pinned offline Remotion/HyperFrames scene executors, scene cache and FFmpeg final
> assembly, provider-neutral material sourcing, official Pexels video integration,
> and approval-gated Hermes TTS import implemented. Live provider and human
> full-chain acceptance remain release work.

## Product Boundary

Marketing OS owns high-quality faceless material video. It does not absorb the
separate Video Studio's digital-human, cast, cinematic-generation or advanced
film-production state.

Hermes owns video understanding, approved edit intent, material identity and
rights, renderer jobs, outputs, review receipts and downstream learning.
Electron only shows those states and collects explicit user decisions.

## Five Layers

### 1. Video Understanding

`video_analyze` is the native bottom capability used for source inspection,
benchmark decomposition and render review.

- `direct`: send a bounded small video to a video-capable model.
- `sampled`: probe locally, extract uniformly distributed frames, add source
  timestamps and send contact sheets to a vision model.
- `auto`: choose sampled mode for files above 20 MB or a focused time range.

Sampled mode must label visible evidence separately from inference and cannot
claim audio, transcript or unsampled continuity. Transcription, OCR, silence,
beat and motion analysis will become separate evidence tracks instead of being
hidden inside one free-text answer.

### 2. Material Intelligence

One native material search request checks user/account-owned assets first, then
fans out to approved providers. Candidates are normalized under one durable
Hermes contract, deduplicated by stable provider identity, checked for rights
and ranked against a shot requirement. Provider adapters never own project
state. The first configured adapter uses the official Pexels v1 video API;
`PEXELS_API_KEY` is read only by the provider and never enters `state.db`.

The ranker combines semantic shot fit, account/brand fit, visual quality,
continuity with adjacent scenes, source reliability, rights confidence, cost and
novelty. A human can always inspect source and license evidence before selection.
The selected provider binary is downloaded only after explicit source/license
review, then hashed and imported into `MediaAssetRepository`. Pexels source,
creator, license URL and rights caveat remain attached to the immutable asset
receipt; search-result URLs alone never satisfy the render gate.

Voiceover follows the same intent-before-effect rule. The Agent first persists
the exact script and SHA-256 as a `marketing_audio_job`; only a one-shot human
approval can call the user's configured native Hermes TTS provider. The actual
audio output is imported as a voice asset with provider, approval and script-hash
evidence. BGM remains a user-confirmed or separately licensed audio asset and is
mixed by the existing FFmpeg lane rather than by a second music subsystem.

### 3. Marketing Video IR

The immutable `marketing.video.ir.v1` is now the approved renderer-neutral scene
contract. Existing `marketing.faceless_video.edl.v1` requests are upgraded into
this IR and compiled back to the same FFmpeg EDL, preserving existing execution
and idempotency. Remotion JSX and HyperFrames HTML remain derived build artifacts:

```json
{
  "version": "marketing.video.ir.v1",
  "canvas": {"width": 1080, "height": 1920, "fps": 30},
  "scenes": [{
    "id": "scene_01",
    "duration": 4,
    "purpose": "hook",
    "visuals": [{
      "media_asset_id": "media_01",
      "source_in": 0,
      "fit": "cover"
    }],
    "text": [],
    "motion_intent": ["straight_cut"],
    "required_capabilities": ["source_media", "crop_cover", "straight_cut"],
    "constraints": {"safe_area": "short_vertical", "rights_required": true},
    "renderer_policy": {"preference": "auto", "fallback": "ffmpeg"},
    "review_rules": ["hook remains readable in the first second"]
  }],
  "captions": [],
  "audio": {},
  "review_rules": []
}
```

Only normalized intent and references are approved. Each scene and the complete
IR receive canonical SHA-256 identities. The render plan binds those hashes to a
capability decision, and the Render Receipt records the IR and plan hashes. This
makes a changed scene discoverable without invalidating unrelated scenes.

### Borrowed From High-End Video

The independent Video Studio informed four contract patterns without becoming a
dependency or owner:

- Shot-contract locality became stable scene IDs and scene hashes, enabling a
  future minimal-repair queue rather than full-video regeneration.
- Model capability evidence became a deterministic renderer capability matrix.
  A requested effect is routed only when one enabled renderer can actually express
  every required capability.
- Paid generation's intent-before-effect rule remains the gate for future missing
  shots and TTS. Local renderer approval never authorizes a paid provider call.
- Whole-film review informed time-bounded findings and repair scope; real audience
  Receipts still remain separate from visual QA.

Marketing OS did not import Video Studio's project blackboard, crew roles,
continuity ledger, provider sessions, cinematic generation state or budget owner.

### 4. Renderer Router

The router scores each scene, not the whole video:

| Scene need | Preferred renderer | Reason |
|---|---|---|
| Normalize, trim, crop, caption, mux, delivery | FFmpeg | Deterministic, fast and packageable |
| React component, chart, data layout, reusable brand system | Remotion | Strong typed composition and component reuse |
| HTML/CSS motion insert, rapid designed sequence | HyperFrames | Fast authoring and lighter local iteration |
| Missing photoreal source shot | Approved generation provider | Only after cost/provenance approval |

Each renderer produces a normalized scene mezzanine plus a technical manifest.
FFmpeg assembles mezzanines, audio and captions into the final deliverable. If a
preferred renderer is unavailable, the router either uses the declared fallback
without changing meaning or stops for approval; it never silently degrades a
claim-bearing visual.

The product runtime now pins Remotion `4.0.488`, HyperFrames `0.7.57`, GSAP
`3.14.2` and React `19.2.4`. It packages their production dependency closure and
reuses the product's staged Playwright Chromium; render jobs never invoke runtime
`npx` or download a browser. Runtime health verifies exact package versions, Node
22+, browser and local entrypoints before exposing either advanced renderer. The
Remotion line is frozen at `4.0.488` across the manifest, source lockfile,
installed packages, staging and Hermes health. Moving to Remotion 5 requires
explicit user approval, a fresh license review and full renderer regression.

Every advanced output is normalized to the approved canvas, frame rate, duration,
GOP and H.264 pixel format before concat. The cache key binds the scene hash,
canvas, selected renderer and renderer-source fingerprint, so a changed scene or
template invalidates only its own mezzanine. Each Receipt records the actual
renderer, cache decision and scene output SHA-256.

### 5. QA And Learning

Before human review, the Agent checks duration, dimensions, frame rate, codec,
black/frozen frames, subtitle timing, safe areas, text contrast, clipping, audio
levels and provenance completeness. `video_analyze sampled` produces a visual
review sheet; direct analysis can inspect motion and audio only when the selected
model demonstrably supports them.

Human review creates an immutable decision or a revision request. Publishing and
metric checkpoints remain the only route from a final render to accepted account
learning. Visual quality scores never substitute for real audience receipts.

## Build Order

1. Completed: native `video_analyze` direct/sampled/auto is the shared inspection seam.
2. Completed: `marketing.video.ir.v1`, scene/IR hashes, capability plan, legacy
   EDL compatibility and Receipt binding are native Hermes contracts.
3. Completed: pinned Remotion and HyperFrames executors, packaged browser reuse,
   per-scene cache, normalized mezzanines and mixed-engine FFmpeg assembly.
4. Completed: provider-neutral material search, user-library priority, Pexels
   video adapter, stable provider deduplication and rights-reviewed materialization.
5. Completed: approval-gated native Hermes TTS output import and real voice/BGM
   FFmpeg mix with receipt-bound audio QA.
6. Completed: automated technical delivery, black/freeze and audio/loudness QA
   manifests are bound to each final media version and Render Receipt.
7. Completed: bounded production, asset, timeline, QA and review state is exposed
   in Electron while decisions continue to write through Hermes owners.
8. Run the deferred live-provider and end-to-end publish, metric, retro and
   learning acceptance test.

## Non-Goals

- Running Remotion and HyperFrames redundantly for every scene.
- Letting renderer code become the durable project format.
- Treating AI HOT or any trend aggregator as verified source evidence.
- Downloading browsers, models or paid assets without an explicit product step.
- Moving account, asset, browser, publishing or learning ownership into Electron.
