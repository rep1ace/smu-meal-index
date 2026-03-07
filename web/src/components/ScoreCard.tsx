import type { MealData, MealType } from '../types';
import { pillClass } from '../utils';
import Gauge from './Gauge';

interface Props {
  mealType: MealType;
  data?: MealData;
}

export default function ScoreCard({ mealType, data }: Props) {
  const icon = mealType === '午饭' ? '☀️' : '☽';

  return (
    <div
      className="bg-card rounded-2xl p-5 shadow-sm flex flex-col items-center gap-2
                 hover:shadow-md transition-shadow duration-200"
    >
      <div className="text-xs font-semibold text-text-2 tracking-wide">
        {icon} {mealType}
      </div>

      {!data ? (
        <div className="h-[110px] flex items-center justify-center text-text-3 text-sm">
          暂无数据
        </div>
      ) : (
        <>
          <Gauge score={data.score} />
          <span
            className={`inline-block px-3 py-1 rounded-full text-xs font-bold ${pillClass(data.level)}`}
          >
            {data.level}
          </span>
          <div className="text-xs text-text-3">
            {data.head_count} 人{data.end_time && <> &middot; {data.end_time} 下课</>}
          </div>
        </>
      )}
    </div>
  );
}
