import type { ComponentProps } from "react";
import { Button, type ButtonProps } from "@astryxdesign/core/Button";
import { StudioLink } from "./StudioContext";

function RouterAnchor({ href, ...props }: ComponentProps<"a"> & { href: string }) {
  return <StudioLink {...props} to={href} />;
}

/** Astryx's link form uses href; StudioLink preserves recorded-mode routing. */
export function StudioActionLink({
  to,
  variant = "secondary",
  className = "",
  ...props
}: Omit<ButtonProps, "href" | "as"> & { to: string }) {
  return <Button {...props} variant={variant} className={`studio-action-link studio-action-${variant} ${className}`} href={to} as={RouterAnchor} />;
}
