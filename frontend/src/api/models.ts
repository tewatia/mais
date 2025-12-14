import type { ModelCatalog } from '../types';
import { requestJson } from './http';

export async function listModels(): Promise<ModelCatalog> {
  return await requestJson<ModelCatalog>('/api/models', { method: 'GET' });
}


