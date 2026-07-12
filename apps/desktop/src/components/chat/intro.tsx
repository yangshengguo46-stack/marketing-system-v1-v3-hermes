import { BrandMark } from '@/components/brand-mark'

export type IntroProps = {
  personality?: string
  seed?: number
}

/**
 * Product-owned empty conversation state.
 *
 * Hermes still owns the Agent loop underneath, but a Marketing OS user should
 * never be greeted by repository/developer copy or an upstream wordmark.
 */
export function Intro(_props: IntroProps) {
  return (
    <div
      className="pointer-events-none flex w-full min-w-0 flex-col items-center justify-center px-6 py-10 text-center"
      data-slot="aui_intro"
    >
      <BrandMark className="size-14 text-[2.8rem] shadow-[0_16px_45px_rgba(239,91,85,0.2)]" />
      <p className="mt-6 text-[0.66rem] font-semibold uppercase tracking-[0.24em] text-(--ui-text-tertiary)">
        Marketing Agent
      </p>
      <h1 className="mt-3 text-[2rem] font-semibold tracking-[-0.045em] text-foreground">今天想把哪个账号往前推？</h1>
      <p className="mt-3 max-w-xl text-sm leading-7 text-(--ui-text-secondary)">
        直接说目标、困惑或一个模糊想法。没有账号、没有定位也没关系，我会先理解你，再决定该查数据、做研究还是开始创作。
      </p>
      <div className="mt-8 grid w-full max-w-2xl gap-2 text-left sm:grid-cols-3">
        {['分析今天适合做什么内容', '从零完成一次账号定位', '检查现有内容是否值得发布'].map(item => (
          <span
            className="rounded-2xl border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) px-4 py-3 text-xs text-(--ui-text-secondary)"
            key={item}
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  )
}
