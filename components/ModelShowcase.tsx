'use client';

/**
 * ModelShowcase — bahis sponsoru banner'ının hemen altında, arka planı kaldırılmış
 * (şeffaf) model görseli. Tıklanınca sponsor sitesine gider. Çok hafif "nefes alma"
 * animasyonu ile canlı durur (giphy tarzı küçük hareket).
 */
const SPONSOR_URL = 'https://grandpashabet8239.com/?btag=52146205_483350';

export default function ModelShowcase() {
  return (
    <section className="model-showcase" data-testid="model-showcase" aria-label="Sponsor model">
      <a
        href={SPONSOR_URL}
        target="_blank"
        rel="noopener noreferrer sponsored"
        className="model-showcase-link"
        data-testid="model-showcase-link"
        aria-label="Grandpashabet"
      >
        <span className="model-glow" aria-hidden="true" />
        <img
          className="model-showcase-img"
          src="/ad_model_cutout.png"
          alt="Sponsor"
          loading="eager"
          decoding="async"
          draggable={false}
        />
      </a>
    </section>
  );
}
