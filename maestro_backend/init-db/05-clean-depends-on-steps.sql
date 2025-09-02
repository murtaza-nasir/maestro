-- Migration to remove deprecated 'depends_on_steps' field from mission contexts
-- This field was removed from the ReportSection schema but may still exist in old database records
-- This migration is idempotent and can be run multiple times safely

DO $$
DECLARE
    mission_record RECORD;
    cleaned_context JSONB;
    updated_count INTEGER := 0;
    needs_migration BOOLEAN := FALSE;
BEGIN
    -- First check if any missions need migration
    SELECT EXISTS (
        SELECT 1 FROM missions 
        WHERE mission_context IS NOT NULL 
        AND mission_context::text LIKE '%depends_on_steps%'
        LIMIT 1
    ) INTO needs_migration;
    
    IF NOT needs_migration THEN
        RAISE NOTICE 'No missions need cleaning - depends_on_steps not found';
        RETURN;
    END IF;
    
    -- Create temporary function to recursively remove 'depends_on_steps' from report sections
    -- Using CREATE OR REPLACE makes this idempotent
    CREATE OR REPLACE FUNCTION temp_remove_depends_on_steps(data JSONB) RETURNS JSONB AS $func$
    DECLARE
        result JSONB;
        section JSONB;
        sections_array JSONB;
        i INTEGER;
    BEGIN
        result := data;
        
        -- Remove depends_on_steps from current level if it exists
        IF result ? 'depends_on_steps' THEN
            result := result - 'depends_on_steps';
        END IF;
        
        -- Process subsections if they exist
        IF result ? 'subsections' AND jsonb_typeof(result->'subsections') = 'array' THEN
            sections_array := '[]'::jsonb;
            FOR i IN 0..jsonb_array_length(result->'subsections') - 1 LOOP
                section := temp_remove_depends_on_steps(result->'subsections'->i);
                sections_array := sections_array || section;
            END LOOP;
            result := jsonb_set(result, '{subsections}', sections_array);
        END IF;
        
        RETURN result;
    END;
    $func$ LANGUAGE plpgsql;
    
    -- Process all missions
    FOR mission_record IN 
        SELECT id, mission_context 
        FROM missions 
        WHERE mission_context IS NOT NULL
    LOOP
        -- Check if migration is needed (if 'depends_on_steps' exists in the JSON)
        IF mission_record.mission_context::text LIKE '%depends_on_steps%' THEN
            cleaned_context := mission_record.mission_context;
            
            -- Clean the plan.report_outline if it exists
            IF cleaned_context ? 'plan' AND 
               cleaned_context->'plan' ? 'report_outline' AND 
               jsonb_typeof(cleaned_context->'plan'->'report_outline') = 'array' THEN
                
                -- Process each section in the report_outline
                DECLARE
                    outline_array JSONB := '[]'::jsonb;
                    section_index INTEGER;
                BEGIN
                    FOR section_index IN 0..jsonb_array_length(cleaned_context->'plan'->'report_outline') - 1 LOOP
                        outline_array := outline_array || temp_remove_depends_on_steps(cleaned_context->'plan'->'report_outline'->section_index);
                    END LOOP;
                    
                    -- Update the cleaned outline
                    cleaned_context := jsonb_set(cleaned_context, '{plan,report_outline}', outline_array);
                END;
            END IF;
            
            -- Update the mission record
            UPDATE missions 
            SET mission_context = cleaned_context
            WHERE id = mission_record.id;
            
            updated_count := updated_count + 1;
        END IF;
    END LOOP;
    
    -- Drop the temporary function
    DROP FUNCTION IF EXISTS temp_remove_depends_on_steps(JSONB);
    
    -- Log the results
    IF updated_count > 0 THEN
        RAISE NOTICE 'Successfully cleaned depends_on_steps from % missions', updated_count;
    ELSE
        RAISE NOTICE 'No missions needed cleaning - depends_on_steps not found';
    END IF;
    
EXCEPTION
    WHEN OTHERS THEN
        -- Log error but don't fail - the app can still work with the old data
        RAISE WARNING 'Error cleaning depends_on_steps: %', SQLERRM;
        -- Clean up the function if it exists
        DROP FUNCTION IF EXISTS temp_remove_depends_on_steps(JSONB);
END $$;