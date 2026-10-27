import Svg, { Circle, Path, Rect } from "react-native-svg";

// Stroke icons from the "Bankr Mobile" design (and the web app's ViewSwitcher).
const ICONS = {
  menu: <Path d="M4 7h16M4 12h16M4 17h10" />,
  bell: (
    <>
      <Path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z" />
      <Path d="M10 20.5a2 2 0 0 0 4 0" />
    </>
  ),
  send: <Path d="M12 19V5M6 11l6-6 6 6" />,
  stop: <Rect x="7" y="7" width="10" height="10" rx="2" />,
  mic: (
    <>
      <Rect x="9" y="3" width="6" height="11" rx="3" />
      <Path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </>
  ),
  refresh: <Path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" />,
  settings: (
    <>
      <Path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
      <Circle cx="12" cy="12" r="3" />
    </>
  ),
  close: <Path d="M18 6 6 18M6 6l12 12" />,
  search: (
    <>
      <Circle cx="11" cy="11" r="6.5" />
      <Path d="m16 16 4 4" />
    </>
  ),
  chevronLeft: <Path d="m15 6-6 6 6 6" />,
  chevronRight: <Path d="m9 6 6 6-6 6" />,
  check: <Path d="m5 12 5 5 9-10" />,
  chat: <Path d="M4 5h16v11H9l-5 4V5Z" />,
  list: (
    <>
      <Path d="M8 6h12M8 12h12M8 18h12" />
      <Circle cx="4" cy="6" r="1" />
      <Circle cx="4" cy="12" r="1" />
      <Circle cx="4" cy="18" r="1" />
    </>
  ),
  flow: <Path d="M3 6c8 0 8 6 18 6M3 6c8 0 8 12 18 12M3 6c8 0 10-2 18-2" />,
  pulse: <Path d="M3 12h4l2-6 3 12 2-6h7" />,
  sparkle: (
    <>
      <Path d="M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7-4.7-1.8 4.7-1.8z" />
      <Path d="M19 15l.8 2.2 2.2.8-2.2.8L19 21l-.8-2.2-2.2-.8 2.2-.8z" />
    </>
  ),
  warning: (
    <>
      <Path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
      <Path d="M12 9v4M12 17h.01" />
    </>
  ),
  target: (
    <>
      <Circle cx="12" cy="12" r="8" />
      <Circle cx="12" cy="12" r="3.5" />
    </>
  ),
  calendar: (
    <>
      <Rect x="4" y="5" width="16" height="15" rx="2" />
      <Path d="M4 10h16M9 3v4M15 3v4" />
    </>
  ),
} as const;

export type IconName = keyof typeof ICONS;

export function Icon({ name, color, size = 20 }: { name: IconName; color: string; size?: number }) {
  return (
    <Svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={name === "send" ? 2 : 1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {ICONS[name]}
    </Svg>
  );
}
