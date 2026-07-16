export type IntroProps = {
  onAction?: (prompt: string) => void
  personality?: string
  seed?: number
}

const STARTER_ACTIONS = ['分析今天适合做什么内容', '从零完成一次账号定位', '检查现有内容是否值得发布'] as const

/**
 * Product-owned empty conversation state.
 *
 * Hermes still owns the Agent loop underneath, but a Marketing OS user should
 * never be greeted by repository/developer copy or an upstream wordmark.
 */
export function Intro({ onAction }: IntroProps) {
  return (
    <div
      className="flex w-full min-w-0 flex-col items-center justify-center px-6 py-10 text-center"
      data-slot="aui_intro"
    >
      <h1 className="text-[1.75rem] font-semibold tracking-[-0.045em] text-foreground">今天想把哪个账号往前推？</h1>
      <p className="mt-3 max-w-xl text-sm leading-7 text-(--ui-text-secondary)">
        直接说目标、困惑或一个模糊想法。没有账号、没有定位也没关系，我会先理解你，再决定该查数据、做研究还是开始创作。
      </p>
      <div className="mt-8 w-full max-w-lg divide-y divide-(--ui-stroke-quaternary) border-y border-(--ui-stroke-tertiary) text-left">
        {STARTER_ACTIONS.map(item => (
          <button
            className="block w-full px-3 py-3.5 text-left text-xs text-(--ui-text-secondary) transition-colors duration-[var(--mos-motion-fast)] hover:bg-(--ui-row-hover-background) hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-(--ui-accent)"
            key={item}
            onClick={() => onAction?.(item)}
            type="button"
          >
            {item}
          </button>
        ))}
      </div>
    </div>
  )
}
