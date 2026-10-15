import { render, screen } from "@testing-library/react";
import type { Dispute } from "@/lib/types";
import { StageTrack } from "./StageTrack";

const base = {
  id: "d", order_id: "o", title: "Solar lamp", amount: "200.00", reason: "Cracked", buyer: { id: "b", name: "Ruth" },
  seller: { id: "s", name: "Kila" }, opened_by: "buyer", opened_at: "2026-10-14T00:00:00Z", deadline: null, overdue: false,
  mediator: null, mediator_id: null, outcome: null, buyer_refund: null, you: "staff", actions: [],
  negotiate_until: "2026-10-17T00:00:00Z", mediator_due: "2026-10-23T07:00:00Z", appeal_until: null, decision: null,
  appeal: null, resolution: null, offers: [], evidence: [], timeline: [],
} satisfies Omit<Dispute, "stage">;

test("a late mediator stage is marked in red with how late it is", () => {
  render(<StageTrack dispute={{ ...base, stage: "mediation" }} now={new Date("2026-10-24T07:00:00Z")} />);
  const current = screen.getByText("Mediator decides").closest("li")!;
  expect(current).toHaveAttribute("aria-current", "step");
  expect(current).toHaveTextContent("24 h late");
  expect(screen.getByText("Buyer and seller negotiate").closest("li")).toHaveTextContent("Done");
});

test("negotiation shows time left", () => {
  render(<StageTrack dispute={{ ...base, stage: "negotiation" }} now={new Date("2026-10-15T00:00:00Z")} />);
  expect(screen.getByText("Buyer and seller negotiate").closest("li")).toHaveTextContent("2 days left");
});
