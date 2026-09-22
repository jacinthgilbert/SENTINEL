import { redirect } from "next/navigation";

/** The dashboard moved to /command when the sidebar was introduced. */
export default function Page() {
  redirect("/command");
}
