import { useEffect, useState } from 'react'
import {
  approveRecommendation,
  getChemicalKPIs,
  getRecommendations,
  rejectRecommendation,
  triggerAgentRun,
} from '../api/agent'
import type { AgentCycleResult, AgentRecommendation, ChemicalKPISummary } from '../api/types'

// ── Urgency colour helpers ────────────────────────────────────────────────────

function urgencyColor(urgency: string): string {
  if (urgency === 'HIGH')   return '#dc2626'
  if (urgency === 'MEDIUM') return '#d97706'
  return '#16a34a'
}

function actionLabel(actionType: string): string {
  return actionType.replace(/_/g, ' ')
}

// ── KPI bar ───────────────────────────────────────────────────────────────────

function ChemicalKPIBar({ kpis }: { kpis: ChemicalKPISummary | null }) {
  if (!kpis) return null
  return (
    <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 24 }}>
      <KPICard
        label="Demand at Risk"
        value={kpis.demand_at_risk_tonnes != null ? `${kpis.demand_at_risk_tonnes.toFixed(0)} t` : '—'}
        sub={`Deviations ≥ ${kpis.deviation_threshold_pct}%`}
      />
      <KPICard
        label="Avg Inventory Cover"
        value={kpis.avg_inventory_cover_days != null ? `${kpis.avg_inventory_cover_days.toFixed(1)} days` : '—'}
        sub="Latest snapshot"
      />
      <KPICard
        label="Forecast MAPE"
        value={kpis.forecast_mape_pct != null ? `${kpis.forecast_mape_pct.toFixed(1)}%` : '—'}
        sub="Test set"
      />
      <KPICard
        label="Pending Actions"
        value={String(kpis.pending_recommendations_count)}
        sub="Awaiting approval"
        highlight={kpis.pending_recommendations_count > 0}
      />
    </div>
  )
}

function KPICard({
  label, value, sub, highlight = false,
}: { label: string; value: string; sub: string; highlight?: boolean }) {
  return (
    <div style={{
      flex: '1 1 160px',
      background: 'var(--code-bg)',
      border: `1px solid ${highlight ? 'var(--accent-border)' : 'var(--border)'}`,
      borderRadius: 8,
      padding: '14px 18px',
      textAlign: 'left',
    }}>
      <div style={{ fontSize: 12, color: 'var(--text)', marginBottom: 4 }}>{label}</div>
      <div style={{
        fontSize: 22, fontWeight: 600,
        color: highlight ? 'var(--accent)' : 'var(--text-h)',
      }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--text)', marginTop: 2 }}>{sub}</div>
    </div>
  )
}

// ── Recommendation card ───────────────────────────────────────────────────────

