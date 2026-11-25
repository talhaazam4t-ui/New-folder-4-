export interface HunterModuleSetting {
  id: string;
  module_name: string;
  label: string;
  description: string;
  is_on: boolean;
  budget_mode: string;
  daily_limit: number;
  used_today: number;
  remaining_today: number;
  usage_date: string;
}

export interface HunterLead {
  id: string;
  business_name: string;
  owner_name: string | null;
  owner_title: string | null;
  linkedin_url: string | null;
  country: string;
  city: string;
  category: string;
  address: string | null;
  phone: string | null;
  email: string | null;
  email_verified: boolean;
  website: string | null;
  favicon_url: string | null;
  services: string | null;
  working_hours: string | null;
  rating: number;
  total_reviews: number;
  has_ai: boolean;
  ai_evidence: Record<string, any>;
  pain_points: string[];
  interest_score: number;
  lead_source: "openstreetmap_free" | "google_places" | "apollo" | "hybrid";
  status: string;
  pipeline_stage: string;
  timezone: string;
  deal_value_usd: number;
  human_needed: boolean;
  do_not_disturb: boolean;
  last_contact_at: string | null;
  next_followup_at: string | null;
  call_result: string | null;
  best_time_to_call?: string;
  pain_summary?: string;
  cold_call_script?: string;
  cold_email_script?: string;
}

export interface HunterDemo {
  id: string;
  lead_id: string;
  email_subject: string;
  email_copy: string;
  whatsapp_copy: string;
  voice_script: string;
  chat_prompt: string;
  business_snapshot: Record<string, any>;
  status: "draft" | "approved" | "sent" | "rejected";
  approved_at: string | null;
  sent_at: string | null;
  sent_channels: string[];
  lead?: {
    business_name: string;
    owner_name: string | null;
    owner_title: string | null;
    linkedin_url: string | null;
    country: string;
    city: string;
    category: string;
    phone: string | null;
    email: string | null;
    website: string | null;
    favicon_url: string | null;
    pipeline_stage: string;
    do_not_disturb: boolean;
    human_needed: boolean;
  };
}

export interface HunterFollowup {
  id: string;
  lead_id: string;
  demo_id: string | null;
  followup_number: number;
  subject: string | null;
  message: string;
  channel: "email" | "linkedin" | "whatsapp";
  scheduled_at: string | null;
  sent_at: string | null;
  status: string;
  business_name?: string;
  owner_name?: string | null;
  human_needed?: boolean;
  do_not_disturb?: boolean;
}

export interface HunterOverviewData {
  kpis: {
    total_leads: number;
    no_ai_hot_leads: number;
    apollo_credits_used_today: number;
    apollo_daily_limit: number;
    demos_generated: number;
    demos_sent: number;
    replied_human_needed: number;
    paid_clients: number;
    revenue_usd: number;
    scheduled_followups: number;
  };
  human_needed_alerts: Array<{
    lead_id: string;
    business_name: string;
    owner_name: string | null;
    phone: string | null;
    email: string | null;
    city: string;
    country: string;
    last_reply: string | null;
  }>;
  api_keys_status: {
    openstreetmap_free_ready?: boolean;
    google_places_configured: boolean;
    apollo_configured: boolean;
    resend_configured: boolean;
    whatsapp_configured: boolean;
    gemini_configured: boolean;
  };
  control_panel: {
    budget_mode: string;
    modules: HunterModuleSetting[];
    module_map: Record<string, HunterModuleSetting>;
  };
}
