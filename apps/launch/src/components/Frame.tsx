import React, {useEffect, useState} from 'react';
import {AbsoluteFill, Img, staticFile, useDelayRender, useVideoConfig} from 'remotion';
import {tokens as t} from '../design/tokens';

let fonts: Promise<void> | undefined;
function prepareFonts() {
  fonts ??= Promise.all([400, 500, 600, 700].map(async weight => {
    const face = new FontFace('Figtree', `url('${staticFile(`fonts/figtree-latin-${weight}-normal.woff2`)}')`, {weight: String(weight)});
    await face.load();
    document.fonts.add(face);
  })).then(() => undefined);
  return fonts;
}

export function FilmFrame({children, dark = false}: {children: React.ReactNode; dark?: boolean}) {
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  const [handle] = useState(() => delayRender('Loading the bundled Figtree fonts'));
  useEffect(() => {prepareFonts().then(() => continueRender(handle)).catch(cancelRender);}, [handle, continueRender, cancelRender]);
  return <AbsoluteFill style={{background: dark ? t.dark : t.paper, color: dark ? 'white' : t.ink, fontFamily: t.font}}>
    <style>{'*{box-sizing:border-box}'}</style>{children}
  </AbsoluteFill>;
}

export function Brand({large = false, dark = false}: {large?: boolean; dark?: boolean}) {
  return <div style={{display: 'flex', alignItems: 'center', gap: large ? 24 : 12, fontSize: large ? 108 : 38, fontWeight: 700, letterSpacing: large ? -5 : -1.4, color: dark ? 'white' : t.ink}}>
    <Img src={staticFile('capychem-mark.png')} style={{width: large ? 130 : 54, height: large ? 130 : 54, objectFit: 'contain'}} />
    <span>capychem</span>
  </div>;
}

export function Header({label}: {label: string}) {
  const {width} = useVideoConfig(); const mobile = width < 1400;
  return <div style={{position: 'absolute', left: mobile ? 64 : 72, right: mobile ? 64 : 72, top: 48, display: 'flex', alignItems: 'center', justifyContent: 'space-between'}}>
    <Brand /><span style={{fontSize: mobile ? 26 : 27, color: t.muted, letterSpacing: 1.1}}>{label}</span>
  </div>;
}

export function Scope({children, dark = false}: {children: React.ReactNode; dark?: boolean}) {
  const {width} = useVideoConfig();
  return <div style={{position: 'absolute', left: width < 1400 ? 64 : 72, bottom: width < 1400 ? 188 : 128, fontSize: width < 1400 ? 36 : 30, lineHeight: 1.3, color: dark ? '#b6c1d0' : t.muted}}>{children}</div>;
}
