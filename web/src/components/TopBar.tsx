import { formatDate } from '../utils';

interface Props {
  date: string;
  updatedAt: string;
}

export default function TopBar({ date, updatedAt }: Props) {
  return (
    <header className="bg-gradient-to-br from-blue-700 via-blue-600 to-blue-500 text-white">
      <div className="max-w-3xl mx-auto px-5 pt-10 pb-16 sm:pt-12 sm:pb-20">
        <h1 className="text-[1.75rem] sm:text-3xl font-extrabold tracking-tight leading-tight">
          SMU Meal Index
        </h1>
        <p className="text-blue-200 text-sm mt-1.5 font-medium">
          南方医科大学抢饭指数
        </p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-4 text-xs text-blue-200/75">
          <span>{formatDate(date)}</span>
          {updatedAt && (
            <span className="flex items-center gap-1">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-200" />
              {updatedAt.replace('T', ' ')}
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
