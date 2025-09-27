-- Fix cascading deletes for research_reports when missions are deleted
-- This migration is idempotent and can be run multiple times safely

DO $$
BEGIN
    -- Check if the foreign key constraint exists without CASCADE
    IF EXISTS (
        SELECT 1 
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name = 'research_reports'
            AND kcu.column_name = 'mission_id'
            AND ccu.table_name = 'missions'
            AND tc.constraint_name = 'research_reports_mission_id_fkey'
    ) THEN
        -- Drop the existing constraint
        ALTER TABLE research_reports 
        DROP CONSTRAINT IF EXISTS research_reports_mission_id_fkey;
        
        -- Re-add with CASCADE
        ALTER TABLE research_reports 
        ADD CONSTRAINT research_reports_mission_id_fkey 
        FOREIGN KEY (mission_id) REFERENCES missions(id) ON DELETE CASCADE;
        
        RAISE NOTICE 'Updated research_reports_mission_id_fkey to include ON DELETE CASCADE';
    ELSE
        RAISE NOTICE 'research_reports_mission_id_fkey already has CASCADE or does not exist - skipping';
    END IF;
END $$;