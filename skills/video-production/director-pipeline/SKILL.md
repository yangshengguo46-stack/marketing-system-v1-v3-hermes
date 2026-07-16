---
name: director-pipeline
description: 9-agent director pipeline for video production — from one-line idea to final video with script, storyboard, voiceover, BGM, and visual style. Use when producing any video content, from short-form social media to brand videos.
---

# Director Pipeline

## When to Use
- Producing a video from a one-line idea
- Planning a multi-step video production workflow
- Coordinating script, visuals, voice, and music
- Batch-producing short videos

## The 9-Agent Pipeline

```
User Brief
    ↓
1. Research Agent → fact-check, references, brand context
    ↓
2. Script Agent → story outline, narrative structure
    ↓
3. Art Style Agent → visual direction, 34 built-in styles
    ↓
4. Storyboard Agent → scene-by-scene shot breakdown
    ↓
5. Character Agent → character design + voice assignment
    ↓
6. Location Agent → environment concepts per scene
    ↓
7. Voice Agent → TTS voice matching + narration plan
    ↓
8. BGM Agent → background music based on atmosphere
    ↓
9. Media Agent → orchestrate image/voice/music → final assets
```

## Agent Details

### 1. Research Agent
- **Input**: User's one-line idea
- **Output**: Research notes with sources, cautions, and references
- **Tasks**:
  - Check if the story references real people/events/brands
  - Gather factual context for accuracy
  - Identify potential sensitivity issues
  - Collect visual references for the art style agent

### 2. Script Agent
- **Input**: Research notes + user idea
- **Output**: Story outline with scene breakdown
- **Tasks**:
  - Select story structure (see `story-structure-router` skill)
  - Write logline and beat sheet
  - Break into scenes with dialogue
  - Identify emotional arc

### 3. Art Style Agent
- **Input**: Script + research visual references
- **Output**: Art direction document with style choice
- **Tasks**:
  - Select from 34 built-in styles (see below)
  - Define color palette
  - Specify visual motifs
  - Create mood board description

#### 34 Built-in Art Styles

| Category | Styles |
|----------|--------|
| Cinematic | Documentary Realism, Film Noir, Golden Hour, Teal & Orange |
| Commercial | Clean Product, Lifestyle Bright, Corporate Professional, Luxury Minimal |
| Futuristic | Neon Noir, Cyberpunk, Holographic, Space Age |
| Retro | 80s VHS, 90s Cartoon, Vintage Film, Polaroid Warm |
| Anime | Studio Ghibli, Dreamscape Watercolor, Cel Shaded, Chibi |
| 3D | Claymation, Low Poly, Photoreal 3D, Stylized 3D |
| Illustration | Hand Drawn, Watercolor, Ink Wash, Flat Design |
| Realistic | Portrait, Street Photography, Nature, Food Photography |
| Experimental | Glitch Art, Abstract, Collage, Mixed Media |

### 4. Storyboard Agent
- **Input**: Script + art style
- **Output**: Shot-by-shot storyboard
- **Tasks**:
  - Break each scene into shots
  - Specify shot type (wide, medium, close-up, etc.)
  - Describe composition and camera movement
  - Note transitions between shots

### 5. Character Agent
- **Input**: Script + art style + storyboard
- **Output**: Character designs with voice profiles
- **Tasks**:
  - Design visual appearance for each character
  - Assign personality traits matching the script
  - Match voice profile (gender, age, tone, language)
  - Create character reference sheets

### 6. Location Agent
- **Input**: Script + art style + storyboard
- **Output**: Environment concepts per scene
- **Tasks**:
  - Design key locations
  - Define lighting and atmosphere
  - Specify time of day, weather, season
  - Ensure visual continuity across scenes

### 7. Voice Agent
- **Input**: Character profiles + script
- **Output**: Voiceover plan with TTS assignments
- **Tasks**:
  - Assign TTS voices to characters
  - Plan narration vs. dialogue
  - Specify emotion and pacing for each line
  - Identify music vs. silence moments

### 8. BGM Agent
- **Input**: Script + emotional arc + art style
- **Output**: Background music plan
- **Tasks**:
  - Map emotional beats to music moods
  - Select tempo and instrumentation
  - Identify crescendo and silence points
  - Plan music transitions

### 9. Media Agent
- **Input**: All previous outputs
- **Output**: Final asset package
- **Tasks**:
  - Orchestrate image generation per storyboard shot
  - Generate voiceover audio
  - Generate/compose BGM
  - Sync audio with visuals
  - Package for target platform (aspect ratio, resolution, format)

## Short Video Adaptation (60-90 seconds)

For short-form content, compress the pipeline:

```
1. Research → Quick context (2 min)
2. Script → 7-beat compressed structure (5 min)
3. Art Style → Pick from top 5 styles (1 min)
4. Storyboard → 6-10 shots max (5 min)
5. Character → 1-2 characters max (2 min)
6. Location → 1-2 locations max (2 min)
7. Voice → 1 voiceover + optional dialogue (3 min)
8. BGM → 1 track, mood-matched (2 min)
9. Media → Generate + assemble (10 min)
```

## Batch Mode

For producing multiple short videos:
1. Generate multiple scripts in parallel (Script Agent × N)
2. Share art style across batch (consistency)
3. Generate storyboards in parallel
4. Batch voiceover generation
5. Batch media assembly

## Integration with Our System

- **Plan Protocol**: Each agent = one plan step with `tool_name` mapping
- **Approval**: Art style and script require approval before production
- **Effect**: Final media generation is an effect (idempotency_key per video)
- **Checkpoint**: Each agent's output is a checkpoint artifact
- **Memory**: Character bibles and art styles persist across videos
