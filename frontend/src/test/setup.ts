import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(window, 'ResizeObserver', { value: ResizeObserverMock, writable: true });
Object.defineProperty(globalThis, 'ResizeObserver', { value: ResizeObserverMock, writable: true });
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

vi.mock('maplibre-gl', () => {
  class MapMock {
    addControl = vi.fn();
    on = vi.fn();
    remove = vi.fn();
    isStyleLoaded = vi.fn(() => true);
    getSource = vi.fn(() => ({ setData: vi.fn() }));
    setPaintProperty = vi.fn();
    getCanvas = vi.fn(() => ({ style: { cursor: '' } }));
  }
  class NavigationControlMock {}
  class PopupMock {
    setLngLat() { return this; }
    setHTML() { return this; }
    addTo() { return this; }
    remove() { return this; }
  }
  return { Map: MapMock, NavigationControl: NavigationControlMock, Popup: PopupMock, setWorkerUrl: vi.fn() };
});

vi.mock('echarts/core', () => ({
  use: vi.fn(),
  init: vi.fn(() => ({ setOption: vi.fn(), on: vi.fn(), resize: vi.fn(), dispose: vi.fn() })),
}));
vi.mock('echarts/charts', () => ({ LineChart: {}, BarChart: {} }));
vi.mock('echarts/components', () => ({ GridComponent: {}, MarkLineComponent: {}, TooltipComponent: {} }));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));
