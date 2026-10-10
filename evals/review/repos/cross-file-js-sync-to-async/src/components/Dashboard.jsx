import { loadFlags } from "../features/flags";
import { NewDashboard } from "./NewDashboard";
import { OldDashboard } from "./OldDashboard";

export function Dashboard({ user }) {
  const flags = loadFlags();
  return flags.newDashboard ? <NewDashboard user={user} /> : <OldDashboard user={user} />;
}
