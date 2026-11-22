-- ==============================================================================
-- TALOX TECH STREAM — Replace Twilio with Telnyx for Office Receptionist Voice
-- Idempotent migration updating:
--   1. public.platform_voice_credentials provider constraint ('retell', 'telnyx', 'calcom')
--   2. public.receptionist_configs columns (twilio_phone_number -> telnyx_phone_number,
--      twilio_phone_sid -> telnyx_phone_id) & covering index
-- ==============================================================================

-- 1. Update provider check constraint on platform_voice_credentials
DELETE FROM public.platform_voice_credentials WHERE provider = 'twilio';

ALTER TABLE public.platform_voice_credentials
    DROP CONSTRAINT IF EXISTS platform_voice_credentials_provider_check;

ALTER TABLE public.platform_voice_credentials
    ADD CONSTRAINT platform_voice_credentials_provider_check
    CHECK (provider IN ('retell', 'telnyx', 'calcom'));

-- 2. Rename Twilio columns on receptionist_configs to Telnyx equivalents (idempotently)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'receptionist_configs'
          AND column_name = 'twilio_phone_number'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'receptionist_configs'
          AND column_name = 'telnyx_phone_number'
    ) THEN
        ALTER TABLE public.receptionist_configs
            RENAME COLUMN twilio_phone_number TO telnyx_phone_number;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'receptionist_configs'
          AND column_name = 'twilio_phone_sid'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'receptionist_configs'
          AND column_name = 'telnyx_phone_id'
    ) THEN
        ALTER TABLE public.receptionist_configs
            RENAME COLUMN twilio_phone_sid TO telnyx_phone_id;
    END IF;
END $$;

ALTER TABLE public.receptionist_configs
    ADD COLUMN IF NOT EXISTS telnyx_phone_number VARCHAR(50),
    ADD COLUMN IF NOT EXISTS telnyx_phone_id VARCHAR(120);

DROP INDEX IF EXISTS public.idx_receptionist_configs_twilio_phone;
CREATE INDEX IF NOT EXISTS idx_receptionist_configs_telnyx_phone
    ON public.receptionist_configs(telnyx_phone_number);
