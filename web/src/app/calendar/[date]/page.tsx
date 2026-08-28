import { notFound } from "next/navigation";
import { DayView } from "@/components/calendar/DayView";

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export default async function CalendarDayPage({
  params,
}: {
  params: Promise<{ date: string }>;
}) {
  const { date } = await params;
  if (!ISO_DATE.test(date) || Number.isNaN(Date.parse(date))) notFound();
  return <DayView date={date} />;
}
