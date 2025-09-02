-- Add settings column to chats table for storing chat-specific settings
-- This migration adds support for persisting user selections in research mode

-- Add the settings column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'chats'
        AND column_name = 'settings'
    ) THEN
        ALTER TABLE chats ADD COLUMN settings JSONB;
    END IF;
END $$;

-- Create an index on the settings column for better query performance
CREATE INDEX IF NOT EXISTS idx_chats_settings ON chats USING gin(settings);