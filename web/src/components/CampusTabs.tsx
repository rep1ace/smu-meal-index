import { motion } from 'framer-motion';
import type { CampusKey } from '../types';

interface Props {
  active: CampusKey;
  onChange: (c: CampusKey) => void;
}

const CAMPUSES: { key: CampusKey; label: string }[] = [
  { key: '本部', label: '校本部' },
  { key: '顺德', label: '顺德校区' },
];

export default function CampusTabs({ active, onChange }: Props) {
  return (
    <div className="flex gap-2 mb-5">
      {CAMPUSES.map((c) => (
        <button
          key={c.key}
          onClick={() => onChange(c.key)}
          className={`
            flex-1 relative py-2.5 rounded-xl text-sm font-semibold text-center
            cursor-pointer border-2 transition-all duration-200
            ${active === c.key
              ? 'border-blue-500 text-blue-600 bg-blue-50 shadow-sm'
              : 'border-slate-200 text-slate-500 bg-white hover:text-blue-600 hover:border-blue-200'
            }
          `}
        >
          {active === c.key && (
            <motion.div
              layoutId="activeCampus"
              className="absolute inset-0 border-2 border-blue-500 rounded-xl"
              transition={{ type: 'spring', stiffness: 500, damping: 35 }}
            />
          )}
          <span className="relative z-10">{c.label}</span>
        </button>
      ))}
    </div>
  );
}
