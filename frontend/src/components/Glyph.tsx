/**
 * The whole icon set — drawn as 1.5px strokes, geometric, no icon soup.
 */
import type { DeviceType } from "../api/types";

type P = { size?: number; className?: string };
const S = ({
  size = 14,
  className,
  children,
}: P & { children: React.ReactNode }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.5}
    strokeLinecap="square"
    strokeLinejoin="miter"
    className={className}
    aria-hidden="true"
  >
    {children}
  </svg>
);

export const ArrowRight = (p: P) => (
  <S {...p}>
    <path d="M2 8h11M9 4l4 4-4 4" />
  </S>
);
export const ArrowLeft = (p: P) => (
  <S {...p}>
    <path d="M14 8H3M7 4L3 8l4 4" />
  </S>
);
export const ArrowUpRight = (p: P) => (
  <S {...p}>
    <path d="M4 12L12 4M5 4h7v7" />
  </S>
);
export const Chevron = (p: P) => (
  <S {...p}>
    <path d="M6 3l5 5-5 5" />
  </S>
);
export const Close = (p: P) => (
  <S {...p}>
    <path d="M3 3l10 10M13 3L3 13" />
  </S>
);
export const Plus = (p: P) => (
  <S {...p}>
    <path d="M8 2v12M2 8h12" />
  </S>
);
export const Check = (p: P) => (
  <S {...p}>
    <path d="M2 8.5l4 4 8-9" />
  </S>
);
export const Trash = (p: P) => (
  <S {...p}>
    <path d="M2.5 4h11M6 4V2.5h4V4M4 4l.7 9.5h6.6L12 4" />
  </S>
);
export const Merge = (p: P) => (
  <S {...p}>
    <path d="M4 2v4l4 4 4-4V2M8 10v4" />
  </S>
);
export const Send = (p: P) => (
  <S {...p}>
    <path d="M14 2L2 7l5 2 2 5 5-12z" />
  </S>
);
export const Image = (p: P) => (
  <S {...p}>
    <path d="M2 3h12v10H2zM2 11l4-4 3 3 2-2 3 3" />
  </S>
);
export const Search = (p: P) => (
  <S {...p}>
    <circle cx="7" cy="7" r="4.5" />
    <path d="M10.5 10.5L14 14" />
  </S>
);
export const CaretDown = (p: P) => (
  <S {...p}>
    <path d="M3 6l5 5 5-5" />
  </S>
);
export const CornerDown = (p: P) => (
  <S {...p}>
    <path d="M4 2v7h9M10 6l3 3-3 3" />
  </S>
);
export const Bell = (p: P) => (
  <S {...p}>
    <path d="M4 12V7a4 4 0 0 1 8 0v5l1.5 1.5h-11L4 12zM6.5 13.5a1.5 1.5 0 0 0 3 0" />
  </S>
);

/* ── bottom-nav icons — filled-block geometry, matches the board ──────── */
export const HostsIcon = (p: P) => (
  <S {...p}>
    <path d="M2 3h12v4H2zM2 9h12v4H2zM4.5 5h.01M4.5 11h.01" />
  </S>
);
export const ReviewIcon = (p: P) => (
  <S {...p}>
    <path d="M8 2l6 3.5v5L8 14 2 10.5v-5zM8 2v12M2 5.5l6 3.5 6-3.5" />
  </S>
);
export const PeopleIcon = (p: P) => (
  <S {...p}>
    <circle cx="6" cy="6" r="2.4" />
    <path d="M2 14c0-2.4 1.8-3.6 4-3.6s4 1.2 4 3.6M10.5 4.2A2.2 2.2 0 0 1 13 8M14 14c0-1.8-1-2.9-2.6-3.3" />
  </S>
);
export const LogIcon = (p: P) => (
  <S {...p}>
    <path d="M3 3h10v10H3zM6 6h5M6 8.5h5M6 11h3" />
  </S>
);
export const ConfigIcon = (p: P) => (
  <S {...p}>
    <path d="M2 4.5h12M2 8h12M2 11.5h12" />
    <path d="M6 4.5V3M11 8V6.5M4.5 11.5V10" />
  </S>
);
export const StatsIcon = (p: P) => (
  <S {...p}>
    <path d="M2 2v12h12M5 11V7M8.5 11V4M12 11V9" />
  </S>
);

