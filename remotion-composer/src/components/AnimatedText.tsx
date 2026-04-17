import {
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type SplitMode = "char" | "word" | "line";
type EntryMode = "fade" | "slide-up" | "slide-down" | "scale";

interface AnimatedTextProps {
  text: string;
  split?: SplitMode;
  entry?: EntryMode;
  staggerFrames?: number;
  startFrame?: number;
  fontFamily?: string;
  fontSize?: number;
  fontWeight?: number;
  color?: string;
  lineHeight?: number;
  letterSpacing?: string;
  textAlign?: "left" | "center" | "right";
  textTransform?: "none" | "uppercase" | "lowercase" | "capitalize";
  accentColor?: string;
  accentCount?: number;
  maxWidth?: number | string;
}

export const AnimatedText: React.FC<AnimatedTextProps> = ({
  text,
  split = "word",
  entry = "slide-up",
  staggerFrames = 2,
  startFrame = 0,
  fontFamily = "Inter, system-ui, sans-serif",
  fontSize = 56,
  fontWeight = 700,
  color = "#F8FAFC",
  lineHeight = 1.25,
  letterSpacing,
  textAlign = "center",
  textTransform,
  accentColor,
  accentCount = 0,
  maxWidth = "85%",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const tokens =
    split === "char"
      ? text.split("")
      : split === "word"
        ? text.split(" ")
        : text.split("\n");

  const gap = split === "char" ? 0 : split === "word" ? "0.28em" : 0;

  return (
    <div
      style={{
        fontFamily,
        fontSize,
        fontWeight,
        color,
        lineHeight,
        letterSpacing,
        textAlign,
        textTransform,
        maxWidth,
        display: "flex",
        flexWrap: "wrap",
        justifyContent:
          textAlign === "center"
            ? "center"
            : textAlign === "right"
              ? "flex-end"
              : "flex-start",
        gap,
        flexDirection: split === "line" ? "column" : "row",
      }}
    >
      {tokens.map((token, i) => {
        const localFrame = frame - startFrame - i * staggerFrames;
        const progress = spring({
          frame: localFrame,
          fps,
          config: { damping: 14, stiffness: 140 },
        });

        let transform = "none";
        if (entry === "slide-up") {
          transform = `translateY(${interpolate(progress, [0, 1], [30, 0])}px)`;
        } else if (entry === "slide-down") {
          transform = `translateY(${interpolate(progress, [0, 1], [-30, 0])}px)`;
        } else if (entry === "scale") {
          transform = `scale(${interpolate(progress, [0, 1], [0.7, 1])})`;
        }

        const isAccent = accentCount > 0 && i < accentCount;

        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              opacity: progress,
              transform,
              color: isAccent && accentColor ? accentColor : undefined,
              whiteSpace: token === " " ? "pre" : undefined,
            }}
          >
            {token}
            {split === "char" && token === " " ? "\u00A0" : null}
          </span>
        );
      })}
    </div>
  );
};
