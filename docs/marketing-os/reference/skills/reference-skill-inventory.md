# Reference Skill Inventory

> Audited: 2026-07-13
> Scope: user-supplied marketing playbooks and locally installed content skills

## Decision

All 36 identified reference modules are now source-controlled. They are not
all converted into tools, because that would erase the boundary between
operating knowledge and stateful execution:

- Skills own methods, checklists, writing frameworks, and review criteria.
- Native Hermes tools own account-scoped reads and writes, browser work,
  evidence capture, drafts, publishing, metrics, receipts, and governed
  learning.
- A native tool with functional overlap does not replace the original Skill.
- Electron owns neither Skills nor tools; it only renders state and collects
  user input or confirmation.

The exact 23-module `marketing-skills` version `0.1.2` snapshot is preserved at
`skills/marketing-playbooks/`. The 13 modules that existed only in the local
installed runtime are preserved under `skills/content-creation/`,
`skills/screenwriting/`, and `skills/video-production/`.

The broader video tool evaluation, executable experiments, license boundaries,
and frozen faceless-video pipeline are recorded in
[`video-pipeline-evaluation.md`](video-pipeline-evaluation.md).

## Marketing Playbooks

| Module | Product disposition | Native overlap or boundary |
|---|---|---|
| `ab-test-setup` | Skill retained; partially native | Account experiments, variants, assets, receipts, metrics, and retro are native Hermes facts. |
| `analytics-tracking` | Skill retained; partially native | Social publish metrics and provenance are native; GA4/GTM website tracking is outside the current product lane. |
| `competitor-alternatives` | Skill retained; partially native | Benchmark accounts and observations are native; SEO comparison-page production is not. |
| `copy-editing` | Skill retained; partially native | Content quality gates and rubric facts are native; editorial method remains a Skill. |
| `copywriting` | Skill retained; partially native | Draft and variant assets are native; writing method remains a Skill. |
| `email-sequence` | Skill retained; outside current lane | No email campaign account or delivery owner exists yet. |
| `form-cro` | Skill retained; outside current lane | Website form conversion is not part of the current social-account loop. |
| `free-tool-strategy` | Skill retained; reference-only | Useful growth method, but no free-tool product owner is planned. |
| `launch-strategy` | Skill retained; reference-only | Can guide a campaign, but no launch state machine should be invented yet. |
| `marketing-ideas` | Skill retained; reference-only | Idea generation may feed a content plan; it must not write account truth. |
| `marketing-psychology` | Skill retained; partially native | Observable content principles exist in Content KB; the full method remains a Skill. |
| `onboarding-cro` | Skill retained; outside current lane | Product onboarding optimization is not a social publishing capability. |
| `page-cro` | Skill retained; outside current lane | Marketing-page conversion is outside the current product lane. |
| `paid-ads` | Skill retained; deferred | No ad-account identity, spend, campaign, or receipt owner exists. |
| `paywall-upgrade-cro` | Skill retained; outside current lane | In-product monetization UX is outside the current product lane. |
| `popup-cro` | Skill retained; outside current lane | Website popup conversion is outside the current product lane. |
| `pricing-strategy` | Skill retained; reference-only | Business strategy knowledge only; it must not become an ungoverned stateful tool. |
| `programmatic-seo` | Skill retained; outside current lane | Website generation and search indexing are not current owners. |
| `referral-program` | Skill retained; deferred | No referral identity, reward, or attribution owner exists. |
| `schema-markup` | Skill retained; outside current lane | Website structured data is outside the current product lane. |
| `seo-audit` | Skill retained; outside current lane | Website search diagnostics are outside the current product lane. |
| `signup-flow-cro` | Skill retained; outside current lane | Product registration optimization is outside the social-account loop. |
| `social-content` | Skill retained; substantially native | Account context, evidence, plans, assets, platform variants, preflight, publish, and learning are native; creative method remains a Skill. |

## Content, Story, And Video Skills

| Group | Modules | Product disposition |
|---|---|---|
| Content creation | `content-analysis`, `platform-content-adapter`, `short-video-script`, `viral-title-writer` | Active reference methods for `article_soft` and `faceless_video`; account facts and resulting assets still go through native tools. |
| Screenwriting | `character-bible`, `dialogue-craft`, `mckee-story-analysis`, `save-the-cat-beats`, `story-structure-router` | Available when a content brief needs narrative structure; no separate screenplay database or workflow is introduced. |
| Video production | `director-pipeline`, `shot-design`, `storyboard-creator`, `voiceover-planner` | May guide the internal faceless-video lane. Advanced video execution remains owned by the separate Video Studio product. |

## Product Skill

`skills/operate-social-platforms/` is the current Marketing OS-specific runtime
Skill. It defines account-scoped browser operation, real login verification,
creator data collection, draft/publish discipline, stable post verification,
and unknown-outcome handling. It complements the reference modules rather than
replacing them.

## Upgrade Rule

The preserved marketing bundle is an input snapshot, not a floating
dependency. Upstream changes must be reviewed module by module before an
upgrade. A newer upstream version must never silently rename Skills, widen
product scope, or create new native tools.
