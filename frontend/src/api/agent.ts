import apiClient from './client'
import type { AgentCycleResult, AgentRecommendation, ChemicalKPISummary, ForecastDeviation } from './types'

// Agent cycle includes LLM calls — allow a longer timeout
const AGENT_TIMEOUT_MS = 60_000

export async function getDeviations(thresholdPct?: number): Promise<ForecastDeviation[]> {
  const { data } = await apiClient.get<ForecastDeviation[]>('/agent/deviations', {
    params: thresholdPct != null ? { threshold_pct: thresholdPct } : {},
    timeout: 20_000,
  })
  return data
}

export async function getRecommendations(): Promise<AgentRecommendation[]> {
  const { data } = await apiClient.get<AgentRecommendation[]>('/agent/recommendations', {
    timeout: 20_000,
  })
  return data
}

export async function approveRecommendation(id: string, approver: string): Promise<AgentRecommendation> {
  const { data } = await apiClient.post<AgentRecommendation>(
    `/agent/recommendations/${id}/approve`,
    { approver },
    { timeout: 20_000 },
  )
  return data
}

export async function rejectRecommendation(id: string, reason: string): Promise<AgentRecommendation> {
  const { data } = await apiClient.post<AgentRecommendation>(
    `/agent/recommendations/${id}/reject`,
    { reason },
    { timeout: 20_000 },
  )
  return data
}

export async function triggerAgentRun(): Promise<AgentCycleResult> {
  const { data } = await apiClient.post<AgentCycleResult>('/agent/run', null, {
    timeout: AGENT_TIMEOUT_MS,
  })
  return data
}

export async function getChemicalKPIs(): Promise<ChemicalKPISummary> {
  const { data } = await apiClient.get<ChemicalKPISummary>('/chemical/kpis', {
    timeout: 20_000,
  })
  return data
}
