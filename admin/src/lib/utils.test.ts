import { compareMoney, isMoney, kina, minus, until } from "./utils";

test("money stays exact to the cent", () => {
  expect(minus("200.00", "60.5")).toBe("139.50");
  expect(minus("0.30", "0.10")).toBe("0.20"); // 0.3 - 0.1 in floats is 0.19999…
  expect(minus("10", "12.25")).toBe("-2.25");
  expect(compareMoney("200.01", "200.00")).toBeGreaterThan(0);
  expect(compareMoney("80", "80.00")).toBe(0);
  expect(kina("1234.5")).toBe("K1,234.50");
  expect(isMoney("12.345")).toBe(false);
  expect(isMoney("12.34")).toBe(true);
});

test("deadlines read as time left or late", () => {
  const now = new Date("2026-10-15T00:00:00Z");
  expect(until("2026-10-17T00:00:00Z", now)).toBe("2 days left");
  expect(until("2026-10-14T19:00:00Z", now)).toBe("5 h late");
});
