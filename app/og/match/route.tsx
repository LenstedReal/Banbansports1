import { ImageResponse } from 'next/og';

export const runtime = 'edge';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const home = (searchParams.get('home') || 'Ev').slice(0, 30);
  const away = (searchParams.get('away') || 'Deplasman').slice(0, 30);
  const score = (searchParams.get('score') || '').slice(0, 12);
  const league = (searchParams.get('league') || '').slice(0, 60).toUpperCase();

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%', height: '100%',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          background: 'linear-gradient(135deg, #0a0510 0%, #1a0830 50%, #2a0a40 100%)',
          color: '#fff',
          fontFamily: 'system-ui, sans-serif',
        }}
      >
        <div style={{
          position: 'absolute', top: 30, left: 40,
          fontSize: 22, letterSpacing: 4,
          color: '#00f0ff',
          textShadow: '0 0 16px #00f0ff',
        }}>
          banbansports · UNDERGROUND HD
        </div>

        {league && (
          <div style={{
            fontSize: 22, letterSpacing: 6, color: '#ff00aa',
            marginBottom: 30, textShadow: '0 0 12px #ff00aa',
          }}>
            {league}
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 50, marginBottom: 20 }}>
          <div style={{ fontSize: 56, color: '#fff', textAlign: 'right', maxWidth: 380 }}>
            {home}
          </div>
          <div style={{
            fontSize: 90, color: '#00f0ff', letterSpacing: 6,
            textShadow: '0 0 22px #00f0ff',
            padding: '0 30px',
          }}>
            {score || 'vs'}
          </div>
          <div style={{ fontSize: 56, color: '#fff', textAlign: 'left', maxWidth: 380 }}>
            {away}
          </div>
        </div>

        <div style={{
          position: 'absolute', bottom: 36,
          fontSize: 18, letterSpacing: 4, color: '#aa80ff',
        }}>
          CANLI MAÇ DETAYI · banbansports.app
        </div>

        {/* Decorative scanlines */}
        <div style={{
          position: 'absolute', inset: 0,
          background: 'repeating-linear-gradient(0deg, rgba(255,255,255,0.02) 0px, rgba(255,255,255,0.02) 1px, transparent 1px, transparent 3px)',
        }} />
      </div>
    ),
    { width: 1200, height: 630 }
  );
}
