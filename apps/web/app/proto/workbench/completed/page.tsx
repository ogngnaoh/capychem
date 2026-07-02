// LOW-FI PROTOTYPE — Workbench cockpit, COMPLETED state.
import { Cockpit } from "../../_cockpit";
import { RUN_COMPLETED } from "../../_mock";

export default function WorkbenchCompletedProto() {
  return <Cockpit snap={RUN_COMPLETED} running={false} />;
}
