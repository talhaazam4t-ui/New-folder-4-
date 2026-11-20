/**
 * Canonical Managed AI Services Metadata, Industries, and Slug Normalization
 * Matches backend catalog (`scripts/seed_services.py`).
 */

export const CORE_INDUSTRIES = [
  "Financing",
  "Clinics / Hospitals",
  "Real Estate / Property",
  "E-Commerce",
] as const;

export type CoreIndustry = (typeof CORE_INDUSTRIES)[number];

export interface CanonicalServiceMeta {
  slug: string;
  name: string;
  shortName: string;
  category: string;
  description: string;
  starterPrice: number;
  growthPrice: number;
  enterprisePrice: number;
  recommendedPath: string;
}

export const CANONICAL_SERVICES: CanonicalServiceMeta[] = [
  {
    slug: "business-financial-tracking",
    name: "Business Financial Tracking & Ledger",
    shortName: "Financial Tracking & Ledger",
    category: "finance",
    description:
      "Multi-currency income, rent, expense, and outstanding payment reconciliation with immutable audit trails.",
    starterPrice: 99,
    growthPrice: 249,
    enterprisePrice: 499,
    recommendedPath: "/finance",
  },
  {
    slug: "ai-marketing-growth",
    name: "AI Marketing & Growth Automation",
    shortName: "AI Marketing & Growth",
    category: "marketing",
    description:
      "Competitor intelligence, audience discovery, personalized outreach, and human-approved campaign orchestration.",
    starterPrice: 149,
    growthPrice: 349,
    enterprisePrice: 699,
    recommendedPath: "/marketing",
  },
  {
    slug: "whatsapp-business-concierge",
    name: "WhatsApp Business Concierge & Webhook Sync",
    shortName: "WhatsApp AI Concierge",
    category: "communication",
    description:
      "24/7 AI Receptionist, appointment booking, customer support, and automated lead replies on WhatsApp.",
    starterPrice: 129,
    growthPrice: 279,
    enterprisePrice: 549,
    recommendedPath: "/settings",
  },
  {
    slug: "multi-agent-orchestration",
    name: "Multi-Agent Task Orchestration Suite",
    shortName: "Multi-Agent Orchestration",
    category: "automation",
    description:
      "Managed end-to-end AI workflow orchestration combining Lead Gen, Qualification, Outreach, and Booking.",
    starterPrice: 199,
    growthPrice: 399,
    enterprisePrice: 799,
    recommendedPath: "/dashboard",
  },
  {
    slug: "lead-crm-qualification",
    name: "Lead CRM & AI Qualification Engine",
    shortName: "Lead CRM & Qualification",
    category: "sales",
    description:
      "Automated lead sourcing, deduplication, AI intent scoring, and appointment handoff.",
    starterPrice: 149,
    growthPrice: 299,
    enterprisePrice: 599,
    recommendedPath: "/marketing",
  },
  {
    slug: "executive-analytics-compliance",
    name: "Executive Analytics & Compliance Vault",
    shortName: "Executive Analytics & Vault",
    category: "governance",
    description:
      "Managed service performance reporting, conversion attribution, PII protection, and compliance auditing.",
    starterPrice: 99,
    growthPrice: 199,
    enterprisePrice: 399,
    recommendedPath: "/dashboard",
  },
];

export const CANONICAL_SERVICE_SLUGS: readonly string[] = CANONICAL_SERVICES.map(
  (s) => s.slug
);

export const SERVICE_SLUG_ALIASES: Record<string, string> = {
  // business-financial-tracking
  "business-financial-tracking": "business-financial-tracking",
  finance: "business-financial-tracking",
  "business-finance": "business-financial-tracking",
  "financial-tracking": "business-financial-tracking",
  automated_financial_ledger: "business-financial-tracking",
  "automated-financial-ledger": "business-financial-tracking",
  financial_ledger: "business-financial-tracking",

  // ai-marketing-growth
  "ai-marketing-growth": "ai-marketing-growth",
  marketing: "ai-marketing-growth",
  "marketing-growth": "ai-marketing-growth",
  marketing_growth: "ai-marketing-growth",
  "lead-generation-outreach": "ai-marketing-growth",
  "lead-generation-growth": "ai-marketing-growth",
  lead_generation_engine: "ai-marketing-growth",
  "lead-generation-engine": "ai-marketing-growth",

  // whatsapp-business-concierge
  "whatsapp-business-concierge": "whatsapp-business-concierge",
  whatsapp: "whatsapp-business-concierge",
  "whatsapp-automation": "whatsapp-business-concierge",
  "whatsapp-concierge": "whatsapp-business-concierge",
  whatsapp_concierge: "whatsapp-business-concierge",
  "whatsapp-conversational-ai": "whatsapp-business-concierge",
  "whatsapp-24-7-concierge": "whatsapp-business-concierge",
  whatsapp_ai_concierge: "whatsapp-business-concierge",
  "whatsapp-ai-concierge": "whatsapp-business-concierge",

  // multi-agent-orchestration
  "multi-agent-orchestration": "multi-agent-orchestration",
  multi_agent_orchestration: "multi-agent-orchestration",
  orchestration: "multi-agent-orchestration",
  "multi-agent": "multi-agent-orchestration",

  // lead-crm-qualification
  "lead-crm-qualification": "lead-crm-qualification",
  "lead-crm": "lead-crm-qualification",
  lead_crm: "lead-crm-qualification",
  "lead-qualification": "lead-crm-qualification",
  lead_funnel: "lead-crm-qualification",

  // executive-analytics-compliance
  "executive-analytics-compliance": "executive-analytics-compliance",
  executive_analytics_compliance: "executive-analytics-compliance",
  analytics: "executive-analytics-compliance",
  "executive-analytics": "executive-analytics-compliance",
  compliance: "executive-analytics-compliance",
};

export function normalizeServiceSlug(raw?: string | null): string | null {
  if (!raw) return null;
  const cleaned = raw.trim().toLowerCase();
  if (!cleaned) return null;
  if (SERVICE_SLUG_ALIASES[cleaned]) {
    return SERVICE_SLUG_ALIASES[cleaned];
  }
  const hyphenated = cleaned.replace(/_/g, "-");
  if (SERVICE_SLUG_ALIASES[hyphenated]) {
    return SERVICE_SLUG_ALIASES[hyphenated];
  }
  return null;
}

export function getCanonicalServiceMeta(
  raw?: string | null
): CanonicalServiceMeta | undefined {
  const normalized = normalizeServiceSlug(raw);
  if (!normalized) return undefined;
  return CANONICAL_SERVICES.find((s) => s.slug === normalized);
}
