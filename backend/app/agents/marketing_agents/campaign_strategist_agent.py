"""Specialized Marketing Agent — Competitor Research & Campaign Copy Strategist.
"""

from app.agents.base_agent import BaseAgent


class CampaignStrategistAgent(BaseAgent):
    name = "campaign_strategist_agent"
    role = "Growth & Campaign Strategist"
    category = "marketing"
    description = (
        "Performs audience discovery, generates ad creatives, and drafts multi-channel campaigns. "
        "Requires human approval before publishing live campaigns."
    )
    default_task_type = "marketing_campaign_strategy"
    allowed_tools = {"read_context", "query_marketing_insights", "generate_ad_copy", "create_campaign_draft"}
    max_steps = 4
    timeout_seconds = 30


campaign_strategist_agent = CampaignStrategistAgent()
