import { cn } from '@/lib/utils'
import { PRODUCT_NAME } from '@/product'

// Product-owned mark. Marketing OS Desktop is the fork itself, not a second
// shell around an upstream Hermes avatar.
export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      aria-label={PRODUCT_NAME}
      className={cn(
        'inline-flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-[28%] bg-[#ff5b55] text-[0.42em] font-black tracking-[-0.08em] text-white shadow-[0_12px_30px_rgba(255,91,85,0.24)]',
        className
      )}
      {...props}
    >
      M
    </span>
  )
}
