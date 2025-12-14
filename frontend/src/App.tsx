import { useEffect, useMemo, useState } from 'react';

import { listModels } from './api/models';
import { downloadTranscript, startSimulation, stopSimulation } from './api/simulations';
import './App.css';
import { AgentCard } from './components/AgentCard';
import { LiveStage } from './components/LiveStage';
import { ModeSelector } from './components/ModeSelector';
import { useSimulationStream } from './hooks/useSimulationStream';
import { PERSONAS, pickRandomColorClass } from './personas';
import type { AgentConfig, InteractionMode, ModelSpec, Provider, StartSimulationRequest } from './types';

function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function randomPersonaKey(): string {
  const keys = Object.keys(PERSONAS);
  return keys[Math.floor(Math.random() * keys.length)]!;
}

function uniqueName(base: string, existingLower: Set<string>): string {
  const cleaned = base.trim() || 'Actor';
  let candidate = cleaned;
  let i = 2;
  while (existingLower.has(candidate.toLowerCase())) {
    candidate = `${cleaned} ${i}`;
    i += 1;
  }
  existingLower.add(candidate.toLowerCase());
  return candidate;
}

function usedNamesExcluding(agents: AgentConfig[], excludeIndex: number): Set<string> {
  return new Set(
    agents
      .filter((_, i) => i !== excludeIndex)
      .map((a) => a.name.trim().toLowerCase())
      .filter(Boolean),
  );
}

const DEFAULT_CUSTOM_NAME = 'John Doe';
const DEFAULT_CUSTOM_PROMPT =
  "Custom persona (replace this text):\n- Who are you?\n- How do you speak?\n- What should you focus on / avoid?\n\nExample: 'You are a pragmatic product manager. Be concise, ask clarifying questions, and propose next steps.'";

function applyDefaultNameForPersona(next: AgentConfig, agents: AgentConfig[], index: number): AgentConfig {
  const prev = agents[index];
  const prevPersona = (prev?.persona ?? 'Custom') as string;
  const nextPersona = (next.persona ?? 'Custom') as string;

  // Only auto-apply defaults when the persona actually changes.
  if (prevPersona === nextPersona) return next;

  const used = usedNamesExcluding(agents, index);

  if (nextPersona === 'Custom') {
    return {
      ...next,
      name: uniqueName(DEFAULT_CUSTOM_NAME, used),
      system_prompt: DEFAULT_CUSTOM_PROMPT,
    };
  }

  const defaultName =
    PERSONAS[nextPersona]?.defaultName ??
    PERSONAS[nextPersona]?.label ??
    nextPersona;
  return { ...next, name: uniqueName(defaultName, used) };
}

function randomPersonaAgent(existingLower: Set<string>): AgentConfig {
  const persona = randomPersonaKey();
  const p = PERSONAS[persona]!;
  return {
    name: uniqueName(p.defaultName || p.label, existingLower),
    model: 'gpt-4o-mini',
    provider: 'openai',
    persona,
    system_prompt: p.systemPrompt,
  };
}

const DEFAULT_AGENTS: AgentConfig[] = (() => {
  const used = new Set<string>();
  return [randomPersonaAgent(used), randomPersonaAgent(used)];
})();

function headerColorClass(agent: AgentConfig): string {
  const persona = agent.persona ?? 'Custom';
  if (persona !== 'Custom') return PERSONAS[persona]?.colorClass ?? agent.ui_colorClass ?? 'actorColor0';
  return agent.ui_colorClass ?? 'actorColor0';
}

function ensureCustomColor(agent: AgentConfig): AgentConfig {
  if (agent.ui_colorClass) return agent;
  return { ...agent, ui_colorClass: pickRandomColorClass() };
}

