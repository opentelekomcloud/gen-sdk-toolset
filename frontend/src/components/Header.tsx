import type { MouseEvent } from "react";
import { useLocation, useNavigate } from "react-router";
import { ODSSlimGlobalHeader } from "@telekom-ods/react-ui-kit/ODSSlimGlobalHeader";
import { ODSGlobalHeaderMenu } from "@telekom-ods/react-ui-kit/ODSGlobalHeaderMenu";
import { ODSGlobalHeaderMenuLabel } from "@telekom-ods/react-ui-kit/ODSGlobalHeaderMenuLabel";
import { ODSGlobalHeaderSecondaryMenu } from "@telekom-ods/react-ui-kit/ODSGlobalHeaderSecondaryMenu";
import { ODSGlobalHeaderMenuButton } from "@telekom-ods/react-ui-kit/ODSGlobalHeaderMenuButton";
import { ODSLanguage, ODSLightDarkMode, ODSLogout, ODSSettings, ODSVisibilityOn } from "@telekom-ods/react-icons";
import { useSummary } from "../features/scan/api/queries";
import { useSession } from "../shared/auth/useSession";
import { useI18n } from "../shared/i18n";
import { useTheme } from "../shared/theme";
import { Spinner } from "../shared/ui/Spinner";
import { inPanel, NAV } from "./nav";

/** The ODS application header: logo, app name, the panels, and the account/display controls. */
function ShellHeader() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { lang, setLang, t } = useI18n();
  const { mode, setMode } = useTheme();
  const { signOut } = useSession();

  /* Menu items stay real links - middle-click and "copy link" keep working -
     and a plain click routes inside the app instead of reloading it. */
  const go = (path: string) => (e: MouseEvent) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    navigate(path);
  };

  return (
    <ODSSlimGlobalHeader
      position="sticky"
      applicationName="gen-sdk-tooling"
      logoProps={{ href: "/scan", onClick: go("/scan"), "aria-label": "gen-sdk-tooling" }}
      menuSlot={
        /* aria-label, not the declared menuAriaLabel: this version passes the
           latter through to the <nav> as an unknown DOM attribute */
        <ODSGlobalHeaderMenu aria-label={t("header.mainMenu")}>
          {NAV.map((item) =>
            item.enabled ? (
              <ODSGlobalHeaderMenuLabel
                key={item.key}
                label={t(item.key)}
                href={item.path}
                onClick={go(item.path)}
                selected={inPanel(pathname, item.path)}
              />
            ) : (
              <ODSGlobalHeaderMenuLabel
                key={item.key}
                label={`${t(item.key)} · ${t("tab.soon")}`}
                title={t("tab.comingSoon")}
                aria-disabled="true"
                className="cursor-not-allowed opacity-50"
              />
            ),
          )}
        </ODSGlobalHeaderMenu>
      }
      secondaryMenuSlot={
        <ODSGlobalHeaderSecondaryMenu aria-label={t("header.secondaryMenu")}>
          {/* a link, lit while the settings are open - as in the prototype */}
          <ODSGlobalHeaderMenuButton
            as="a"
            href="/settings"
            onClick={go("/settings")}
            icon={<ODSSettings />}
            label={t("settings.title")}
            title={t("settings.title")}
            selected={inPanel(pathname, "/settings")}
            aria-current={inPanel(pathname, "/settings") ? "page" : undefined}
          />
          <ODSGlobalHeaderMenuButton
            icon={<ODSLightDarkMode />}
            label={mode === "dark" ? t("theme.toLight") : t("theme.toDark")}
            onClick={() => setMode(mode === "dark" ? "light" : "dark")}
          />
          <ODSGlobalHeaderMenuButton
            icon={<ODSLanguage />}
            label={t("header.switchLang")}
            onClick={() => setLang(lang === "en" ? "de" : "en")}
          />
          <ODSGlobalHeaderMenuButton icon={<ODSLogout />} label={t("auth.signOut")} onClick={signOut} />
        </ODSGlobalHeaderSecondaryMenu>
      }
    />
  );
}

/** What the old header said beside the app name and in its pills: what this
 *  panel covers, the scanner's state and who is signed in. Read-only facts, so
 *  a plain strip - the ODS header has room for the app name only. */
function StatusStrip() {
  const { data: summary } = useSummary();
  const { name, canWrite } = useSession();
  const { t } = useI18n();
  return (
    <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-1 border-b border-neutral-200 bg-surface-subtle px-6 py-1.5 text-xs text-ink-recessive">
      <span className="mr-auto">{t("header.subtitle")}</span>
      {summary && summary.scans_running > 0 && (
        <span className="flex items-center gap-1.5 text-info">
          <Spinner />
          {t("header.scansRunning", { n: summary.scans_running })}
        </span>
      )}
      {summary && <span className="font-mono">{t("header.scanner", { v: summary.scanner_version })}</span>}
      {/* The viewer badge is here rather than on each disabled control: it
          answers "why can I not do anything" once, instead of at every button. */}
      {!canWrite && (
        <span title={t("auth.viewerHint")} className="flex items-center gap-1 font-semibold">
          <ODSVisibilityOn size={14} aria-hidden="true" /> {t("auth.viewer")}
        </span>
      )}
      <span className="font-mono">{name}</span>
    </div>
  );
}

/** The app header: the ODS shell bar, then the status strip. No bulk actions here by design (PS9). */
export function Header() {
  return (
    <>
      <ShellHeader />
      <StatusStrip />
    </>
  );
}
