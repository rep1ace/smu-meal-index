import { motion } from 'framer-motion';
import type { ViewType } from '../types';

interface Props {
  active: ViewType;
  onChange: (v: ViewType) => void;
  show: boolean;
}

const VIEWS: { key: ViewType; label: string }[] = [
  { key: 'today', label: '今日' },
  { key: 'week', label: '本周' },
];

export default function ViewToggle({ active, onChange, show }: Props) {
  if (!show) return null;

  return (
    <div className="flex bg-white rounded-xl p-1 mb-4 shadow-sm">
      {VIEWS.map((v) => (
        <button
          key={v.key}
          onClick={() => onChange(v.key)}
          className="flex-1 relative py-2 text-sm font-semibold text-center cursor-pointer rounded-lg"
          style={{ color: active === v.key ? '#fff' : '#64748b' }}
        >
          {active === v.key && (
            <motion.div
              layoutId="activeView"
              className="absolute inset-0 bg-blue-500 rounded-lg shadow-sm"
              transition={{ type: 'spring', stiffness: 500, damping: 35 }}
            />
          )}
          <span className="relative z-10">{v.label}</span>
        </button>
      ))}
    </div>
  );
}
