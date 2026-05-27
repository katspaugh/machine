const DASH = "—";

export function formatBytes(n: number | null): string {
  if (n === null) return DASH;
  const gb = n / 1_073_741_824;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = n / 1_048_576;
  return `${Math.round(mb)} MB`;
}

export function formatDuration(secs: number | null): string {
  if (secs === null) return DASH;
  if (secs < 60) return `${Math.floor(secs)}s`;
  const m = Math.floor(secs / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}

export function formatPercent(p: number | null): string {
  if (p === null) return DASH;
  return `${Math.round(p)}%`;
}

export function formatMem(used: number | null, total: number | null): string {
  if (used === null || total === null) return DASH;
  const u = used / 1_073_741_824;
  const t = total / 1_073_741_824;
  return `${u.toFixed(1)} / ${Math.round(t)} GB`;
}
