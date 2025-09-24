-- Add fields to track document groups generated from missions
-- This migration is idempotent and can be run multiple times safely

DO $$
BEGIN
    -- Add generated_document_group_id to missions table
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'missions' AND column_name = 'generated_document_group_id'
    ) THEN
        ALTER TABLE missions ADD COLUMN generated_document_group_id UUID;
        ALTER TABLE missions ADD CONSTRAINT fk_mission_generated_doc_group 
            FOREIGN KEY (generated_document_group_id) REFERENCES document_groups(id) ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS idx_missions_generated_document_group ON missions(generated_document_group_id);
        RAISE NOTICE 'Added generated_document_group_id to missions table';
    ELSE
        RAISE NOTICE 'generated_document_group_id already exists in missions table - skipping';
    END IF;

    -- Add source_mission_id to document_groups table to track origin
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'document_groups' AND column_name = 'source_mission_id'
    ) THEN
        ALTER TABLE document_groups ADD COLUMN source_mission_id UUID;
        ALTER TABLE document_groups ADD CONSTRAINT fk_doc_group_source_mission 
            FOREIGN KEY (source_mission_id) REFERENCES missions(id) ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS idx_document_groups_source_mission ON document_groups(source_mission_id);
        RAISE NOTICE 'Added source_mission_id to document_groups table';
    ELSE
        RAISE NOTICE 'source_mission_id already exists in document_groups table - skipping';
    END IF;

    -- Add auto_generated flag to document_groups table
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'document_groups' AND column_name = 'auto_generated'
    ) THEN
        ALTER TABLE document_groups ADD COLUMN auto_generated BOOLEAN DEFAULT FALSE;
        RAISE NOTICE 'Added auto_generated flag to document_groups table';
    ELSE
        RAISE NOTICE 'auto_generated flag already exists in document_groups table - skipping';
    END IF;

EXCEPTION
    WHEN OTHERS THEN
        RAISE WARNING 'Migration error: %', SQLERRM;
END $$;