/**
 * REQ-042 WS-S1: Workspace 时间显示辅助。
 * - formatTime: 列表用相对时间（<7 天），更早落回日期。
 * - formatFullTime: 详情用完整本地化时间；无效输入落回占位（不抛）。
 */

function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatTime(iso: string | null | undefined): string {
  const d = parse(iso);
  if (!d) return "";
  const diffMs = Date.now() - d.getTime();
  const min = Math.floor(diffMs / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour} 小时前`;
  const day = Math.floor(hour / 24);
  if (day < 7) return `${day} 天前`;
  return d.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

export function formatFullTime(iso: string | null | undefined): string {
  const d = parse(iso);
  if (!d) return "—";
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