export default function App() {
  const FALLBACK_MODELS: ModelSpec[] = useMemo(
    () => [
      { id: 'gpt-4o-mini', display_name: 'GPT-4o Mini', provider: 'openai' },
      { id: 'gpt-4o', display_name: 'GPT-4o', provider: 'openai' },
      { id: 'gemini-2.5-flash', display_name: 'Gemini 2.5 Flash', provider: 'google' },
      { id: 'claude-sonnet-4-5', display_name: 'Claude Sonnet 4.5', provider: 'anthropic' },
    ],
    [],
  );
  const [models, setModels] = useState<ModelSpec[]>([]);

  const [mode, setMode] = useState<InteractionMode>('debate');
  const [stage, setStage] = useState(
    "This is a debate setting.\n\nParticipants must take a clear position (for or against the topic) and defend it with reasons and examples.\n- Respond directly to the last point made.\n- Challenge weak assumptions and propose counterarguments.\n- Stay respectful; keep it sharp but not rude.\n\nGoal: pressure-test ideas and expose trade-offs.",
  );
  const [topic, setTopic] = useState('Is AI sentient?');
  const [turnLimit, setTurnLimit] = useState(20);

  const [agents, setAgents] = useState<AgentConfig[]>(() => DEFAULT_AGENTS.map(ensureCustomColor));
  const [moderatorEnabled, setModeratorEnabled] = useState(false);
  const [moderatorModel, setModeratorModel] = useState('gpt-4o-mini');
  const [moderatorFrequency, setModeratorFrequency] = useState(2);
  const [moderatorPrompt, setModeratorPrompt] = useState(
    'You are a debate moderator.\nDo NOT introduce new ideas.\nSummarize the debate so far (neutral), merge duplicates, and suggest the next focus/questions.',
  );

  const [synthEnabled, setSynthEnabled] = useState(false);
  const [synthModel, setSynthModel] = useState('gpt-4o-mini');
  const [synthFrequency, setSynthFrequency] = useState(2);
  const [synthPrompt, setSynthPrompt] = useState(
    'You are the collaboration lead.\nDo NOT introduce new ideas.\nSummarize progress, merge duplicates, and list concrete next steps using only what participants already said.',
  );

  const [simulationId, setSimulationId] = useState<string | null>(null);
  const [uiError, setUiError] = useState<string | null>(null);
  const [startPending, setStartPending] = useState(false);

  const stream = useSimulationStream(simulationId);

  const modelOptions = models.length ? models : FALLBACK_MODELS;

  function providerForModel(modelId: string): Provider | null {
    return modelOptions.find((m) => m.id === modelId)?.provider ?? null;
  }

  // Fetch model list from backend catalog (safe fallback if request fails).
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const catalog = await listModels();
        if (!alive) return;
        if (Array.isArray(catalog.models) && catalog.models.length) {
          setModels(catalog.models);
        }
      } catch {
        // ignore: fallback list will be used
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // Normalize selected models to something present in the catalog when it loads.
  useEffect(() => {
    if (!models.length) return;
    const first = models[0]!;
    setAgents((prev) =>
      prev.map((a) => {
        const spec = models.find((m) => m.id === a.model) ?? first;
        return { ...a, model: spec.id, provider: spec.provider };
      }),
    );
    setModeratorModel((prev) => (models.some((m) => m.id === prev) ? prev : first.id));
    setSynthModel((prev) => (models.some((m) => m.id === prev) ? prev : first.id));
  }, [models.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const agentNameSet = useMemo(() => new Set(agents.map((a) => a.name.trim().toLowerCase())), [agents]);
  const palette = useMemo(() => {
    const mapping: Record<string, string> = {};
    for (let i = 0; i < agents.length; i++) {
      const name = agents[i]?.name?.trim() || `Actor ${i + 1}`;
      mapping[name] = headerColorClass(agents[i]!);
    }
    return mapping;
  }, [agents]);
  const isValid = useMemo(() => {
    if (!topic.trim()) return false;
    if (!stage.trim()) return false;
    if (agents.length < 2) return false;
    if (agentNameSet.size !== agents.length) return false;
    return agents.every((a) => a.name.trim() && a.model.trim());
  }, [agentNameSet.size, agents, stage, topic]);

  async function onStart() {
    if (startPending) return;
    setUiError(null);
    stream.reset();
    setStartPending(true);

    const body: StartSimulationRequest = {
      topic: topic.trim(),
      mode,
      stage: stage.trim(),
      turn_limit: turnLimit,
      agents: agents.map((a) => ({
        name: a.name.trim(),
        model: a.model.trim(),
        provider: a.provider ?? providerForModel(a.model.trim()),
        persona: a.persona ?? null,
        system_prompt: a.system_prompt ?? null,
        debate_side: mode === 'debate' ? (a.debate_side ?? null) : null,
        responsibility: mode === 'collaboration' ? (a.responsibility ?? null) : null,
      })),
      moderator: {
        enabled: mode === 'debate' ? moderatorEnabled : false,
        model: mode === 'debate' && moderatorEnabled ? moderatorModel : null,
        provider:
          mode === 'debate' && moderatorEnabled ? providerForModel(moderatorModel) : null,
        system_prompt: mode === 'debate' ? moderatorPrompt : null,
        frequency_turns: moderatorFrequency,
      },
      synthesizer: {
        enabled: mode === 'collaboration' ? synthEnabled : false,
        model: mode === 'collaboration' && synthEnabled ? synthModel : null,
        provider:
          mode === 'collaboration' && synthEnabled ? providerForModel(synthModel) : null,
        system_prompt: mode === 'collaboration' ? synthPrompt : null,
        frequency_turns: synthFrequency,
      },
    };

    try {
      const resp = await startSimulation(body);
      setSimulationId(resp.simulation_id);
    } catch (e) {
      setUiError(e instanceof Error ? e.message : 'Failed to start simulation');
      setSimulationId(null);
    } finally {
      setStartPending(false);
    }
  }

  async function onStop() {
    if (!simulationId) return;
    try {
      await stopSimulation(simulationId);
    } catch {
      // ignore
    }
  }

  async function onDownload() {
    if (!simulationId) return;
    try {
      const transcript = await downloadTranscript(simulationId);
      downloadJson(`mais-transcript-${simulationId}.json`, transcript);
    } catch (e) {
      setUiError(e instanceof Error ? e.message : 'Failed to download transcript');
    }
  }

  return (
    <div className="appShell">
      <header className="topBar">
        <div className="brand">MAIS</div>
        <div className="topBarSub">Multi-Agent Interaction Studio (MVP)</div>
      </header>

      <main className="layout">
        <aside className="panel panelColumn sidebarPanel">
          <div className="panelHeader">
            <div>
              <div className="panelTitle">1. Interaction</div>
              <div className="panelSubtitle">Mode & settings</div>
            </div>
          </div>
          <div className="panelScroll">
            <ModeSelector mode={mode} onChange={(m) => setMode(m)} stage={stage} onStageChange={setStage} />
          </div>
        </aside>

        <section className="panel panelColumn">
          <div className="panelHeader">
      <div>
              <div className="panelTitle">2. Cast & Scenario</div>
              <div className="panelSubtitle">Topic, actors, and controls</div>
            </div>
          </div>

          <div className="panelScroll">
            <div className="card">
              <div className="cardTitle">Global Topic</div>
              <textarea aria-label="Global topic" value={topic} onChange={(e) => setTopic(e.target.value)} rows={4} />
            </div>

            <div className="card">
              <div className="cardTitle">Turn Limit</div>
              <input
                type="number"
                min={1}
                max={400}
                value={turnLimit}
                onChange={(e) => setTurnLimit(Number(e.target.value))}
              />
              <div className="hint">Prevents infinite loops. Moderator can also steer in Debate mode.</div>
      </div>

      <div className="card">
              <div className="cardHeader">
                <div className="cardTitle">Actors</div>
              </div>
              <div className="stack">
                {agents.map((agent, idx) => (
                  <AgentCard
                    key={idx}
                    agent={agent}
                    index={idx}
                    mode={mode}
                    models={modelOptions}
                    onChange={(next) =>
                      setAgents((prev) =>
                        prev.map((x, i) => (i === idx ? applyDefaultNameForPersona(next, prev, idx) : x)),
                      )
                    }
                    onRemove={idx >= 2 ? () => setAgents((prev) => prev.filter((_, i) => i !== idx)) : undefined}
                  />
                ))}
      </div>
              <button
                type="button"
                className="secondaryButton"
                style={{ marginTop: 12, width: '100%' }}
                onClick={() =>
                  setAgents((prev) =>
                    prev.length >= 6
                      ? prev
                      : (() => {
                          const used = new Set(prev.map((a) => a.name.trim().toLowerCase()));
                          return [...prev, randomPersonaAgent(used)];
                        })(),
                  )
                }
                disabled={agents.length >= 6}
              >
                ➕ Add Actor
              </button>
            </div>

            {mode === 'debate' ? (
              <div className="card">
                <div className="moderatorHeader">
                  <div className="cardTitle" style={{ marginBottom: 0 }}>
                    Moderator (Debate Mode)
                  </div>
                  <label className="toggleInline">
                    <input
                      type="checkbox"
                      checked={moderatorEnabled}
                      onChange={(e) => setModeratorEnabled(e.target.checked)}
                    />
                    <span className="labelInline">Enable</span>
                  </label>
                </div>

                <label className="field">
                  <div className="label">Moderator model</div>
                  <select
                    value={moderatorModel}
                    onChange={(e) => setModeratorModel(e.target.value)}
                    disabled={!moderatorEnabled}
                  >
                    {modelOptions.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.display_name} ({m.provider})
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field">
                  <div className="label">Frequency (turns)</div>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={moderatorFrequency}
                    onChange={(e) => setModeratorFrequency(Number(e.target.value))}
                    disabled={!moderatorEnabled}
                  />
                </label>

                <label className="field">
                  <div className="label">Moderator system prompt</div>
                  <textarea
                    className="promptTextarea"
                    value={moderatorPrompt}
                    onChange={(e) => setModeratorPrompt(e.target.value)}
                    placeholder="Instructions for the moderator…"
                    rows={5}
                    readOnly={!moderatorEnabled}
                  />
                  <div className="hint">
                    {moderatorEnabled
                      ? 'Editable. This prompt is sent to the backend for the moderator turns.'
                      : 'Enable moderator to edit this prompt.'}
                  </div>
                </label>
              </div>
            ) : null}

            {mode === 'collaboration' ? (
              <div className="card">
                <div className="moderatorHeader">
                  <div className="cardTitle" style={{ marginBottom: 0 }}>
                    Synthesizer / Lead (Collaboration)
                  </div>
                  <label className="toggleInline">
                    <input
                      type="checkbox"
                      checked={synthEnabled}
                      onChange={(e) => setSynthEnabled(e.target.checked)}
                    />
                    <span className="labelInline">Enable</span>
                  </label>
                </div>

                <label className="field">
                  <div className="label">Synthesizer model</div>
                  <select value={synthModel} onChange={(e) => setSynthModel(e.target.value)} disabled={!synthEnabled}>
                    {modelOptions.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.display_name} ({m.provider})
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field">
                  <div className="label">Frequency (collaboration rounds)</div>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={synthFrequency}
                    onChange={(e) => setSynthFrequency(Number(e.target.value))}
                    disabled={!synthEnabled}
                  />
                  <div className="hint">
                    Runs after every N completed collaboration rounds (a round = each actor speaks once). It will also run once at the end if enabled.
                  </div>
                </label>

                <label className="field">
                  <div className="label">Synthesizer system prompt</div>
                  <textarea
                    className="promptTextarea"
                    value={synthPrompt}
                    onChange={(e) => setSynthPrompt(e.target.value)}
                    placeholder="Instructions for the synthesizer…"
                    rows={5}
                    readOnly={!synthEnabled}
                  />
                  <div className="hint">
                    {synthEnabled
                      ? 'Editable. This prompt is sent to the backend for synthesizer turns.'
                      : 'Enable synthesizer to edit this prompt.'}
                  </div>
                </label>
              </div>
            ) : null}
          </div>

          <div className="panelFooter">
            <div className="footerRow">
              <button
                type="button"
                className="primaryButton fullWidth"
                onClick={onStart}
                disabled={!isValid || startPending || stream.canStop}
              >
                ▶ Start Simulation
              </button>
            </div>
            {uiError ? <div className="error">{uiError}</div> : null}
          </div>
        </section>

        <LiveStage
          status={stream.status}
          typingName={stream.typingName}
          items={stream.items}
          onStop={onStop}
          canStop={stream.canStop}
          onDownload={onDownload}
          canDownload={!!simulationId}
          palette={palette}
        />
      </main>
    </div>
  );
}
