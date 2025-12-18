export type InteractionMode = 'debate' | 'collaboration' | 'interaction' | 'custom';

export type Provider = 'openai' | 'anthropic' | 'google' | 'ollama';

export type ModelSpec = {
  id: string;
  display_name: string;
  provider: Provider;
};

export type ModelCatalog = {
  models: ModelSpec[];
};

export type AgentConfig = {
  name: string;
  model: string;
  persona?: string | null;
  system_prompt?: string | null;
  provider?: Provider | null;
  debate_side?: 'for' | 'against' | null;
  responsibility?: string | null;
  // Generation settings (optional)
  temperature?: number | null;
  max_tokens?: number | null;
  context_size?: number | null;
  ui_colorClass?: string | null; // UI-only (not sent to backend)
};

export type ModeratorConfig = {
  enabled: boolean;
  model?: string | null;
  provider?: Provider | null;
  system_prompt?: string | null;
  frequency_turns?: number;
  // Generation settings (optional)
  temperature?: number | null;
  max_tokens?: number | null;
  context_size?: number | null;
};

export type SynthesizerConfig = {
  enabled: boolean;
  model?: string | null;
  provider?: Provider | null;
  system_prompt?: string | null;
  frequency_turns?: number;
  // Generation settings (optional)
  temperature?: number | null;
  max_tokens?: number | null;
  context_size?: number | null;
};

export type StartSimulationRequest = {
  topic: string;
  mode: InteractionMode;
  stage: string;
  turn_limit: number;
  agents: AgentConfig[];
  moderator: ModeratorConfig;
  synthesizer: SynthesizerConfig;
};

export type TranscriptMessage = {
  role: 'agent' | 'moderator' | 'synthesizer';
  name: string;
  content: string;
  turn: number;
  model: string;
  agent_id?: number;
};

export type SimulationTranscript = {
  simulation_id: string;
  topic: string;
  mode: InteractionMode;
  messages: TranscriptMessage[];
};


