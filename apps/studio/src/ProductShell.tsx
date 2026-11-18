import { useEffect, useState, useRef } from "react";
import { Outlet, useLocation } from "react-router";
import {
  House,
  FlaskConical,
  Library,
  Server,
  CircleHelp,
  Menu,
  X,
  ArrowUpRight,
} from "lucide-react";
import { StudioLink, useStudio } from "./StudioContext";

const navigation = [
  { path: "/", label: "Overview", icon: House },
  { path: "/experiments", label: "Experiments", icon: FlaskConical },
  { path: "/references/cdk2", label: "References", icon: Library },
];
export function ProductShell() {
  const { pathname } = useLocation();
  const editor = /^\/experiments\/[^/]+\/?$/.test(pathname) &&
    pathname !== "/experiments/new";
  const workspace = useStudio();
  const [menu, setMenu] = useState(false);
  const [mobile, setMobile] = useState(
    () => matchMedia("(max-width:767px)").matches,
  );
  const rail = useRef<HTMLElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const media = matchMedia("(max-width:767px)");
    const change = () => setMobile(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    if (!mobile || !menu) return;
    const previous = document.activeElement as HTMLElement | null;
    const controls = () =>
      Array.from(
        rail.current?.querySelectorAll<HTMLElement>(
          "a[href],button:not([disabled])",
        ) ?? [],
      );
    controls()[0]?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setMenu(false);
      }
      if (e.key === "Tab") {
        const items = controls();
        const first = items[0],
          last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, [menu, mobile]);
  useEffect(() => {
    setMenu(false);
    window.scrollTo(0, 0);
    document
      .querySelector<HTMLElement>("#main-content")
      ?.focus({ preventScroll: true });
  }, [pathname]);
  const active = (path: string) =>
    path === "/"
      ? pathname === "/"
      : pathname.startsWith(path) ||
        (path === "/experiments" && pathname.startsWith("/studies"));
  return (
    <div
      className={`product-shell compact-rail ${editor ? "studio-editor-shell" : ""} ${menu ? "navigation-open" : ""}`}
    >
      <a
        className="skip-link"
        href={`${location.pathname}${location.search}#main-content`}
      >
        Skip to main content
      </a>
      <header className="mobile-product-header">
        <StudioLink to="/" className="product-brand">
          <img src="/brand/capychem-mark.png" alt="" />
          <span>capychem</span>
        </StudioLink>
        <button
          ref={menuButton}
          className="secondary-button"
          aria-expanded={menu}
          aria-controls="primary-navigation"
          onClick={() => setMenu(!menu)}
        >
          {menu ? <X size={19} /> : <Menu size={19} />}Menu
        </button>
      </header>
      {menu && (
        <button
          className="navigation-scrim"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        />
      )}
      <aside
        ref={rail}
        className="product-rail"
        id="primary-navigation"
        inert={mobile && !menu}
        aria-hidden={mobile && !menu ? true : undefined}
        role={mobile && menu ? "dialog" : undefined}
        aria-modal={mobile && menu ? true : undefined}
        aria-label={mobile && menu ? "Navigation" : undefined}
      >
        {mobile && (
          <button
            className="mobile-close-navigation"
            aria-label="Close navigation"
            onClick={() => setMenu(false)}
          >
            <X size={20} />
          </button>
        )}
        <StudioLink
          className="product-brand"
          to="/"
          aria-label="CapyChem overview"
        >
          <img src="/brand/capychem-mark.png" alt="" />
          <span>capychem</span>
        </StudioLink>
        <nav aria-label="Main navigation">
          {navigation.map(({ path, label, icon: Icon }) => (
            <StudioLink
              key={path}
              to={path}
              title={label}
              aria-label={label}
              className={active(path) ? "selected" : ""}
              aria-current={active(path) ? "page" : undefined}
            >
              <Icon size={20} />
              <span>{label}</span>
            </StudioLink>
          ))}
        </nav>
        <nav className="rail-bottom" aria-label="Support navigation">
          <StudioLink
            to="/engine"
            title="Local engine"
            aria-label="Local engine"
            className={active("/engine") ? "selected" : ""}
            aria-current={active("/engine") ? "page" : undefined}
          >
            <Server size={20} />
            <span>Local engine</span>
            <i
              className={`engine-dot ${workspace.health.ready ? "ready" : ""}`}
              aria-label={
                workspace.demo
                  ? "Recorded mode"
                  : workspace.health.ready
                    ? "Ready"
                    : "Needs setup"
              }
            />
          </StudioLink>
          <StudioLink
            to="/help"
            title="Help"
            aria-label="Help"
            className={active("/help") ? "selected" : ""}
            aria-current={active("/help") ? "page" : undefined}
          >
            <CircleHelp size={20} />
            <span>Help</span>
          </StudioLink>
        </nav>
      </aside>
      <div className="product-content" inert={mobile && menu}>
        {workspace.demo && (
          <div className="product-demo-banner">
            <span>
              Recorded example · saved coordinates and computational evidence.
              No calculations are launched.
            </span>
            <a href="/engine">
              Run locally <ArrowUpRight size={14} />
            </a>
          </div>
        )}
        {!workspace.demo && workspace.apiError && (
          <div className="product-global-error" role="alert">
            <span>{workspace.apiError}</span>
            <StudioLink to="/engine">Check connection</StudioLink>
            <button onClick={workspace.clearError} aria-label="Dismiss error">
              <X size={16} />
            </button>
          </div>
        )}
        <main id="main-content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
