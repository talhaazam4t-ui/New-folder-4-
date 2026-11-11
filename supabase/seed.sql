-- ==============================================================================
-- TALOX TECH STREAM — Seed Data
-- Standard Services, Default Agent Registry, and Agent Permissions
-- ==============================================================================

-- 1. Default Services
INSERT INTO services (id, name, slug, category, description, configuration_schema, active)
VALUES
    ('11111111-1111-1111-1111-111111111101', 'Business Finance Tracking', 'business-finance', 'finance', 'Automated income, expense, and rent tracking with double-entry audit history.', '{"features": ["rent_tracking", "expense_logging", "reports"]}'::jsonb, TRUE),
    ('11111111-1111-1111-1111-111111111102', 'WhatsApp Business Automation', 'whatsapp-automation', 'messaging', 'Direct WhatsApp transaction extraction, auto-replies, and customer alerts.', '{"features": ["auto_reply", "transaction_parsing"]}'::jsonb, TRUE),
    ('11111111-1111-1111-1111-111111111103', 'Marketing & Growth Engine', 'marketing-growth', 'growth', 'Automated campaign planning, lead qualification, and ad analytics.', '{"features": ["campaign_planner", "lead_scoring"]}'::jsonb, TRUE)
ON CONFLICT (slug) DO NOTHING;

-- 2. Default Agent Registry
INSERT INTO agent_registry (id, name, category, description, version, configuration, active)
VALUES
    ('22222222-2222-2222-2222-222222222201', 'master_agent', 'orchestration', 'Central supervisor for task categorization, intent detection, and agent dispatch.', '1.0.0', '{"max_retries": 2}'::jsonb, TRUE),
    ('22222222-2222-2222-2222-222222222202', 'whatsapp_agent', 'messaging', 'Processes WhatsApp webhook conversations and extracts structured transactions.', '1.0.0', '{"tier": "fast"}'::jsonb, TRUE),
    ('22222222-2222-2222-2222-222222222203', 'transaction_agent', 'finance', 'Validates financial calculations and writes auditable double-entry business records.', '1.0.0', '{"currency": "USD"}'::jsonb, TRUE),
    ('22222222-2222-2222-2222-222222222204', 'campaign_planning_agent', 'marketing', 'Develops comprehensive marketing plans, content calendars, and growth strategies.', '1.0.0', '{"tier": "reasoning"}'::jsonb, TRUE),
    ('22222222-2222-2222-2222-222222222205', 'reviewer_agent', 'verification', 'Performs policy, mathematical, and schema compliance reviews before execution.', '1.0.0', '{"strict": true}'::jsonb, TRUE)
ON CONFLICT (name) DO NOTHING;

-- 3. Base Agent Permissions
INSERT INTO agent_permissions (agent_id, permission_name, allowed)
VALUES
    ('22222222-2222-2222-2222-222222222201', 'agents.execute', TRUE),
    ('22222222-2222-2222-2222-222222222202', 'business.records.create', TRUE),
    ('22222222-2222-2222-2222-222222222202', 'notifications.send', TRUE),
    ('22222222-2222-2222-2222-222222222203', 'business.records.read', TRUE),
    ('22222222-2222-2222-2222-222222222203', 'business.records.create', TRUE),
    ('22222222-2222-2222-2222-222222222204', 'marketing.campaign.create', TRUE),
    ('22222222-2222-2222-2222-222222222205', 'approvals.review', TRUE)
ON CONFLICT (agent_id, permission_name) DO NOTHING;
