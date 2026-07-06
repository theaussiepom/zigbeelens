/**
 * jsdom shims required by @xyflow/react, based on the React Flow testing
 * guide. jsdom implements neither ResizeObserver nor DOMMatrixReadOnly, and
 * elements report zero dimensions; these mocks let React Flow measure and
 * render nodes/edges under Vitest.
 */

class ResizeObserverMock {
  callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }

  observe(target: Element) {
    this.callback([{ target } as ResizeObserverEntry], this as unknown as ResizeObserver);
  }

  unobserve() {}
  disconnect() {}
}

class DOMMatrixReadOnlyMock {
  m22: number;

  constructor(transform?: string) {
    const scale = transform?.match(/scale\(([1-9.]+)\)/)?.[1];
    this.m22 = scale !== undefined ? +scale : 1;
  }
}

let initialized = false;

export function mockReactFlow() {
  if (initialized) return;
  initialized = true;

  globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;
  // @ts-expect-error - minimal stub for jsdom
  globalThis.DOMMatrixReadOnly = DOMMatrixReadOnlyMock;

  Object.defineProperties(globalThis.HTMLElement.prototype, {
    offsetHeight: {
      get() {
        return parseFloat((this as HTMLElement).style.height) || 1;
      },
    },
    offsetWidth: {
      get() {
        return parseFloat((this as HTMLElement).style.width) || 1;
      },
    },
  });

  (globalThis.SVGElement.prototype as unknown as { getBBox: () => DOMRect }).getBBox = () =>
    ({ x: 0, y: 0, width: 0, height: 0 }) as DOMRect;
}
