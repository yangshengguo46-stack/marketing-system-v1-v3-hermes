const TECHNICAL_ERROR =
  /unknown method|method not found|gateway|bridge|ipc|provider|cookie|econn|websocket|traceback|stack|[a-z]+(?:\.[a-z_]+){2,}|[a-z]+_[a-z_]+/i

export function userFacingError(cause: unknown, fallback: string): string {
  const message = cause instanceof Error ? cause.message.trim() : typeof cause === 'string' ? cause.trim() : ''

  if (!message || message.length > 100 || TECHNICAL_ERROR.test(message)) {
    return fallback
  }

  return message
}
