// Node 22 registers an experimental (broken) localStorage accessor on globalThis
// before vitest's jsdom environment can populate it. The result is that
// global.localStorage === undefined even though jsdom.window.localStorage works.
// This setup file copies the real Storage instances from the jsdom window.

const g = globalThis as Record<string, unknown>;
const jsdomWin = (g.jsdom as Record<string, unknown> | undefined)?.window as
  | Record<string, unknown>
  | undefined;

if (jsdomWin) {
  Object.defineProperty(globalThis, "localStorage", {
    value: jsdomWin.localStorage,
    writable: true,
    configurable: true,
    enumerable: false,
  });
  Object.defineProperty(globalThis, "sessionStorage", {
    value: jsdomWin.sessionStorage,
    writable: true,
    configurable: true,
    enumerable: false,
  });
}
