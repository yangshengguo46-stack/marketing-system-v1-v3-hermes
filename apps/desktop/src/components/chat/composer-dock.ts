import { cn } from '@/lib/utils'

/**
 * The composer surface and the status/queue stack paint ONE shared
 * `--composer-fill` var. The state ladder (rest / scrolled) lives in styles.css
 * on `[data-slot='composer-root']`, so the layers can never disagree.
 */
export const composerFill = 'bg-(--composer-fill)'

/** Backdrop treatment for the composer input surface. Harmless when the fill
 *  goes opaque (drawer open) — nothing shows through to blur. */
export const composerSurfaceGlass = cn(
  'backdrop-blur-[0.75rem] backdrop-saturate-[1.12] [-webkit-backdrop-filter:blur(0.75rem)_saturate(1.12)]',
  'transition-[background-color] duration-150 ease-out'
)

/** Shared frame for every first-party composer surface. Workbench composers
 * use this too, so their density, border and glass treatment cannot drift from
 * the main conversation composer. */
export const composerSurfaceFrame = cn(
  'group/composer-surface relative z-4 isolate grid grid-rows-[auto_1fr] overflow-hidden rounded-[inherit]',
  'border border-[color-mix(in_srgb,var(--dt-composer-ring)_calc(18%*var(--composer-ring-strength)),var(--dt-input))]'
)

/** Shared inner spacing and row behavior for composer content. */
export const composerSurfaceContent =
  'relative z-1 flex min-h-0 w-full flex-col gap-(--composer-row-gap) overflow-hidden rounded-[inherit] px-(--composer-surface-pad-x) py-(--composer-surface-pad-y)'

const composerDockEdge = (edge: 'bottom' | 'top') =>
  cn('border border-border/65', edge === 'top' ? 'rounded-t-2xl border-b-0' : 'rounded-b-2xl border-t-0')

/** Glassy docked card — the status stack / queue. Paints the SAME
 *  `--composer-fill` as the surface, so rest / scrolled / focused / drawer-open
 *  all match the composer by construction. */
export const composerDockCard = (edge: 'bottom' | 'top' = 'top') =>
  cn(composerDockEdge(edge), composerFill, composerSurfaceGlass)

/** Floating composer panel skin — the `/`·`@`·`?` completion drawer and the
 *  attach (`+`) menu. Glassy translucent card, hairline border, full radius,
 *  smallest type, soft nous shadow. Uses an explicit fill (not `--composer-fill`)
 *  so it renders identically whether mounted inside the composer or portaled out
 *  of it. Visual skin only — consumers add their own size/position/padding. */
export const composerPanelCard = cn(
  'rounded-2xl border border-border/65 shadow-nous text-[length:var(--conversation-tool-font-size)]',
  'bg-[color-mix(in_srgb,var(--dt-card)_72%,transparent)]',
  composerSurfaceGlass
)
