ALTER TABLE profiles
ADD COLUMN show_ranking_position INTEGER NOT NULL DEFAULT 1
    CHECK (show_ranking_position IN (0, 1));
