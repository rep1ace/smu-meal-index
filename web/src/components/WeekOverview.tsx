import type { CampusKey, CampusMeals } from '../types';
import { shortDate, weekdayOf, addDays, scoreColor, pillClass } from '../utils';

interface Props {
  baseDate: string;
  campus: CampusKey;
  today: Record<string, CampusMeals>;
  forecast: Record<string, Record<string, CampusMeals>>;
  selectedDate: string | null;
  onSelectDate: (d: string) => void;
}

export default function WeekOverview({
  baseDate,
  campus,
  today,
  forecast,
  selectedDate,
  onSelectDate,
}: Props) {
  const days = Array.from({ length: 7 }, (_, i) => addDays(baseDate, i));
  const realToday = new Date().toISOString().slice(0, 10);

  return (
    <div className="grid grid-cols-4 sm:grid-cols-7 gap-2 mb-5">
      {days.map((d) => {
        const isRealToday = d === realToday;
        const isBaseDate = d === baseDate;
        const isActive = d === selectedDate;

        let dayMeals: CampusMeals | null = null;
        if (isBaseDate) {
          dayMeals = (today as Record<string, CampusMeals>)[campus] ?? null;
        } else {
          dayMeals = forecast[d]?.[campus] ?? null;
        }

        const hasData = !!(dayMeals && (dayMeals['午饭'] || dayMeals['晚饭']));
        const primaryMeal = dayMeals?.['午饭'] ?? dayMeals?.['晚饭'];

        return (
          <div
            key={d}
            onClick={() => onSelectDate(d)}
            className={`
              bg-card rounded-xl py-3 px-2 shadow-sm text-center cursor-pointer
              border-2 transition-all duration-200
              ${isActive ? 'border-blue-500 shadow-md' : 'border-transparent hover:border-blue-200'}
              ${!hasData ? 'opacity-40' : ''}
            `}
          >
            <div className="text-[0.7rem] font-bold text-text-2 mb-0.5">
              {shortDate(d)}
            </div>
            <div className="text-[0.6rem] text-text-3 mb-2">
              {isRealToday ? '今天' : weekdayOf(d)}
            </div>
            {hasData && primaryMeal ? (
              <>
                <div
                  className="text-lg font-extrabold leading-none"
                  style={{ color: scoreColor(primaryMeal.score) }}
                >
                  {Math.round(primaryMeal.score)}
                </div>
                <div className="text-[0.6rem] text-text-3 mt-0.5">午饭</div>
                <div className="mt-1.5">
                  <span
                    className={`inline-block px-2 py-0.5 rounded-full text-[0.55rem] font-bold ${pillClass(primaryMeal.level)}`}
                  >
                    {primaryMeal.level}
                  </span>
                </div>
              </>
            ) : (
              <div className="text-[0.7rem] text-text-3 py-2">无课</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
