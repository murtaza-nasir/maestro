-- Add support for versioned research reports
-- This migration is idempotent and can be run multiple times safely

DO $$
BEGIN
    -- Create research_reports table to store versioned reports for research missions
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_name = 'research_reports'
    ) THEN
        CREATE TABLE research_reports (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            mission_id UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
            version INTEGER NOT NULL DEFAULT 1,
            title VARCHAR(255),
            content TEXT NOT NULL,
            is_current BOOLEAN DEFAULT TRUE,
            revision_notes TEXT, -- Notes about what was revised in this version
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(mission_id, version)
        );
        
        -- Create indexes for performance
        CREATE INDEX idx_research_reports_mission_id ON research_reports(mission_id);
        CREATE INDEX idx_research_reports_is_current ON research_reports(is_current);
        CREATE INDEX idx_research_reports_mission_current ON research_reports(mission_id, is_current);
        
        RAISE NOTICE 'Created research_reports table for versioned research reports';
    ELSE
        RAISE NOTICE 'research_reports table already exists - skipping';
    END IF;
    
    -- Add report_version field to missions table to track current version
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'missions' AND column_name = 'current_report_version'
    ) THEN
        ALTER TABLE missions ADD COLUMN current_report_version INTEGER DEFAULT 1;
        RAISE NOTICE 'Added current_report_version to missions table';
    ELSE
        RAISE NOTICE 'current_report_version already exists in missions table - skipping';
    END IF;

    -- Create trigger to update timestamps
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.triggers
        WHERE trigger_name = 'update_research_reports_updated_at'
    ) THEN
        CREATE TRIGGER update_research_reports_updated_at
            BEFORE UPDATE ON research_reports
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        RAISE NOTICE 'Created update trigger for research_reports table';
    ELSE
        RAISE NOTICE 'update_research_reports_updated_at trigger already exists - skipping';
    END IF;

EXCEPTION
    WHEN OTHERS THEN
        RAISE WARNING 'Migration error: %', SQLERRM;
END $$;