import { useState } from "react";
import CompanyView from "./CompanyView";
import JournalView from "./JournalView";

type ModuleId = "journal" | "company";

export default function App() {
  const [moduleId, setModuleId] = useState<ModuleId>("journal");
  return (
    <main>
      <header>
        <nav className="module-nav" aria-label="功能模块">
          <button
            type="button"
            className={moduleId === "journal" ? "secondary active" : "secondary"}
            onClick={() => setModuleId("journal")}
          >
            选刊神器
          </button>
          <button
            type="button"
            className={moduleId === "company" ? "secondary active" : "secondary"}
            onClick={() => setModuleId("company")}
          >
            公司查询
          </button>
        </nav>
        <h1>
          {moduleId === "journal" ? "选刊神器" : "公司查询"}{" "}
          <span className="version">v0.1</span>
        </h1>
      </header>
      {moduleId === "journal" ? <JournalView /> : <CompanyView />}
    </main>
  );
}
