// LOW-FI PROTOTYPE — Workbench cockpit, RUNNING state.
import { Cockpit } from "../_cockpit";
import { RUN_RUNNING } from "../_mock";

export default function WorkbenchRunningProto() {
  return <Cockpit snap={RUN_RUNNING} running />;
}
