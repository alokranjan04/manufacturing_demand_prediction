import { useCallback, useEffect, useState } from 'react'
import { getChemicalKPIs } from '../api/agent'
import type { ChemicalKPISummary } from '../api/types'
import { useCountUp } from '../hooks/useCountUp'

function fmt(v: number | null, decimals = 0): string {
  if (v === null) return '—'
  return v.toLocaleString(undefined, { maximumFractionDigits: decimals })
}

function RiskIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3 2 20h20z" /><line x1="12" y1="10" x2="12" y2="15" />
      <circle cx="12" cy="17.5" r="0.6" fill="currentColor" stroke="none" />
    </svg>
  )
}
function InventoryIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="7" width="20" height="14" rx="2" /><path d="M16 7V5a2 2 0 0 0-4 0v2" /><path d="M8 7V5a2 2 0 0 0-4 0v2" />
    </svg>
  )
}
function AccuracyIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  )
}
function AgentIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><path d="M12 8v4l3 3" />
    </svg>
  )
}

function KPIBar() {
  const [kpis, setKpis] = useState<ChemicalKPISummary | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    setError(false)
    getChemicalKPIs()
      .then(setKpis)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const riskTonnes   = useCountUp(kpis?.demand_at_risk_tonnes ?? null, 900)
  const coverDays    = useCountUp(kpis?.avg_inventory_cover_days ?? null, 900)
  const mape         = useCountUp(kpis?.forecast_mape_pct ?? null, 900)
  const pending      = useCountUp(kpis?.pending_recommendations_count ?? null, 700)

  if (error) {
    return (
      <div className="banner error-banner kpi-error">
        <span>Could not load KPI summary.</span>
        <button type="button" className="chip" onClick={load} disabled={loading}>
          {loading ? 'Retrying…' : 'Retry'}
        </button>
      </div>
    )
  }

  return (
    <div className="kpi-bar">
      <div className="kpi-tile kpi-tile--risk">
        <div className="kpi-icon"><RiskIcon /></div>
        <div className="kpi-text">
          <span className="kpi-label">Demand at Risk</span>
          <span className="kpi-value">{riskTonnes !== null ? `${fmt(riskTonnes, 1)} t` : '…'}</span>
          <span className="kpi-subvalue">above {kpis?.deviation_threshold_pct ?? 10}% deviation threshold</span>
        </div>
      </div>

      <div className="kpi-tile kpi-tile--category">
        <div className="kpi-icon"><InventoryIcon /></div>
        <div className="kpi-text">
          <span className="kpi-label">Avg Inventory Cover</span>
          <span className="kpi-value">{coverDays !== null ? `${fmt(coverDays, 1)} days` : '…'}</span>
          <span className="kpi-subvalue">across active SKUs</span>
        </div>
      </div>

      <div className="kpi-tile kpi-tile--product">
        <div className="kpi-icon"><AccuracyIcon /></div>
        <div className="kpi-text">
          <span className="kpi-label">Forecast Accuracy</span>
          <span className="kpi-value">{mape !== null ? `${fmt(100 - mape, 1)}%` : '…'}</span>
          <span className="kpi-subvalue">1 − MAPE (LightGBM Champion)</span>
        </div>
      </div>

      <div className="kpi-tile kpi-tile--revenue">
        <div className="kpi-icon"><AgentIcon /></div>
        <div className="kpi-text">
          <span className="kpi-label">Pending Agent Actions</span>
          <span className="kpi-value">{pending !== null ? Math.round(pending) : '…'}</span>
          <span className="kpi-subvalue">awaiting human approval</span>
        </div>
      </div>
    </div>
  )
}

export default KPIBar
