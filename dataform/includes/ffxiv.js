const SESSION_GAP_MIN = 30; // Scrape cadence is 15m; 2 missed cycles = new session
const PATTERN_WINDOW_WEEKS = 8; // intraday "when to post" patterns use only the recent window

// Cutoff for recent-window pattern marts, anchored on the data frontier (max first_seen_date)
// in fct_listing_lifecycle rather than CURRENT_DATE(), so a lagging manual load doesn't empty
// the window. Pass the resolved ref("fct_listing_lifecycle") string.
function patternWindowCutoff(lifecycleRef) {
  return `DATE_SUB((SELECT MAX(first_seen_date) FROM ${lifecycleRef}), INTERVAL ${PATTERN_WINDOW_WEEKS} WEEK)`;
}

function resetWeekStart(tsExpr) {
  return `
    CASE
      WHEN ${tsExpr} >= TIMESTAMP_ADD(TIMESTAMP_TRUNC(${tsExpr}, WEEK(TUESDAY)), INTERVAL 8 HOUR)
      THEN TIMESTAMP_ADD(TIMESTAMP_TRUNC(${tsExpr}, WEEK(TUESDAY)), INTERVAL 8 HOUR)
      ELSE TIMESTAMP_SUB(TIMESTAMP_ADD(TIMESTAMP_TRUNC(${tsExpr}, WEEK(TUESDAY)), INTERVAL 8 HOUR), INTERVAL 7 DAY)
    END`;
}

function resetWeekBounds(period) {
  const cur = `(${resetWeekStart("CURRENT_TIMESTAMP()")})`;

  if (period === "current") {
    return { start: cur, end: `TIMESTAMP_ADD(${cur}, INTERVAL 7 DAY)` };
  }
  if (period === "previous") {
    return { start: `TIMESTAMP_SUB(${cur}, INTERVAL 7 DAY)`, end: cur };
  }
  throw new Error(`Invalid resetWeekBounds period: ${period}`);
}

function playerHash(creatorExpr, serverExpr) {
  return `
    CASE
      WHEN ${creatorExpr} IS NULL THEN NULL
      ELSE TO_HEX(MD5(CONCAT(LOWER(TRIM(${creatorExpr})), '|', LOWER(TRIM(COALESCE(${serverExpr}, ''))))))
    END`;
}

function playerInitials(creatorExpr) {
  return `
    ARRAY_TO_STRING(
      ARRAY(
        SELECT UPPER(SUBSTR(p, 1, 1)) || '.'
        FROM UNNEST(SPLIT(TRIM(${creatorExpr}), ' ')) AS p
        WHERE p != ''
      ), ' ')`;
}

module.exports = {
  SESSION_GAP_MIN,
  PATTERN_WINDOW_WEEKS,
  patternWindowCutoff,
  resetWeekStart,
  resetWeekBounds,
  playerHash,
  playerInitials
};
