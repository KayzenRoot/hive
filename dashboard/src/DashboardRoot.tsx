import { useState } from "react";

import ControlCenter from "./ControlCenter";

export default function DashboardRoot() {
  const [selectedProjectId, setSelectedProjectId] = useState(() => {
    try {
      return window.localStorage.getItem("hive.control-center.project") ?? "";
    } catch {
      return "";
    }
  });

  const selectProject = (projectId: string) => {
    setSelectedProjectId(projectId);
    try {
      if (projectId) window.localStorage.setItem("hive.control-center.project", projectId);
      else window.localStorage.removeItem("hive.control-center.project");
    } catch {
      // The selector remains functional when browser storage is disabled.
    }
  };

  return <ControlCenter selectedProjectId={selectedProjectId} onSelectProject={selectProject} />;
}
