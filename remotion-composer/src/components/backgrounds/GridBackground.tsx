import { AbsoluteFill, useCurrentFrame } from "remotion";

interface GridBackgroundProps {
  cellSize?: number;
  lineColor?: string;
  lineWidth?: number;
  backgroundColor?: string;
  scrollSpeed?: number;
  dotMode?: boolean;
  vignette?: boolean;
}

export const GridBackground: React.FC<GridBackgroundProps> = ({
  cellSize = 80,
  lineColor = "rgba(148, 163, 184, 0.18)",
  lineWidth = 1,
  backgroundColor = "#0B1120",
  scrollSpeed = 0.5,
  dotMode = false,
  vignette = true,
}) => {
  const frame = useCurrentFrame();
  const offset = (frame * scrollSpeed) % cellSize;

  const pattern = dotMode
    ? {
        backgroundImage: `radial-gradient(circle, ${lineColor} ${lineWidth}px, transparent ${lineWidth}px)`,
        backgroundSize: `${cellSize}px ${cellSize}px`,
      }
    : {
        backgroundImage: `linear-gradient(${lineColor} ${lineWidth}px, transparent ${lineWidth}px), linear-gradient(90deg, ${lineColor} ${lineWidth}px, transparent ${lineWidth}px)`,
        backgroundSize: `${cellSize}px ${cellSize}px`,
      };

  return (
    <AbsoluteFill style={{ backgroundColor }}>
      <AbsoluteFill
        style={{
          ...pattern,
          backgroundPosition: `${offset}px ${offset}px`,
        }}
      />
      {vignette && (
        <AbsoluteFill
          style={{
            background:
              "radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.55) 100%)",
          }}
        />
      )}
    </AbsoluteFill>
  );
};
