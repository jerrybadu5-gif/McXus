export type Role = "user" | "support" | "kyc" | "moderator" | "mediator" | "finance" | "compliance" | "admin";

export interface User {
  id: string; phone: string | null; display_name: string; role: Role; kyc_tier: number; status: "active" | "frozen";
}

export type Stage = "negotiation" | "mediation" | "decided" | "appeal" | "resolved";
export type Who = "buyer" | "seller" | "staff" | "McXus";

export interface DisputeSummary {
  id: string; order_id: string; title: string; amount: string; stage: Stage; reason: string;
  buyer: { id: string; name: string }; seller: { id: string; name: string };
  opened_by: "buyer" | "seller"; opened_at: string; deadline: string | null; overdue: boolean;
  mediator: string | null; mediator_id: string | null; outcome: "agreed" | "mediator" | "senior" | null;
  buyer_refund: string | null;
}

export interface Dispute extends DisputeSummary {
  you: "buyer" | "seller" | "staff";
  actions: string[];
  negotiate_until: string | null; mediator_due: string | null; appeal_until: string | null;
  decision: { buyer_refund: string; note: string; decided_at: string | null; buyer_accepted: boolean; seller_accepted: boolean } | null;
  appeal: { by: Who; reason: string; at: string | null } | null;
  resolution: { outcome: string | null; buyer_refund: string | null; seller_gets: string; note: string; at: string | null } | null;
  offers: { id: string; by: Who; mine: boolean; buyer_refund: string; note: string; status: string; at: string }[];
  evidence: { id: string; by: Who; mine: boolean; kind: "statement" | "photo"; text: string; width: number | null; height: number | null; at: string; file: string | null }[];
  timeline: { kind: string; by: Who; text: string; at: string }[];
}

export interface Overview {
  role: Role; disputes: Partial<Record<Stage, number>>; disputes_overdue: number; deposits_pending: number;
  withdrawals_requested: number; reports_open: number; freezes_open: number; freeze_appeals: number; users: number; staff: number;
}

export interface FreezeCase {
  id: string; user_id: string; user: { id: string; name: string; phone: string | null; status: string };
  status: "frozen" | "appealed" | "unfrozen" | "upheld"; reason: string; frozen_at: string; frozen_by: string | null;
  frozen_by_id: string | null; appeal_text: string; appealed_at: string | null; decision_note: string;
  decided_at: string | null; decided_by: string | null;
}

export interface Deposit {
  id: string; user_id: string; amount: string; method: string; external_ref: string; status: string;
  created_by: string; approved_by: string | null; created_at: string;
}

export interface Withdrawal {
  id: string; user_id: string; amount: string; fee: string; bank_account: string; status: string; bank_ref: string | null; created_at: string;
}

export interface Report { id: string; listing_id: string; reporter_id: string; reason: string; note: string; status: string; created_at: string }

export interface Listing {
  id: string; title: string; description: string; price: string; status: string; province: string;
  photos: { id: string; url: string; thumb_url: string }[];
  seller: { id: string; name: string; badge?: string };
}

export interface Profile {
  user: User; created_at: string; wallet: string; penalties_owed: string; orders_as_buyer: number; orders_as_seller: number;
  disputes: number; trust_badge: string; trust_score: number; completed_sales: number;
}

export interface Order {
  id: string; buyer_id: string; seller_id: string; title: string; amount: string; status: string; created_at: string;
  fee_charged: string; buyer_refunded: string; seller_paid: string;
}

export interface AuditEntry { id: number; actor_id: string; actor: string; action: string; target_type: string; target_id: string; detail: string; created_at: string }
