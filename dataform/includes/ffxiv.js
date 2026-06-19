// =============================================================================
// Shared FFXIV / pipeline logic for Dataform models.
// Accessible in .sqlx files via the `ffxiv` namespace, e.g. ${ffxiv.SESSION_GAP_MIN}.
// =============================================================================

// Two consecutive scrapes more than this many minutes apart are treated as
// separate listing sessions (gap-and-islands). Scrape cadence is 15 min, so
// 30 min = two missed cycles before we consider a listing a fresh re-post.
const SESSION_GAP_MIN = 30;

// Most recent FFXIV weekly reset (Tuesday 08:00 UTC) at or before `tsExpr`.
// `tsExpr` is any SQL TIMESTAMP expression. Returns a SQL TIMESTAMP expression.
function resetWeekStart(tsExpr) {
  return `
    CASE
      WHEN ${tsExpr} >= TIMESTAMP_ADD(TIMESTAMP_TRUNC(${tsExpr}, WEEK(TUESDAY)), INTERVAL 8 HOUR)
      THEN TIMESTAMP_ADD(TIMESTAMP_TRUNC(${tsExpr}, WEEK(TUESDAY)), INTERVAL 8 HOUR)
      ELSE TIMESTAMP_SUB(
             TIMESTAMP_ADD(TIMESTAMP_TRUNC(${tsExpr}, WEEK(TUESDAY)), INTERVAL 8 HOUR),
             INTERVAL 7 DAY)
    END`;
}

// Boundaries of the "current" or "previous" FFXIV reset week, relative to now.
// Returns { start, end } as SQL TIMESTAMP expressions (half-open [start, end)).
function resetWeekBounds(period) {
  const cur = `(${resetWeekStart("CURRENT_TIMESTAMP()")})`;
  if (period === "current") {
    return { start: cur, end: `TIMESTAMP_ADD(${cur}, INTERVAL 7 DAY)` };
  }
  if (period === "previous") {
    return { start: `TIMESTAMP_SUB(${cur}, INTERVAL 7 DAY)`, end: cur };
  }
  throw new Error(`resetWeekBounds: unknown period '${period}' (expected 'current' or 'previous')`);
}

module.exports = { SESSION_GAP_MIN, resetWeekStart, resetWeekBounds };
