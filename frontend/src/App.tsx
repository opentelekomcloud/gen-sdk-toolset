import { Navigate, Route, Routes } from "react-router";
import "./App.css";
import { I18nProvider, useI18n } from "./shared/i18n";
import { Header } from "./components/Header";
import { TabBar } from "./components/TabBar";
import { AttentionBand } from "./features/scan/components/AttentionBand";
import { RegistryPage } from "./features/scan/pages/RegistryPage";
import { ServicePage } from "./features/scan/pages/ServicePage";

function NotFound() {
  const { t } = useI18n();
  return <div className="px-6 py-16 text-center text-sm text-gray-400">{t("app.notFound")}</div>;
}

/** Shell order is deliberate: header → attention band (app-level) → tabs → content. */
function App() {
  return (
    <I18nProvider>
      <div className="min-h-screen">
        <Header />
        <AttentionBand />
        <TabBar />
        <Routes>
          <Route path="/" element={<Navigate to="/scan" replace />} />
          <Route path="/scan" element={<RegistryPage />} />
          <Route path="/scan/services/:name" element={<ServicePage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </div>
    </I18nProvider>
  );
}

export default App;
