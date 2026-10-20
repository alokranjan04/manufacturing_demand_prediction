import { useEffect, useState } from 'react'
import { getDeviations } from '../api/agent'
import type { ForecastDeviation } from '../api/types'
import KPIBar from '../components/KPIBar'
import PipelineControl from '../components/PipelineControl'
import TrendBackdrop from '../components/TrendBackdrop'


function DashboardPage() {
  const [deviations, setDeviations] = useState<ForecastDeviation[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getDeviations()
      .then(setDeviations)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="header-top-row">
          <h1>Chemical Manufacturing Intelligence</h1>
        </div>
        <p className="subtitle">Databricks-powered demand forecasting and agentic supply planning</p>
        <TrendBackdrop />
      </header>

      <KPIBar />

      <PipelineControl />

      <div className="panel">
        <h2>Current Forecast Deviations</h2>
        <p className="subtitle" style={{ marginBottom: 16 }}>
          SKU/region combinations where the latest forecast deviated ≥10% from the prior run.
          Go to <strong>Agent Recommendations</strong> to review and approve the AI-generated supply actions.
        </p>

        {loading ? (
          <p style={{ color: 'var(--text)' }}>Loading…</p>
        ) : deviations.length === 0 ? (
          <p style={{ color: 'var(--text)' }}>No significant deviations detected in the latest pipeline run.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--border)', color: 'var(--text)', textAlign: 'left' }}>
                  <th style={{ padding: '8px 12px' }}>SKU</th>
                  <th style={{ padding: '8px 12px' }}>Region</th>
                  <th style={{ padding: '8px 12px' }}>Segment</th>
                  <th style={{ padding: '8px 12px' }}>Deviation</th>
                  <th style={{ padding: '8px 12px' }}>Current (t)</th>
                  <th style={{ padding: '8px 12px' }}>Prior (t)</th>
                </tr>
              </thead>
              <tbody>
                {deviations.map(d => (
                  <tr key={d.deviation_id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '8px 12px', fontWeight: 600 }}>{d.sku}</td>
                    <td style={{ padding: '8px 12px' }}>{d.region}</td>
                    <td style={{ padding: '8px 12px' }}>{d.customer_segment}</td>
                    <td style={{ padding: '8px 12px', color: d.direction === 'UP' ? '#16a34a' : '#dc2626', fontWeight: 700 }}>
                      {d.direction === 'UP' ? '▲' : '▼'} {Math.abs(d.deviation_pct).toFixed(1)}%
                    </td>
                    <td style={{ padding: '8px 12px' }}>{d.current_predicted_tonnes.toFixed(1)}</td>
                    <td style={{ padding: '8px 12px' }}>{d.prior_predicted_tonnes.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default DashboardPage
