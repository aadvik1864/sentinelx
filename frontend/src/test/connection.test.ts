import { describe, expect, it } from "vitest";
import { websocketUrl } from "../services/connection";

describe("live-update connection", () => {
  it("uses the hosted backend over WSS without putting tokens in the URL", () => {
    expect(websocketUrl("alerts", "https://sentinelx-api.example.test"))
      .toBe("wss://sentinelx-api.example.test/ws/alerts");
  });
  it("preserves local development ports", () => {
    expect(websocketUrl("events", "http://localhost:8080"))
      .toBe("ws://localhost:8080/ws/events");
  });
  it("rejects credentials and unsupported protocols", () => {
    expect(() => websocketUrl("incidents", "https://name:secret@example.test"))
      .toThrow();
    expect(() => websocketUrl("incidents", "file:///tmp/socket"))
      .toThrow();
  });
});
