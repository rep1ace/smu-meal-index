import { useState, useCallback, useEffect } from 'react';
import type { CampusKey, ViewType, CampusMeals, HourlyFlow } from './types';
import { useAppData } from './hooks/useAppData';
import { shortDate, weekdayOf, addDays } from './utils';
import TopBar from './components/TopBar';
import ViewToggle from './components/ViewToggle';
import CampusTabs from './components/CampusTabs';
import ScoreCard from './components/ScoreCard';
import FlowChart from './components/FlowChart';
import WeekOverview from './components/WeekOverview';
import HistoryTable from './components/HistoryTable';
import Footer from './components/Footer';

function pickInitialDate(
  baseDate: string,
  today: Record<string, CampusMeals>,
  forecast: Record<string, Record<string, CampusMeals>>,
): string {
  if (today && Object.keys(today).length > 0) return baseDate;
  for (let i = 1; i <= 6; i++) {
    const d = addDays(baseDate, i);
    if (forecast[d] && Object.keys(forecast[d]).length > 0) return d;
  }
  return baseDate;
}

export default function App() {
  const { data, error, loading } = useAppData();
  const [campus, setCampus] = useState<CampusKey>('本部');
  const [view, setView] = useState<ViewType>('today');
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  // Auto-switch to week view when today has no data but forecast does
  useEffect(() => {
    if (!data) return;
    const hasTodayData =
      Object.keys(data.today || {}).length > 0 ||
      Object.keys(data.hourly || {}).length > 0;
    const hasForecast =
      data.forecast && Object.keys(data.forecast).length > 0;

    if (!hasTodayData && hasForecast) {
      setView('week');
    }
  }, [data]);

  // Initialize selected date
  useEffect(() => {
    if (!data || selectedDate) return;
    const initial = pickInitialDate(data.date, data.today, data.forecast || {});
    setSelectedDate(initial);
  }, [data, selectedDate]);

  const handleViewChange = useCallback(
    (v: ViewType) => {
      setView(v);
      if (v === 'week' && !selectedDate && data) {
        setSelectedDate(data.date);
      }
    },
    [selectedDate, data],
  );

  /* ---------- Loading ---------- */
  if (loading) {
    return (
      <div className="min-h-screen bg-surface flex items-center justify-center">
        <div className="text-text-3 text-sm text-center">
          <div className="w-8 h-8 border-3 border-blue-200 border-t-blue-500 rounded-full mx-auto mb-3 animate-spin" />
          加载中...
        </div>
      </div>
    );
  }

  /* ---------- Error ---------- */
  if (error || !data) {
    return (
      <div className="min-h-screen bg-surface flex items-center justify-center">
        <div className="bg-card rounded-2xl shadow-sm text-center p-8 text-text-3 text-sm mx-4">
          加载失败: {error || 'Unknown error'}
        </div>
      </div>
    );
  }

  /* ---------- Data prep ---------- */
  const hasForecast = !!(data.forecast && Object.keys(data.forecast).length > 0);
  const hasTodayData =
    Object.keys(data.today || {}).length > 0 ||
    Object.keys(data.hourly || {}).length > 0;

  return (
    <div className="min-h-screen bg-surface">
      <TopBar date={data.date} updatedAt={data.updated_at} />

      <div className="max-w-3xl mx-auto -mt-8 px-4 pb-8 relative z-10">
        <ViewToggle active={view} onChange={handleViewChange} show={hasForecast} />
        <CampusTabs active={campus} onChange={setCampus} />

        {view === 'today' ? (
          <TodayView data={data} campus={campus} hasTodayData={hasTodayData} />
        ) : (
          <WeekView
            data={data}
            campus={campus}
            selectedDate={selectedDate}
            onSelectDate={setSelectedDate}
          />
        )}
      </div>

      <Footer />
    </div>
  );
}

/* ================= Today View ================= */
interface TodayViewProps {
  data: NonNullable<ReturnType<typeof useAppData>['data']>;
  campus: CampusKey;
  hasTodayData: boolean;
}

function TodayView({ data, campus, hasTodayData }: TodayViewProps) {
  const meals = (data.today?.[campus] ?? {}) as CampusMeals;
  const flows = (data.hourly?.[campus] ?? []) as HourlyFlow[];

  return (
    <div>
      {!hasTodayData ? (
        <div className="bg-card rounded-2xl shadow-sm text-center py-10 px-4 text-text-3 text-sm mb-5">
          今日暂无课程数据
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 mb-5">
            <ScoreCard mealType="午饭" data={meals['午饭']} />
            <ScoreCard mealType="晚饭" data={meals['晚饭']} />
          </div>
          {flows.length > 0 && (
            <FlowChart flows={flows} title="今日下课人流" />
          )}
          <div className="mt-5" />
        </>
      )}
      <HistoryTable history={data.history} campus={campus} />
    </div>
  );
}

/* ================= Week View ================= */
interface WeekViewProps {
  data: NonNullable<ReturnType<typeof useAppData>['data']>;
  campus: CampusKey;
  selectedDate: string | null;
  onSelectDate: (d: string) => void;
}

function WeekView({ data, campus, selectedDate, onSelectDate }: WeekViewProps) {
  const isBaseDate = selectedDate === data.date;
  const realToday = new Date().toISOString().slice(0, 10);
  const isRealToday = selectedDate === realToday;
  let dayMeals: CampusMeals = {};
  let dayFlows: HourlyFlow[] = [];

  if (selectedDate) {
    if (isBaseDate) {
      dayMeals = (data.today?.[campus] ?? {}) as CampusMeals;
      dayFlows = (data.hourly?.[campus] ?? []) as HourlyFlow[];
    } else {
      dayMeals = (data.forecast?.[selectedDate]?.[campus] ?? {}) as CampusMeals;
      dayFlows = (data.forecast_hourly?.[selectedDate]?.[campus] ?? []) as HourlyFlow[];
    }
  }

  const hasDayData = !!(dayMeals['午饭'] || dayMeals['晚饭']);
  const dateLabel = isRealToday
    ? '今天'
    : selectedDate
      ? `${shortDate(selectedDate)} ${weekdayOf(selectedDate)}`
      : '';

  return (
    <div>
      <WeekOverview
        baseDate={data.date}
        campus={campus}
        today={data.today}
        forecast={data.forecast || {}}
        selectedDate={selectedDate}
        onSelectDate={onSelectDate}
      />

      {!hasDayData ? (
        <div className="bg-card rounded-2xl shadow-sm text-center py-10 px-4 text-text-3 text-sm mb-5">
          {dateLabel} 暂无课程数据
        </div>
      ) : (
        <>
          <h3 className="text-sm font-bold text-text mb-3 flex items-center gap-2">
            <span className="w-1 h-[1.1em] rounded-sm bg-accent shrink-0" />
            {dateLabel}
          </h3>
          <div className="grid grid-cols-2 gap-4 mb-5">
            <ScoreCard mealType="午饭" data={dayMeals['午饭']} />
            <ScoreCard mealType="晚饭" data={dayMeals['晚饭']} />
          </div>
          {dayFlows.length > 0 && (
            <FlowChart flows={dayFlows} title={`${dateLabel}下课人流`} />
          )}
        </>
      )}
    </div>
  );
}
