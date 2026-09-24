'use client';
import { useState } from 'react';
import { postClient } from '@/lib/api';

type Prediction = {
  winner: 'home' | 'away' | 'draw' | string;
  predicted_score: string;
  confidence: number;
  key_factors: string[];
  analysis: string;
  consensus?: string;
};

type AIResponse = {
  available: boolean;
  error?: string;
  home?: string;
  away?: string;
  league?: string;
  models_used?: string[];
  individual?: (Prediction & { _model?: string })[];
  harmonized?: Prediction;
  _cached?: boolean;
};

const WINNER_LABEL: Record<string, string> = {
  home: 'EV SAHİBİ',
  away: 'DEPLASMAN',
  draw: 'BERABERLİK',
};

const MODEL_LABEL: Record<string, string> = {
  'openai/gpt-5.2': 'GPT-5.2',
  'gemini/gemini-3.1-pro-preview': 'GEMİNİ 3 PRO',
  'anthropic/claude-sonnet-4-5-20250929': 'CLAUDE 4.5',
};

const modelDisplay = (m?: string) => {
  if (!m) return 'AI';
  return MODEL_LABEL[m] || m.split('/').pop()?.toUpperCase() || 'AI';
};

export default function AIPrediction({ home, away, league }: { home: string; away: string; league?: string }) {
  const [data, setData] = useState<AIResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  const runPrediction = async () => {
    setLoading(true);
    try {
      const res = await postClient<AIResponse>('/api/ai/predict', { home, away, league: league || '' });
      setData(res);
    } catch {
      setData({ available: false, error: 'Tahmin sırasında hata oluştu' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ai-prediction" data-testid="ai-prediction" style={{
      padding: 20,
      margin: '0 12px 20px',
      background: 'linear-gradient(135deg, rgba(0,240,255,0.06), rgba(255,0,170,0.06))',
      border: '1px solid rgba(0,240,255,0.25)',
      borderRadius: 8,
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 14, gap: 12, flexWrap: 'wrap',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          fontFamily: 'Orbitron, sans-serif', fontSize: 12,
          color: 'var(--cyan)', letterSpacing: 2,
        }}>
          <span style={{
            display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
            background: 'var(--cyan)', boxShadow: '0 0 8px var(--cyan)',
          }} />
          YAPAY ZEKA TAHMİNİ · 3-MODEL HARMAN
        </div>
        {!data && (
          <button
            onClick={runPrediction}
            disabled={loading}
            data-testid="ai-predict-btn"
            style={{
              padding: '8px 18px',
              background: 'linear-gradient(135deg, var(--cyan), var(--pink))',
              color: '#000',
              border: 'none',
              fontFamily: 'Orbitron, sans-serif',
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: 2,
              cursor: loading ? 'wait' : 'pointer',
              opacity: loading ? 0.6 : 1,
              boxShadow: '0 0 16px rgba(0,240,255,0.4)',
              transition: 'transform 0.2s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.transform = 'scale(1.05)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
          >
            {loading ? '⟳ ANALİZ EDİLİYOR...' : '⚡ TAHMİN ÜRET'}
          </button>
        )}
      </div>

      {loading && (
        <div data-testid="ai-loading" style={{
          padding: 30, textAlign: 'center', color: 'var(--text-dim)',
          fontFamily: 'VT323, monospace', fontSize: 14, letterSpacing: 1,
        }}>
          <div style={{ marginBottom: 8 }}>GPT-5.2 · GEMİNİ 3 PRO · CLAUDE SONNET 4.5</div>
          <div style={{ fontSize: 11, color: 'var(--pink)' }}>3 model paralel çalışıyor...</div>
        </div>
      )}

      {data && !data.available && (
        <div data-testid="ai-error" style={{
          color: 'var(--orange)', fontSize: 12, textAlign: 'center', padding: 20,
        }}>
          {data.error || 'Tahmin üretilemedi'}
        </div>
      )}

      {data && data.available && data.harmonized && (
        <>
          {/* Harmonized verdict */}
          <div data-testid="ai-verdict" style={{
            background: 'rgba(0,0,0,0.35)',
            border: '1px solid rgba(255,0,170,0.3)',
            padding: 16, borderRadius: 6,
          }}>
            <div style={{
              display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'center', gap: 12,
              marginBottom: 12,
            }}>
              <div style={{
                textAlign: 'center', fontFamily: 'Orbitron, sans-serif',
                fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2,
              }}>
                KAZANAN
              </div>
              <div style={{
                fontFamily: 'Orbitron, sans-serif', fontSize: 22, fontWeight: 900,
                color: 'var(--cyan)', letterSpacing: 3, textShadow: '0 0 10px var(--cyan)',
                textAlign: 'center', minWidth: 120,
              }} data-testid="ai-winner">
                {WINNER_LABEL[data.harmonized.winner] || data.harmonized.winner?.toUpperCase()}
              </div>
              <div style={{
                textAlign: 'center', fontFamily: 'Orbitron, sans-serif',
                fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2,
              }}>
                GÜVEN: <span style={{ color: 'var(--pink)', fontWeight: 700 }} data-testid="ai-confidence">%{data.harmonized.confidence}</span>
              </div>
            </div>

            <div style={{
              textAlign: 'center', fontFamily: 'Orbitron, sans-serif',
              fontSize: 36, fontWeight: 900, color: 'var(--pink)',
              textShadow: '0 0 14px var(--pink)', letterSpacing: 4, margin: '8px 0',
            }} data-testid="ai-score">
              {data.harmonized.predicted_score}
            </div>

            <div style={{
              fontSize: 13, color: '#cfc9e0', lineHeight: 1.6,
              padding: 10, fontFamily: 'VT323, monospace', letterSpacing: 0.5,
              borderTop: '1px solid rgba(255,255,255,0.06)', marginTop: 10,
            }} data-testid="ai-analysis">
              {data.harmonized.analysis}
            </div>

            {data.harmonized.key_factors && data.harmonized.key_factors.length > 0 && (
              <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 6 }} data-testid="ai-factors">
                {data.harmonized.key_factors.map((f, i) => (
                  <span key={i} style={{
                    padding: '3px 9px', fontSize: 10,
                    background: 'rgba(0,240,255,0.08)',
                    border: '1px solid rgba(0,240,255,0.3)',
                    color: 'var(--cyan)', borderRadius: 3,
                    fontFamily: 'VT323, monospace', letterSpacing: 0.5,
                  }}>{f}</span>
                ))}
              </div>
            )}

            {data.harmonized.consensus && (
              <div style={{
                marginTop: 12, padding: 8, fontSize: 11,
                background: 'rgba(170,0,255,0.06)', borderLeft: '2px solid var(--purple)',
                color: '#b4a8d4', fontFamily: 'VT323, monospace', fontStyle: 'italic',
              }} data-testid="ai-consensus">
                <strong style={{ color: 'var(--purple)' }}>KONSENSÜS:</strong> {data.harmonized.consensus}
              </div>
            )}
          </div>

          {/* Model attribution */}
          <div style={{
            marginTop: 10, display: 'flex', justifyContent: 'space-between',
            alignItems: 'center', fontSize: 9, color: 'var(--text-dim)',
            letterSpacing: 1, fontFamily: 'VT323, monospace',
          }}>
            <span data-testid="ai-models-used">
              MODELLER: {(data.models_used || []).map(modelDisplay).join(' · ')}
              {data._cached && <span style={{ color: 'var(--green)', marginLeft: 8 }}>● CACHED</span>}
            </span>
            <button
              onClick={() => setShowDetails((s) => !s)}
              data-testid="ai-toggle-details"
              style={{
                background: 'none', border: '1px solid rgba(255,255,255,0.15)',
                color: 'var(--text-dim)', padding: '3px 8px', fontSize: 9,
                cursor: 'pointer', fontFamily: 'inherit', letterSpacing: 1,
              }}
            >
              {showDetails ? 'GİZLE' : 'MODEL DETAYLARI'}
            </button>
          </div>

          {/* Per-model breakdown */}
          {showDetails && data.individual && (
            <div style={{ marginTop: 12, display: 'grid', gap: 8 }} data-testid="ai-individual">
              {data.individual.map((p, i) => (
                <div key={i} style={{
                  padding: 10, background: 'rgba(255,255,255,0.02)',
                  border: '1px solid rgba(255,255,255,0.08)', borderRadius: 4,
                }} data-testid={`ai-model-${i}`}>
                  <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    marginBottom: 6, fontSize: 10, color: 'var(--pink)',
                    fontFamily: 'Orbitron, sans-serif', letterSpacing: 2,
                  }}>
                    <span>{modelDisplay((p as any)._model)}</span>
                    <span style={{ color: 'var(--cyan)' }}>
                      {p.predicted_score} · %{p.confidence} GÜVEN
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: '#cfc9e0', lineHeight: 1.5, fontFamily: 'VT323, monospace' }}>
                    {p.analysis}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
