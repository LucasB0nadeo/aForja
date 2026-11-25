UPDATE games
SET achievements_sync_status = 'stale',
    achievements_sync_error = NULL
WHERE source = 'steam'
  AND achievements_sync_status = 'success';
