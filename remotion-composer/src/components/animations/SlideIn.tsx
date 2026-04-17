import { ReactNode } from "react";
import {
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type Direction = "up" | "down" | "left" | "right";

interface SlideInProps {
  children: ReactNode;
  from?: Direction;
  distance?: number;
  startFrame?: number;
  damping?: number;
  stiffness?: number;
  fade?: boolean;
  style?: React.CSSProperties;
}

export const SlideIn: React.FC<SlideInProps> = ({
  children,
  from = "up",
  distance = 60,
  startFrame = 0,
  damping = 14,
  stiffness = 120,
  fade = true,
  style,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({
    frame: frame - startFrame,
    fps,
    config: { damping, stiffness },
  });

  const axis = from === "up" || from === "down" ? "Y" : "X";
  const sign = from === "up" || from === "left" ? 1 : -1;
  const offset = interpolate(progress, [0, 1], [distance * sign, 0]);

  return (
    <div
      style={{
        ...style,
        transform: `translate${axis}(${offset}px)`,
        opacity: fade ? progress : 1,
      }}
    >
      {children}
    </div>
  );
};