/* ── device-type icons — geometric, keyed by DeviceType ──────────────── */
const T: Record<DeviceType, (p: P) => React.ReactElement> = {
  unknown: (p) => <S {...p}><path d="M6 6a2 2 0 1 1 2.6 1.9c-.6.2-1.1.6-1.1 1.6M7.5 12h.01" /></S>,
  router: (p) => <S {...p}><path d="M2 9.5h12v4H2zM4.5 11.5h.01M7 11.5h3M8 9.5V6M8 6l-2.5-2M8 6l2.5-2M8 6V3" /></S>,
  access_point: (p) => <S {...p}><path d="M8 13V7M5.5 13h5M4 6.5a5 5 0 0 1 8 0M6 8a2.7 2.7 0 0 1 4 0" /></S>,
  pc: (p) => <S {...p}><path d="M2 3h12v8H2zM6 14h4M8 11v3" /></S>,
  laptop: (p) => <S {...p}><path d="M3.5 4h9v6h-9zM1.5 12.5h13l-1-2h-11z" /></S>,
  phone: (p) => <S {...p}><path d="M4.5 2h7v12h-7zM7 12h2" /></S>,
  tablet: (p) => <S {...p}><path d="M3 2.5h10v11H3zM7 11.5h2" /></S>,
  tv: (p) => <S {...p}><path d="M2 3.5h12v8H2zM6 14h4M6.5 3.5L8 2l1.5 1.5" /></S>,
  media: (p) => <S {...p}><path d="M2 3.5h12v7H2zM4 13.5c0-2 1.5-3 4-3s4 1 4 3M8 6l3 1.7L8 9.4z" /></S>,
  console: (p) => <S {...p}><path d="M4.5 5h7a3.5 3.5 0 0 1 0 7c-1.3 0-1.8-1-3.5-1s-2.2 1-3.5 1a3.5 3.5 0 0 1 0-7zM6 7v2M5 8h2M10.5 8h.01M9.5 9.5h.01" /></S>,
  printer: (p) => <S {...p}><path d="M4 6V2.5h8V6M4 12H2.5V6h11v6H12M4 9.5h8v4H4z" /></S>,
  nas: (p) => <S {...p}><path d="M2.5 2.5h11v11h-11zM5 5h6M5 8h6M5 11h3" /></S>,
  iot: (p) => <S {...p}><path d="M5 5h6v6H5zM8 5V2.5M8 13.5V11M5 8H2.5M13.5 8H11M11 5l2-2M11 11l2 2M5 5L3 3M5 11l-2 2" /></S>,
  camera: (p) => <S {...p}><path d="M2 4.5l9-1.5v10L2 11.5zM11 6.5l3-1.5v6l-3-1.5" /></S>,
  speaker: (p) => <S {...p}><path d="M4 2.5h8v11H4zM8 6.5h.01M8 10a1.7 1.7 0 1 0 0-.01z" /></S>,
  wearable: (p) => <S {...p}><path d="M5 5h6v6H5zM6 5V2.5h4V5M6 11v2.5h4V11" /></S>,
  server: (p) => <S {...p}><path d="M2.5 2.5h11v5h-11zM2.5 8.5h11v5h-11zM5 5h.01M5 11h.01M8 5h4M8 11h4" /></S>,
  car: (p) => <S {...p}><path d="M2 10.5V8l1.5-3.5h9L14 8v2.5M2 10.5h12v1.5H2zM4.5 8h7M4.5 12v1M11.5 12v1" /><path d="M4.5 8.5h.01M11.5 8.5h.01" /></S>,
};

export function DeviceTypeIcon({ type, size = 14, className }: P & { type: DeviceType }) {
  return (T[type] ?? T.unknown)({ size, className });
}
