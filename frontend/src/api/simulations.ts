import type { SimulationTranscript, StartSimulationRequest } from '../types';
import { getApiBaseUrl } from './baseUrl';
import { requestJson } from './http';

export async function startSimulation(body: StartSimulationRequest): Promise<{ simulation_id: string }> {
  return await requestJson<{ simulation_id: string }>('/api/simulations', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function stopSimulation(simulationId: string): Promise<void> {
  await requestJson('/api/simulations/' + encodeURIComponent(simulationId) + '/stop', { method: 'POST' });
}

export async function downloadTranscript(simulationId: string): Promise<SimulationTranscript> {
  return await requestJson<SimulationTranscript>(
    '/api/simulations/' + encodeURIComponent(simulationId) + '/download',
    { method: 'GET' },
  );
}

export function eventsUrl(simulationId: string): string {
  const base = getApiBaseUrl();
  return `${base}/api/simulations/${encodeURIComponent(simulationId)}/events`;
}


