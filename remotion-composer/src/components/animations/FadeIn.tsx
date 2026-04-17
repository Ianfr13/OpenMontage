import { ReactNode } from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";

interface FadeInProps {
  children: ReactNode;
  startFrame?: number;
  durationFrames?: number;
  exitFrame?: number;
  exitDurationFrames?: number;
  style?: React.CSSProperties;
}

export const FadeIn: React.FC<FadeInProps> = ({
  children,
  startFrame = 0,
  durationFrames = 20,
  exitFrame,
  exitDurationFrames = 15,
  style,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({
    frame: frame - startFrame,
    fps,
    durationInFrames: durationFrames,
    config: { damping: 20 },
  });

  const exit =
    exitFrame !== undefined
      ? 1 -
        spring({
          frame: frame - exitFrame,
          fps,
          durationInFrames: exitDurationFrames,
          config: { damping: 20 },
        })
      : 1;

  return <div style={{ ...style, opacity: enter * exit }}>{children}</div>;
};
