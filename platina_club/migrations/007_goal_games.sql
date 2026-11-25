CREATE TABLE goal_games (
    id INTEGER PRIMARY KEY,
    goal_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    steam_app_id INTEGER NOT NULL CHECK (steam_app_id > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (goal_id, steam_app_id),
    UNIQUE (id, goal_id),
    FOREIGN KEY (goal_id) REFERENCES personal_goals (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_goal_games_goal ON goal_games (goal_id);
CREATE INDEX idx_goal_games_user ON goal_games (user_id, steam_app_id);

INSERT INTO goal_games (goal_id, user_id, steam_app_id)
SELECT id, user_id, steam_app_id
FROM personal_goals
WHERE steam_app_id IS NOT NULL;
