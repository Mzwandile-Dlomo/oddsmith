import { TeamView } from "@/components/teams/TeamView";

export const metadata = { title: "Team — Oddsmith" };

export default async function TeamPage({
  params,
  searchParams,
}: {
  params: Promise<{ team: string }>;
  searchParams: Promise<{ league?: string }>;
}) {
  const { team } = await params;
  const { league } = await searchParams;
  return <TeamView team={decodeURIComponent(team)} league={league || null} />;
}
