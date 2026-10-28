import { redirect } from "next/navigation";

// The day feed on the home page replaced the old fixture list.
export default function MatchesIndex() {
  redirect("/");
}
