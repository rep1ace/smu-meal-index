/* ========== Data contract types matching data.json ========== */

export interface MealData {
  score: number;
  level: '畅通' | '一般' | '拥挤' | '爆满';
  head_count: number;
  end_time?: string;
}

export interface CampusMeals {
  午饭?: MealData;
  晚饭?: MealData;
}

export interface HourlyFlow {
  end_node: number;
  end_time: string;
  head_count: number;
}

export type CampusKey = '本部' | '顺德';
export type MealType = '午饭' | '晚饭';
export type ViewType = 'today' | 'week';

export interface AppData {
  date: string;
  updated_at: string;
  today: Record<CampusKey, CampusMeals>;
  hourly: Record<CampusKey, HourlyFlow[]>;
  history: Record<string, Record<CampusKey, CampusMeals>>;
  forecast: Record<string, Record<CampusKey, CampusMeals>>;
  forecast_hourly: Record<string, Record<CampusKey, HourlyFlow[]>>;
}
