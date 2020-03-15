CREATE INDEX repositories_participant_idx ON repositories (participant, show_on_profile);
CREATE INDEX repositories_info_fetched_at_idx ON repositories (info_fetched_at ASC)
    WHERE participant IS NOT NULL AND show_on_profile;
