---
name: story-structure-router
description: Route a story request to the right structural framework based on intent, medium, and stage. Supports three-act, Hero's Journey, Save the Cat, Story Circle, kishotenketsu, and 8-sequence. Use before any writing to select the optimal story structure.
---

# Story Structure Router

## When to Use
- Starting a new writing project (select the right structure first)
- Evaluating which framework fits a specific content type
- Switching structures mid-project (diagnose why the current one isn't working)

## Routing Matrix

### By Intent

| Intent | Recommended Structure | Why |
|--------|----------------------|-----|
| Brand storytelling | Save the Cat (compressed) | Clear transformation arc, product as catalyst |
| Educational content | Kishōtenketsu | No conflict needed, discovery-based |
| Entertainment short | Hero's Journey (mini) | Familiar, satisfying arc in 60-90 seconds |
| Documentary/exposé | 8-Sequence | Allows layered investigation |
| Personal essay | Story Circle (Dan Harmon) | Simple, relatable, cyclical |
| Series episode | Three-Act + B-story | Sustains across episodes |

### By Medium

| Medium | Structure | Beat Count | Notes |
|--------|-----------|------------|-------|
| 60s short video | Compressed 7-beat | 7 | Hook(3s)→Problem→Catalyst→Try→Fail→Epiphany→Resolution |
| 3-5 min video | Save the Cat mini | 10 | Merge Debate+Break, merge Dark Night+Break Three |
| 10-15 min video | Full Save the Cat | 15 | All beats, proportional timing |
| Long-form video | Hero's Journey | 12 | Campbell's monomyth, allows world-building |
| Image+text post | Story Circle | 8 | Harmon's circle, very compact |
| Article/blog | 8-Sequence | 8 | Classic TV structure, works for text |
| Series (multi-ep) | Three-Act per ep + Season arc | 3+3 | Each episode has a mini-arc, season has a macro-arc |

### By Stage

| Stage | What to Do |
|-------|------------|
| Ideation | Pick structure → write logline → identify protagonist's "before" and "after" |
| Outline | Fill beat sheet → identify weak beats → plan B-story |
| Drafting | Write beat by beat → don't skip ahead → track character state |
| Revision | Audit beats → flag missing beats → check pacing → verify theme |
| Polish | Dialogue pass → subtext audit → cut redundant beats |

## Framework Details

### Three-Act Structure
```
Act 1 (25%): Setup → Inciting Incident → Turning Point
Act 2 (50%): Rising Action → Midpoint → Crisis
Act 3 (25%): Climax → Resolution
```
Best for: Traditional narratives, features, pilot episodes

### Hero's Journey (Campbell/Vogler)
```
1. Ordinary World    7. Approach
2. Call to Adventure 8. Ordeal
3. Refusal of Call    9. Reward
4. Meeting Mentor    10. Road Back
5. Crossing Threshold 11. Resurrection
6. Tests/Allies/Enemies 12. Return with Elixir
```
Best for: Adventure stories, brand origin stories, transformation content

### Save the Cat (Snyder)
See the `save-the-cat-beats` skill for full 15-beat breakdown.
Best for: Screenplays, marketing videos, structured short content

### Story Circle (Dan Harmon)
```
1. You (a character in a comfort zone)
2. Need (but they want something)
3. Go (they enter an unfamiliar situation)
4. Search (adapt to it)
5. Find (get what they wanted)
6. Take (pay a heavy price)
7. Return (return to their familiar situation)
8. Change (they have changed)
```
Best for: Short-form content, personal essays, comedy sketches

### Kishōtenketsu (起承転結)
```
起 (Ki): Introduction — establish the setting
承 (Shō): Development — build on the introduction
転 (Ten): Twist — unexpected turn or new element
結 (Ketsu): Conclusion — bring it all together
```
Best for: Educational content, slice-of-life, non-conflict narratives, Asian audience content

### 8-Sequence Approach
```
1. Setup (10-15%)     5. First Obstacle (10-15%)
2. Inciting (10%)     6. Midpoint Turn (10%)
3. Progress (10%)     7. Complications (10%)
4. Commitment (10%)   8. Resolution (15-20%)
```
Best for: TV episodes, long-form articles, documentary structure

## Decision Flow

```
1. What is the intent? → narrows to 2-3 frameworks
2. What is the medium? → narrows to 1-2 frameworks
3. What is the target length? → determines beat count
4. Who is the audience? → may swap framework (e.g., kishōtenketsu for Asian audiences)
5. Is this part of a series? → add season-level structure
```

## Output

After routing, produce:
1. **Selected framework** — name and rationale
2. **Beat count** — adjusted for medium/length
3. **Beat sheet template** — pre-filled with framework's beats
4. **Customization notes** — any adaptations for the specific project
