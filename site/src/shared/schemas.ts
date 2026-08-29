import { z } from "zod";

/** The one place a signup's shape is defined. Routes validate with it; the
 *  query layer takes the parsed type. Keeping a second copy anywhere is how a
 *  rule enforced on one surface gets missed on another. */
export const signupSchema = z.object({
  email: z.string().trim().email().max(254),
  // How many networks they would point at a hosted panel. Free-form on
  // purpose: it is a conversation starter, not a billing input.
  networks: z.string().trim().max(120).optional(),
  note: z.string().trim().max(2000).optional(),
  source: z.string().trim().max(60).optional(),
});

export type Signup = z.infer<typeof signupSchema>;

export function emailKey(email: string): string {
  return email.trim().toLowerCase();
}
