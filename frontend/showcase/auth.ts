import { demoUser } from "./fixtures";

// Only the showcase build resolves useAuth here. This is not a monitoring session.
export function useAuth() {
  return { user: demoUser, loading: false };
}
