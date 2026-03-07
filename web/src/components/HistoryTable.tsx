import type { CampusKey, CampusMeals } from '../types';
import { shortDate, scoreColor, pillClass } from '../utils';

interface Props {
  history: Record<string, Record<CampusKey, CampusMeals>>;
  campus: CampusKey;
}

export default function HistoryTable({ history, campus }: Props) {
  if (!history || Object.keys(history).length === 0) return null;

  const dates = Object.keys(history).sort().reverse();
  type Row = {
    date: string;
    meal: string;
    score: number;
    level: string;
    count: number;
  };
  const rows: Row[] = [];

  for (const date of dates) {
    const meals = history[date]?.[campus];
    if (!meals) continue;
    for (const mt of ['午饭', '晚饭'] as const) {
      const d = meals[mt];
      if (!d) continue;
      rows.push({
        date,
        meal: mt,
        score: d.score,
        level: d.level,
        count: d.head_count,
      });
    }
  }

  if (rows.length === 0) return null;

  return (
    <div>
      <h3 className="text-sm font-bold text-text mb-3 flex items-center gap-2">
        <span className="w-1 h-[1.1em] rounded-sm bg-accent shrink-0" />
        历史记录
      </h3>

      {/* Desktop table */}
      <div className="hidden sm:block bg-card rounded-2xl shadow-sm overflow-hidden mb-5">
        <table className="w-full border-spacing-0">
          <thead className="bg-blue-50">
            <tr>
              {['日期', '餐次', '得分', '等级', '人数'].map((h) => (
                <th
                  key={h}
                  className="py-2.5 px-4 text-[0.7rem] font-bold text-blue-700 text-left tracking-wider"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={`${row.date}-${row.meal}`}
                className="hover:bg-blue-50/60 transition-colors"
              >
                <td className="py-2 px-4 text-sm border-t border-border text-text-2">
                  {shortDate(row.date)}
                </td>
                <td className="py-2 px-4 text-sm border-t border-border text-text-2">
                  {row.meal}
                </td>
                <td
                  className="py-2 px-4 text-sm border-t border-border font-bold"
                  style={{ color: scoreColor(row.score) }}
                >
                  {row.score}
                </td>
                <td className="py-2 px-4 text-sm border-t border-border">
                  <span
                    className={`inline-block px-2.5 py-0.5 rounded-full text-[0.65rem] font-bold ${pillClass(row.level)}`}
                  >
                    {row.level}
                  </span>
                </td>
                <td className="py-2 px-4 text-sm border-t border-border text-text-2">
                  {row.count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile card list */}
      <div className="sm:hidden space-y-2 mb-5">
        {rows.map((row) => (
          <div
            key={`${row.date}-${row.meal}-m`}
            className="bg-card rounded-xl px-4 py-3 shadow-sm flex items-center justify-between gap-3"
          >
            <div className="min-w-0">
              <div className="text-sm font-semibold text-text">
                {shortDate(row.date)} · {row.meal}
              </div>
              <div className="text-xs text-text-3 mt-0.5">{row.count} 人</div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span
                className="text-lg font-extrabold"
                style={{ color: scoreColor(row.score) }}
              >
                {row.score}
              </span>
              <span
                className={`inline-block px-2 py-0.5 rounded-full text-[0.6rem] font-bold ${pillClass(row.level)}`}
              >
                {row.level}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
