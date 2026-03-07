import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import { scoreColor } from '../utils';

interface Props {
  score: number;
  size?: number;
}

export default function Gauge({ score, size = 110 }: Props) {
  const [animatedScore, setAnimatedScore] = useState(0);

  const sw = 7;
  const r = (size - sw * 2) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (animatedScore / 100) * circ;
  const color = scoreColor(score);

  // Animate the score number on mount / score change
  useEffect(() => {
    let start: number | null = null;
    let raf: number;
    const duration = 900;

    const step = (ts: number) => {
      if (start === null) start = ts;
      const progress = Math.min((ts - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setAnimatedScore(Math.round(eased * score));
      if (progress < 1) raf = requestAnimationFrame(step);
    };

    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [score]);

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        style={{ transform: 'rotate(-90deg)' }}
      >
        <circle className="gauge-track" cx={cx} cy={cy} r={r} />
        <motion.circle
          className="gauge-fill"
          cx={cx}
          cy={cy}
          r={r}
          stroke={color}
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 0.9, ease: [0.4, 0, 0.2, 1] }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-extrabold leading-none" style={{ color }}>
          {animatedScore}
        </span>
        <span className="text-[0.65rem] text-text-3 mt-0.5">/ 100</span>
      </div>
    </div>
  );
}
