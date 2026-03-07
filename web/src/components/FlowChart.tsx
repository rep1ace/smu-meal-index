import { useEffect, useRef, useState } from 'react';
import type { HourlyFlow } from '../types';
import { barGradient } from '../utils';

interface Props {
  flows: HourlyFlow[];
  title: string;
}

export default function FlowChart({ flows, title }: Props) {
  if (flows.length === 0) return null;

  const maxCount = Math.max(...flows.map((f) => f.head_count), 1);

  // Trigger CSS transition after mount
  const [ready, setReady] = useState(false);
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      requestAnimationFrame(() => setReady(true));
    } else {
      setReady(true);
    }
  }, [flows]);

  return (
    <div>
      <h3 className="text-sm font-bold text-text mb-3 flex items-center gap-2">
        <span className="w-1 h-[1.1em] rounded-sm bg-accent shrink-0" />
        {title}
      </h3>
      <div className="bg-card rounded-2xl py-4 px-4 sm:px-5 shadow-sm">
        {flows.map((f, i) => {
          const pct = (f.head_count / maxCount) * 100;
          return (
            <div key={i} className="flex items-center mb-2 last:mb-0">
              <div className="w-12 text-xs font-semibold text-text-2 text-right pr-3 shrink-0">
                {f.end_time}
              </div>
              <div className="flex-1 h-5 bg-blue-50 rounded-md overflow-hidden">
                <div
                  className="flow-bar h-full rounded-md"
                  style={{
                    width: ready ? `${pct}%` : '0%',
                    background: barGradient(pct),
                    minWidth: 3,
                  }}
                />
              </div>
              <div className="w-14 text-xs font-semibold text-text-2 text-right pl-2 shrink-0">
                {f.head_count}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
