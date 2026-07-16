import { afterEach } from 'vitest'

import { setRuntimeI18nLocale } from '@/i18n/runtime'

function createMemoryStorage(): Storage {
  const values = new Map<string, string>()

  return {
    get length() {
      return values.size
    },
    clear() {
      values.clear()
    },
    getItem(key) {
      return values.get(String(key)) ?? null
    },
    key(index) {
      return [...values.keys()][index] ?? null
    },
    removeItem(key) {
      values.delete(String(key))
    },
    setItem(key, value) {
      values.set(String(key), String(value))
    }
  }
}

function installStorage(name: 'localStorage' | 'sessionStorage') {
  const storage = createMemoryStorage()

  Object.defineProperty(window, name, {
    configurable: true,
    value: storage
  })
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value: storage
  })
}

// Node 26 exposes storage globals backed by --localstorage-file. Those
// accessors can replace jsdom's in-memory implementation with `undefined` or
// throw before a test starts. Renderer tests need browser-scoped, hermetic
// storage regardless of the host Node version.
installStorage('localStorage')
installStorage('sessionStorage')

// jsdom does not implement CSS.escape, while Chromium does. Keep selectors in
// component tests aligned with the browser API without weakening production
// code paths that rely on escaped message ids.
if (typeof globalThis.CSS === 'undefined') {
  Object.defineProperty(globalThis, 'CSS', {
    configurable: true,
    value: {
      escape: (value: string) => String(value).replaceAll(/[^a-zA-Z0-9_-]/g, character => `\\${character}`)
    }
  })
} else if (typeof globalThis.CSS.escape !== 'function') {
  globalThis.CSS.escape = value => String(value).replaceAll(/[^a-zA-Z0-9_-]/g, character => `\\${character}`)
}

// Product installs default to Chinese, while the inherited component suite
// asserts its original English copy unless a test explicitly selects another
// locale. Pin the test runtime before component modules are imported so a UI
// locale change does not turn unrelated behavior tests into copy failures.
setRuntimeI18nLocale('en')

afterEach(() => {
  setRuntimeI18nLocale('en')
})
