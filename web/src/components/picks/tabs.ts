// Shared by the server page (reads ?tab=) and the client view, so it cannot
// live in the "use client" module.
export const PICK_TABS = ["daily", "strong", "value", "pool"] as const;
export type PickTab = (typeof PICK_TABS)[number];
