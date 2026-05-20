"use client";

const COLOR_MAP: Record<string, string> = {
  green: "#27ae60",
  yellow: "#e2a03f",
  orange: "#e67e22",
  gray: "#8e99a0",
};

interface MatchRingProps {
  score: number;
  color: string;
  size?: number;
}

export function MatchRing({ score, color, size = 60 }: MatchRingProps) {
  const stroke = COLOR_MAP[color] || COLOR_MAP.gray;
  const r = 22;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;

  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        boxShadow: "var(--neu-raised)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--neu-bg)",
        flexShrink: 0,
      }}
    >
      <svg width={size - 8} height={size - 8} viewBox="0 0 52 52">
        <circle cx="26" cy="26" r={r} fill="none" stroke="var(--neu-bg-2)" strokeWidth="4" />
        <circle
          cx="26"
          cy="26"
          r={r}
          fill="none"
          stroke={stroke}
          strokeWidth="4"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 26 26)"
        />
        <text
          x="26"
          y="28"
          textAnchor="middle"
          fontSize="13"
          fontWeight="600"
          fontFamily="var(--jp-mono)"
          fill="var(--jp-ink)"
        >
          {score}
        </text>
      </svg>
    </div>
  );
}
