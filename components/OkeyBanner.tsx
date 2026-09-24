'use client';

/** OkeyBanner — OKEY Rötar reklamı. Solda kampanya metni, sağda HAREKETLİ GIF + altında OK marka değeri. */
import { trackSponsorClick } from './Sponsors';

const OKEY_URL = 'https://www.ok.com.tr/prezervatifler/';

export default function OkeyBanner() {
  return (
    <section className="okey-banner-wrap" data-testid="okey-banner" aria-label="Reklam — OKEY">
      <a
        href={OKEY_URL}
        target="_blank"
        rel="noopener noreferrer sponsored"
        className="okey2"
        onClick={() => trackSponsorClick('okey', 'OKEY Rötar')}
        data-testid="okey-banner-link"
        aria-label="OKEY Rötar — Heyecanı sabahlara kadar sürecek"
      >
        <div className="okey2-text">
          <span className="okey2-ad">REKLAM</span>
          <div className="okey2-title">
            <span>HEYECANI</span>
            <span className="okey2-green">SABAHLARA KADAR</span>
            <span className="okey2-green">SÜRECEK</span>
          </div>
          <div className="okey2-tag">#OKupaBuKupa</div>
        </div>
        <div className="okey2-visual" aria-hidden="true">
          <img className="okey2-gif" src="/ads/okey_banner.gif" alt="" loading="lazy" decoding="async" draggable={false} data-testid="okey-gif" />
        </div>
      </a>
    </section>
  );
}