function RecommendationCard({
  rec,
  onApprove,
  onReject,
}: {
  rec: AgentRecommendation
  onApprove: (id: string, approver: string) => Promise<void>
  onReject: (id: string, reason: string) => Promise<void>
}) {
  const [approverName, setApproverName] = useState('Supply Planner')
  const [showReject, setShowReject] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isPending = rec.status === 'PENDING'

  async function handleApprove() {
    setBusy(true)
    setError(null)
    try {
      await onApprove(rec.id, approverName)
    } catch {
      setError('Approval failed. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  async function handleReject() {
    if (!rejectReason.trim()) {
      setError('Please enter a rejection reason.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await onReject(rec.id, rejectReason.trim())
    } catch {
      setError('Rejection failed. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{
      background: 'var(--code-bg)',
      border: '1px solid var(--border)',
      borderRadius: 10,
      padding: 20,
      marginBottom: 16,
      textAlign: 'left',
    }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
        <span style={{
          background: urgencyColor(rec.urgency),
          color: '#fff',
          fontSize: 11,
          fontWeight: 700,
          padding: '2px 8px',
          borderRadius: 4,
          letterSpacing: 0.5,
        }}>
          {rec.urgency}
        </span>
        <span style={{ fontWeight: 600, color: 'var(--text-h)', fontSize: 15 }}>{rec.sku}</span>
        <span style={{ color: 'var(--text)', fontSize: 13 }}>{rec.region}</span>
        {rec.customer_segment && (
          <span style={{
            fontSize: 11,
            color: 'var(--text)',
            border: '1px solid var(--border)',
            borderRadius: 4,
            padding: '1px 6px',
          }}>{rec.customer_segment}</span>
        )}
        {/* Decided badge */}
        {rec.status === 'APPROVED' && (
          <span style={{
            marginLeft: 'auto',
            background: '#16a34a',
            color: '#fff',
            fontSize: 11,
            fontWeight: 700,
            padding: '2px 10px',
            borderRadius: 4,
          }}>
            APPROVED {rec.approver ? `by ${rec.approver}` : ''}
          </span>
        )}
        {rec.status === 'REJECTED' && (
          <span style={{
            marginLeft: 'auto',
            background: '#dc2626',
            color: '#fff',
            fontSize: 11,
            fontWeight: 700,
            padding: '2px 10px',
            borderRadius: 4,
          }}>
            REJECTED {rec.rejection_reason ? `— ${rec.rejection_reason}` : ''}
          </span>
        )}
      </div>

      {/* Deviation summary */}
      {rec.deviation_pct != null && (
        <div style={{ fontSize: 13, marginBottom: 10, color: 'var(--text)' }}>
          Forecast deviation:&nbsp;
          <strong style={{ color: rec.direction === 'UP' ? '#16a34a' : '#dc2626' }}>
            {rec.deviation_pct > 0 ? '+' : ''}{rec.deviation_pct.toFixed(1)}% {rec.direction}
          </strong>
          {rec.quantity_adjustment_tonnes !== 0 && (
            <span>
              &nbsp;({rec.quantity_adjustment_tonnes > 0 ? '+' : ''}
              {rec.quantity_adjustment_tonnes.toFixed(0)} t adjustment recommended)
            </span>
          )}
        </div>
      )}

      {/* Constraints */}
      <div style={{
        display: 'flex',
        gap: 16,
        flexWrap: 'wrap',
        fontSize: 12,
        color: 'var(--text)',
        marginBottom: 12,
        padding: '8px 10px',
        background: 'var(--bg)',
        borderRadius: 6,
      }}>
        <span>
          Inventory cover:&nbsp;
          <strong style={{ color: rec.inventory_days_on_hand != null && rec.inventory_days_on_hand < 14 ? '#dc2626' : 'var(--text-h)' }}>
            {rec.inventory_days_on_hand != null ? `${rec.inventory_days_on_hand.toFixed(1)} days` : '—'}
          </strong>
        </span>
        <span>
          Capacity utilisation:&nbsp;
          <strong style={{ color: rec.capacity_utilisation_pct != null && rec.capacity_utilisation_pct > 90 ? '#d97706' : 'var(--text-h)' }}>
            {rec.capacity_utilisation_pct != null ? `${rec.capacity_utilisation_pct.toFixed(0)}%` : '—'}
          </strong>
        </span>
        {rec.supplier_lead_time_days != null && (
          <span>Lead time: <strong>{rec.supplier_lead_time_days} days</strong></span>
        )}
      </div>

      {/* Agent recommendation */}
      <div style={{
        fontSize: 13,
        marginBottom: 14,
        padding: '10px 12px',
        border: '1px solid var(--accent-border)',
        background: 'var(--accent-bg)',
        borderRadius: 6,
      }}>
        <span style={{
          fontWeight: 600,
          fontSize: 11,
          textTransform: 'uppercase',
          letterSpacing: 0.5,
          color: 'var(--accent)',
          display: 'block',
          marginBottom: 4,
        }}>
          {actionLabel(rec.action_type)}
        </span>
        {rec.description}
      </div>

      {/* Error */}
      {error && (
        <div style={{ fontSize: 12, color: '#dc2626', marginBottom: 10 }}>{error}</div>
      )}

      {/* Action buttons (only for PENDING) */}
      {isPending && (
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="text"
              value={approverName}
              onChange={e => setApproverName(e.target.value)}
              placeholder="Your name"
              style={{
                fontSize: 13,
                padding: '6px 10px',
                borderRadius: 6,
                border: '1px solid var(--border)',
                background: 'var(--bg)',
                color: 'var(--text-h)',
                width: 140,
              }}
            />
            <button
              onClick={handleApprove}
              disabled={busy}
              style={{
                background: '#16a34a',
                color: '#fff',
                border: 'none',
                borderRadius: 6,
                padding: '6px 16px',
                fontSize: 13,
                fontWeight: 600,
                cursor: busy ? 'not-allowed' : 'pointer',
                opacity: busy ? 0.7 : 1,
              }}
            >
              {busy ? 'Approving…' : 'Approve'}
            </button>
          </div>

          {!showReject ? (
            <button
              onClick={() => setShowReject(true)}
              style={{
                background: 'transparent',
                color: '#dc2626',
                border: '1px solid #dc2626',
                borderRadius: 6,
                padding: '6px 16px',
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              Reject
            </button>
          ) : (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                type="text"
                value={rejectReason}
                onChange={e => setRejectReason(e.target.value)}
                placeholder="Rejection reason (required)"
                style={{
                  fontSize: 13,
                  padding: '6px 10px',
                  borderRadius: 6,
                  border: '1px solid #dc2626',
                  background: 'var(--bg)',
                  color: 'var(--text-h)',
                  width: 220,
                }}
              />
              <button
                onClick={handleReject}
                disabled={busy}
                style={{
                  background: '#dc2626',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 6,
                  padding: '6px 14px',
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: busy ? 'not-allowed' : 'pointer',
                  opacity: busy ? 0.7 : 1,
                }}
              >
                {busy ? 'Rejecting…' : 'Confirm Rejection'}
              </button>
              <button
                onClick={() => { setShowReject(false); setRejectReason('') }}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text)',
                  cursor: 'pointer',
                  fontSize: 13,
                }}
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

function AgentWorkflowPage() {
  const [recommendations, setRecommendations] = useState<AgentRecommendation[]>([])
  const [kpis, setKpis] = useState<ChemicalKPISummary | null>(null)
  const [lastRunResult, setLastRunResult] = useState<AgentCycleResult | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [runBusy, setRunBusy] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)

  async function loadData() {
    try {
      const [recs, kpiData] = await Promise.all([getRecommendations(), getChemicalKPIs()])
      setRecommendations(recs)
      setKpis(kpiData)
      setLoadError(null)
    } catch {
      setLoadError('Could not load recommendations from backend.')
    }
  }

  useEffect(() => { loadData() }, [])

  async function handleRunAgent() {
    setRunBusy(true)
    setRunError(null)
    try {
      const result = await triggerAgentRun()
      setLastRunResult(result)
      await loadData()
    } catch {
      setRunError('Agent cycle failed. Check that the backend and Databricks are connected.')
    } finally {
      setRunBusy(false)
    }
  }

  async function handleApprove(id: string, approver: string) {
    await approveRecommendation(id, approver)
    await loadData()
  }

  async function handleReject(id: string, reason: string) {
    await rejectRecommendation(id, reason)
    await loadData()
  }

  const pending = recommendations.filter(r => r.status === 'PENDING')
  const decided = recommendations.filter(r => r.status !== 'PENDING')

  return (
    <div style={{ padding: '24px 32px', maxWidth: 900, margin: '0 auto', textAlign: 'left' }}>
      {/* Page header */}
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0, fontSize: 24, color: 'var(--text-h)' }}>
          Agent Workflow — Demand & Distribution
        </h2>
        <p style={{ margin: '6px 0 0', fontSize: 14, color: 'var(--text)' }}>
          AI-generated supply planning recommendations awaiting human approval.
          Each recommendation is based on a demand forecast deviation detected by the pipeline.
        </p>
      </div>

      {/* Chemical KPI bar */}
      <ChemicalKPIBar kpis={kpis} />

      {/* Agent control */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        marginBottom: 24,
        padding: '12px 16px',
        background: 'var(--code-bg)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        flexWrap: 'wrap',
      }}>
        <button
          onClick={handleRunAgent}
          disabled={runBusy}
          style={{
            background: 'var(--accent)',
            color: '#fff',
            border: 'none',
            borderRadius: 6,
            padding: '8px 20px',
            fontSize: 14,
            fontWeight: 600,
            cursor: runBusy ? 'not-allowed' : 'pointer',
            opacity: runBusy ? 0.7 : 1,
          }}
        >
          {runBusy ? 'Running agent cycle…' : 'Run Agent Cycle'}
        </button>

        {lastRunResult && !runBusy && (
          <span style={{ fontSize: 13, color: 'var(--text)' }}>
            Last run: {lastRunResult.deviations_found} deviations found,&nbsp;
            {lastRunResult.recommendations_created} recommendations created
            {lastRunResult.errors > 0 && ` (${lastRunResult.errors} errors)`}
            &nbsp;at {new Date(lastRunResult.run_timestamp).toLocaleTimeString()}
          </span>
        )}

        {runError && (
          <span style={{ fontSize: 13, color: '#dc2626' }}>{runError}</span>
        )}
      </div>

      {loadError && (
        <div style={{
          padding: '10px 14px',
          background: 'rgba(220,38,38,0.08)',
          border: '1px solid rgba(220,38,38,0.3)',
          borderRadius: 6,
          color: '#dc2626',
          fontSize: 13,
          marginBottom: 16,
        }}>
          {loadError}
        </div>
      )}

      {/* Pending queue */}
      <section>
        <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-h)', margin: '0 0 12px' }}>
          Pending ({pending.length})
        </h3>

        {pending.length === 0 && !loadError && (
          <div style={{
            padding: '24px',
            textAlign: 'center',
            color: 'var(--text)',
            fontSize: 14,
            border: '1px dashed var(--border)',
            borderRadius: 8,
            marginBottom: 24,
          }}>
            No pending recommendations. Run an agent cycle or wait for the next pipeline run.
          </div>
        )}

        {pending.map(rec => (
          <RecommendationCard
            key={rec.id}
            rec={rec}
            onApprove={handleApprove}
            onReject={handleReject}
          />
        ))}
      </section>

      {/* Decided */}
      {decided.length > 0 && (
        <section style={{ marginTop: 32 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-h)', margin: '0 0 12px' }}>
            Decided ({decided.length})
          </h3>
          {decided.map(rec => (
            <RecommendationCard
              key={rec.id}
              rec={rec}
              onApprove={handleApprove}
              onReject={handleReject}
            />
          ))}
        </section>
      )}
    </div>
  )
}

export default AgentWorkflowPage
