const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];

export function scoreColor(s: number): string {
  if (s <= 25) return '#10b981';
  if (s <= 50) return '#f59e0b';
  if (s <= 75) return '#f97316';
  return '#ef4444';
}

export function pillClass(level: string): string {
  switch (level) {
    case '畅通': return 'pill-green';
    case '一般': return 'pill-yellow';
    case '拥挤': return 'pill-orange';
    case '爆满': return 'pill-red';
    default:     return 'pill-green';
  }
}

export function barGradient(pct: number): string {
  if (pct <= 25) return 'linear-gradient(90deg,#6ee7b7,#10b981)';
  if (pct <= 50) return 'linear-gradient(90deg,#fcd34d,#f59e0b)';
  if (pct <= 75) return 'linear-gradient(90deg,#fdba74,#f97316)';
  return 'linear-gradient(90deg,#fca5a5,#ef4444)';
}

export function formatDate(iso: string): string {
  if (!iso) return '--';
  const d = new Date(iso + 'T00:00:00');
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}/${m}/${day}  周${WEEKDAYS[d.getDay()]}`;
}

export function shortDate(iso: string): string {
  if (!iso) return '--';
  return iso.slice(5);
}

export function weekdayOf(iso: string): string {
  const d = new Date(iso + 'T00:00:00');
  return '周' + WEEKDAYS[d.getDay()];
}

export function addDays(isoDate: string, n: number): string {
  const d = new Date(isoDate + 'T00:00:00');
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}
