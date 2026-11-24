-- Native SQL Server 2022 Row-Level Security & Least-Privilege Reader Login for CORE Pulse
-- Applied by scripts/load_mssql.py against the [core_pulse] database.

-- 1. Conversation history tables in [app] schema (the only tables pulse_reader may write)
IF OBJECT_ID('app.app_conversation_state', 'U') IS NULL
BEGIN
    CREATE TABLE app.app_conversation (
        conversation_id NVARCHAR(36) NOT NULL PRIMARY KEY,
        user_id NVARCHAR(80) NOT NULL,
        persona NVARCHAR(50) NOT NULL,
        title NVARCHAR(120) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        is_pinned BIT NOT NULL DEFAULT 0
    );
    CREATE INDEX ix_app_conv_user ON app.app_conversation(user_id, is_pinned DESC, updated_at DESC);

    CREATE TABLE app.app_message (
        message_id NVARCHAR(36) NOT NULL PRIMARY KEY,
        conversation_id NVARCHAR(36) NOT NULL
            REFERENCES app.app_conversation(conversation_id) ON DELETE CASCADE,
        seq INT NOT NULL,
        role NVARCHAR(10) NOT NULL,
        content_markdown NVARCHAR(MAX) NOT NULL,
        payload_json NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL
    );
    CREATE INDEX ix_app_msg_conv ON app.app_message(conversation_id, seq);

    CREATE TABLE app.app_conversation_state (
        conversation_id NVARCHAR(36) NOT NULL PRIMARY KEY
            REFERENCES app.app_conversation(conversation_id) ON DELETE CASCADE,
        agent_state_json NVARCHAR(MAX) NOT NULL
    );
END;
GO

-- 2. Drop existing security policy before recreating predicate functions
IF EXISTS (SELECT 1 FROM sys.security_policies WHERE name = 'core_pulse_rls_policy')
    DROP SECURITY POLICY rls.core_pulse_rls_policy;
GO

IF OBJECT_ID('rls.fn_region_access', 'IF') IS NOT NULL
    DROP FUNCTION rls.fn_region_access;
GO

IF OBJECT_ID('rls.fn_store_access', 'IF') IS NOT NULL
    DROP FUNCTION rls.fn_store_access;
GO

CREATE FUNCTION rls.fn_region_access(@RegionCode NVARCHAR(20))
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN
    SELECT 1 AS fn_access_ok
    WHERE
        SESSION_CONTEXT(N'user_id') IS NULL
        OR CAST(SESSION_CONTEXT(N'user_id') AS NVARCHAR(50)) = N'global_program_lead'
        OR EXISTS (
            SELECT 1
            FROM rls.user_region_access u
            WHERE u.user_id = CAST(SESSION_CONTEXT(N'user_id') AS NVARCHAR(50))
              AND u.region_code = @RegionCode
        );
GO

CREATE FUNCTION rls.fn_store_access(@RegionCode NVARCHAR(20), @AdoptionWaveNumber INT)
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN
    SELECT 1 AS fn_access_ok
    WHERE
        SESSION_CONTEXT(N'user_id') IS NULL
        OR CAST(SESSION_CONTEXT(N'user_id') AS NVARCHAR(50)) = N'global_program_lead'
        OR EXISTS (
            SELECT 1
            FROM rls.user_region_access u
            WHERE u.user_id = CAST(SESSION_CONTEXT(N'user_id') AS NVARCHAR(50))
              AND u.region_code = @RegionCode
        )
        OR (
            @RegionCode IS NULL AND @AdoptionWaveNumber IS NOT NULL AND EXISTS (
                SELECT 1
                FROM rls.user_region_access u
                INNER JOIN silver.organization o ON o.RegionCode = u.region_code
                WHERE u.user_id = CAST(SESSION_CONTEXT(N'user_id') AS NVARCHAR(50))
                  AND o.AdoptionWaveNumber = @AdoptionWaveNumber
            )
        );
GO

CREATE SECURITY POLICY rls.core_pulse_rls_policy
    ADD FILTER PREDICATE rls.fn_store_access(RegionCode, AdoptionWaveNumber) ON gold.certified_adoption_store,
    ADD FILTER PREDICATE rls.fn_region_access(RegionCode) ON gold.coreadoption_event,
    ADD FILTER PREDICATE rls.fn_region_access(RegionCode) ON gold.coreadoption_user_activity,
    ADD FILTER PREDICATE rls.fn_region_access(RegionCode) ON reference.rollout_registry
WITH (STATE = ON);
GO
