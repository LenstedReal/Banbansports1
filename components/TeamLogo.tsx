'use client';
import { useState } from 'react';
import { teamLogo } from '@/lib/footy';

export default function TeamLogo({ name, size = 20, className = '' }: { name?: string | null; size?: number; className?: string }) {
  const src = teamLogo(name);
  const [failed, setFailed] = useState(false);
  // Logo bulunamazsa: takımın baş harfiyle neon rozet (placeholder — uydurma logo değil)
  if (!src || failed) {
    if (!name || name === '—') return null;
    return (
      <span
        className={`team-logo team-logo-fallback ${className}`}
        aria-hidden="true"
        style={{ width: size, height: size, fontSize: Math.max(9, Math.round(size * 0.52)) }}
      >
        {name.trim().charAt(0).toUpperCase()}
      </span>
    );
  }
  return (
    <img
      src={`${src}?v=2`}
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      className={`team-logo ${className}`}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
    />
  );
}
