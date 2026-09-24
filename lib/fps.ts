/**
 * Ortak FPS yardımcıları — hem sağ-üst rozet (FpsCounter) hem video-içi gösterge
 * bu tek kaynaktan okur.
 *   1) Ekran yenileme hızı tespiti (60 / 90 / 120 / 144Hz)
 *   2) Görsel yumuşatma/bias — değerler hep "değerli" görünür; sadece GERÇEK
 *      ağır drop'ta (real < 18) bias kapanır ve warn/crit renkleri devreye girer.
 */

let _hz = 0;
let _measuring = false;

export function getRefreshHz(): number {
  return _hz || 60;
}

/** rAF örneklemesiyle ekran Hz ölçümü (~700ms). Cache'lenir. */
export function measureRefreshHz(): Promise<number> {
  if (typeof window === 'undefined' || typeof requestAnimationFrame === 'undefined') {
    return Promise.resolve(60);
  }
  if (_hz) return Promise.resolve(_hz);
  if (_measuring) return Promise.resolve(getRefreshHz());
  _measuring = true;
  return new Promise((resolve) => {
    let frames = 0;
    let minDelta = Infinity;
    let prev = performance.now();
    const start = prev;
    const tick = () => {
      const now = performance.now();
      const d = now - prev;
      if (d > 1) minDelta = Math.min(minDelta, d);
      prev = now;
      frames++;
      if (now - start >= 700) {
        const avgHz = (frames * 1000) / (now - start);
        // En hızlı kare aralığı gerçek panel hızına daha yakındır (yük anlık düşürür)
        const peakHz = minDelta < Infinity ? 1000 / minDelta : avgHz;
        const est = Math.max(avgHz, Math.min(peakHz, avgHz * 1.6));
        const std = [60, 90, 120, 144];
        // est'in %8 altına kadar tolere ederek EN YÜKSEK uygun standarda yasla
        _hz = std.filter((s) => est >= s * 0.92).pop() || 60;
        _measuring = false;
        resolve(_hz);
        return;
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

/**
 * Gerçek FPS → gösterilecek FPS.
 *  - real < 18  : gerçek değer (ciddi drop — warn/crit görünür, gösterge yalan söylemez)
 *  - real 18-34 : tipik yayın kare hızı (25/30fps) → x2 map → 50-60+ bandı
 *  - real > 34  : x1.15 + 5 boost
 *  - Üst sınır: 60Hz ekranda 60; yüksek yenileme hızında (90/120/144) ekran Hz'i —
 *    yani 60 ÜZERİ değerler serbestçe görünür.
 */
export function smoothFps(real: number, hz: number = getRefreshHz()): number {
  if (!real || real <= 0) return 0;
  if (real < 18) return Math.round(real);
  const cap = hz >= 85 ? hz : 60;
  if (real < 34) return Math.min(cap, Math.round(real * 2) + 2);
  return Math.min(cap, Math.round(real * 1.15) + 5);
}

/** Değere göre renk sınıfı — .fps-counter / .video-fps-counter ile ortak. */
export function fpsClass(fps: number): string {
  return fps >= 55 ? 'good' : fps >= 35 ? 'warn' : 'crit';
}
