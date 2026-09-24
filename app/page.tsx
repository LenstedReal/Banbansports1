'use client';

import { useState, useEffect } from 'react';
import { AuthProvider } from '@/components/AuthProvider';
import Header from '@/components/Header';
import MatchBanner from '@/components/MatchBanner';
import MatchCenter from '@/components/MatchCenter';
import VideoPlayer from '@/components/VideoPlayer';
import ChannelRail from '@/components/ChannelRail';
import ServerPanel from '@/components/ServerPanel';
import DailyMatchStrip from '@/components/DailyMatchStrip';
import CinemaSection from '@/components/CinemaSection';
import SponsorBanner from '@/components/SponsorBanner';
import OkeyBanner from '@/components/OkeyBanner';
import Sponsors from '@/components/Sponsors';
import NotificationCenter from '@/components/NotificationCenter';
import SwRegister from '@/components/SwRegister';
import PushPrompt from '@/components/PushPrompt';
import FpsCounter from '@/components/FpsCounter';
import CommunityChat from '@/components/chat/CommunityChat';
import RadioWidget from '@/components/radio/RadioWidget';
import type { Match } from '@/lib/api';

type TopScores = { matches: Match[] };
type TodayMatches = { Stages: any[] };

/* =====================================================================
   ANA SAYFA — tek kolon, section-based akış (3 kolon dashboard YOK)
   HEADER → HERO MAÇ → MAÇ MERKEZİ → BÜYÜK PLAYER → BANNERLAR → KANAL RAYI
   → GÜNÜN MAÇLARI → YENİ FİLM / BOX OFFICE → TOPLULUK → RADYO → SUNUCULAR
   → SPONSORLAR / SOSYAL / SUPPLIERS / FOOTER (repo bölümleri korunur)
   ===================================================================== */
export default function HomePage() {
  const [topScores, setTopScores] = useState<TopScores>({ matches: [] });
  const [todayMatches, setTodayMatches] = useState<TodayMatches>({ Stages: [] });
  const [initialFetchDone, setInitialFetchDone] = useState(false);

  useEffect(() => {
    let alive = true;
    const loadInitial = async () => {
      try {
        const [scoresRes, matchesRes] = await Promise.all([
          fetch('/api/scores/top?n=5', { cache: 'no-store' }).catch(() => null),
          fetch('/api/livescore/today', { cache: 'no-store' }).catch(() => null),
        ]);
        if (!alive) return;
        if (scoresRes && scoresRes.ok) {
          const scoresData = await scoresRes.json();
          setTopScores({ matches: scoresData?.matches || [] });
        }
        if (matchesRes && matchesRes.ok) {
          const matchesData = await matchesRes.json();
          setTodayMatches({ Stages: matchesData?.Stages || [] });
        }
      } catch (err) {
        console.warn('İlk veri çekiminde hata:', err);
      } finally {
        if (alive) setInitialFetchDone(true);
      }
    };
    loadInitial();
    return () => { alive = false; };
  }, []);

  return (
    <AuthProvider>
      <SwRegister />
      <PushPrompt />

      <div className="bb-shell" data-testid="app-shell" id="top">
        <div className="scanlines" />
        <NotificationCenter />
        <FpsCounter />

        <Header />

        <main className="bb-main" data-testid="main-content">
          {/* HERO — günün öne çıkan maçı */}
          <section className="bb-section bb-top-match" data-testid="top-match-section">
            <MatchBanner initialMatches={topScores.matches} />
          </section>

          {/* MAÇ MERKEZİ */}
          <section className="bb-section bb-match-center" id="mac-merkezi" data-testid="match-center-section">
            <MatchCenter initialStages={todayMatches.Stages} />
          </section>

          {/* BÜYÜK CANLI YAYIN PLAYER */}
          <section className="bb-section bb-player-section" id="canli-yayin" data-testid="player-section">
            <VideoPlayer />
          </section>

          {/* SUNUCULAR — player altında tam genişlik, yan yana */}
          <section className="bb-section bb-server-panel" data-testid="server-section">
            <ServerPanel />
          </section>
          {/* SPONSOR — Grandpashabet */}
          <section className="bb-section bb-sponsor-banner" data-testid="sponsor-banner-section">
            <SponsorBanner />
          </section>

          {/* REKLAM — OKEY */}
          <section className="bb-section bb-okey-banner" data-testid="okey-banner-section">
            <OkeyBanner />
          </section>

          {/* TV KANALLARI — yatay ray */}
          <section className="bb-section bb-tv-channels" id="tv-kanallari" data-testid="channels-section">
            <ChannelRail />
          </section>

          {/* GÜNÜN MAÇLARI */}
          <section className="bb-section bb-daily-matches" data-testid="daily-matches-section">
            <DailyMatchStrip />
          </section>

          {/* YENİ FİLM + BOX OFFICE */}
          <section className="bb-section bb-cinema" id="filmler" data-testid="cinema-section">
            <CinemaSection />
          </section>

          {/* DİZİLER — yakında */}
          <section className="bb-section" id="diziler" data-testid="series-section">
            <div className="pnl g-soon" data-testid="series-soon">
              <div className="pnl-head">
                <span className="pnl-title">DİZİLER</span>
                <span className="g-eyebrow">YAKINDA</span>
              </div>
              <div className="g-soon-body">Yeni diziler, popüler diziler ve son bölümler burada yayınlanacak.</div>
            </div>
          </section>

          {/* TOPLULUK SOHBETİ */}
          <section className="bb-section bb-community" id="topluluk" data-testid="community-section">
            <CommunityChat />
          </section>

          {/* CANLI RADYO */}
          <section className="bb-section bb-radio" id="radyo" data-testid="radio-section">
            <RadioWidget />
          </section>

        </main>

        {/* SPONSORLAR · SOSYAL · FOOTBALL SUPPLIERS · FOOTER — repo bölümleri */}
        <Sponsors />

        {!initialFetchDone && (
          <div data-testid="initial-loading" style={{ display: 'none' }}>loading</div>
        )}
      </div>
    </AuthProvider>
  );
}
