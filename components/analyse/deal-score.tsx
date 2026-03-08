"use client"

interface DealScoreProps {
  score: number
}

function getScoreColor(score: number): string {
  if (score >= 75) return "oklch(0.7 0.17 155)"  // green
  if (score >= 50) return "oklch(0.75 0.15 190)"  // teal/primary
  if (score >= 25) return "oklch(0.78 0.15 85)"   // amber
  return "oklch(0.55 0.2 25)"                      // red
}

function getScoreLabel(score: number): string {
  if (score >= 80) return "Excellent Deal"
  if (score >= 65) return "Good Deal"
  if (score >= 50) return "Fair Deal"
  if (score >= 35) return "Below Average"
  return "Poor Deal"
}

export function DealScore({ score }: DealScoreProps) {
  const color = getScoreColor(score)
  const label = getScoreLabel(score)

  // Full circle progress ring
  const size = 160
  const strokeWidth = 14
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const progress = (score / 100) * circumference
  const cx = size / 2
  const cy = size / 2

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Ring + centered text overlay */}
      <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
        {/* SVG rotated so progress starts at 12 o'clock */}
        <svg
          width={size}
          height={size}
          style={{ transform: "rotate(-90deg)" }}
          className="absolute inset-0"
        >
          {/* Background track */}
          <circle
            cx={cx}
            cy={cy}
            r={radius}
            fill="none"
            stroke="oklch(0.2 0.015 260)"
            strokeWidth={strokeWidth}
          />
          {/* Green progress arc */}
          <circle
            cx={cx}
            cy={cy}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={`${progress} ${circumference}`}
            className="transition-all duration-1000 ease-out"
          />
        </svg>

        {/* Centered score text (not rotated) */}
        <div className="absolute flex flex-col items-center leading-none">
          <span className="text-3xl font-bold" style={{ color }}>
            {score}%
          </span>
          <span className="mt-1 text-[11px] text-muted-foreground">/100</span>
        </div>
      </div>

      {/* Label below the ring */}
      <span className="text-sm font-semibold" style={{ color }}>
        {label}
      </span>
    </div>
  )
}
