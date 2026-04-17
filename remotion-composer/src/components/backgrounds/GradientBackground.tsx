import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

interface GradientBackgroundProps {
  colors?: [string, string, string?];
  angleDegrees?: number;
  rotateSpeed?: number;
  pulse?: boolean;
}

export const GradientBackground: React.FC<GradientBackgroundProps> = ({
  colors = ["#0F172A", "#1E1B4B", "#312E81"],
  angleDegrees = 135,
  rotateSpeed = 0.15,
  pulse = true,
}) => {
  const frame = useCurrentFrame();

  const angle = angleDegrees + frame * rotateSpeed;
  const intensity = pulse
    ? interpolate(
        Math.sin(frame / 45),
        [-1, 1],
        [0.85, 1],
      )
    : 1;

  const stops = colors.filter(Boolean).join(", ");

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(${angle}deg, ${stops})`,
        opacity: intensity,
      }}
    />
  );
};
