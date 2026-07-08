const SESSION_GAP_MIN = 30; // Scrape cadence is 15m; 2 missed cycles = new session

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
  resetWeekStart,
  resetWeekBounds,
  playerHash,
  playerInitials
};