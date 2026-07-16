import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Intro } from './intro'

describe('conversation intro', () => {
  it('submits each visible starter through the provided action pipeline', () => {
    const onAction = vi.fn()

    render(<Intro onAction={onAction} />)
    fireEvent.click(screen.getByRole('button', { name: '分析今天适合做什么内容' }))

    expect(onAction).toHaveBeenCalledWith('分析今天适合做什么内容')
  })
})
