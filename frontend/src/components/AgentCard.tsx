import { PERSONAS, pickRandomColorClass } from '../personas';
import type { AgentConfig, InteractionMode, ModelSpec } from '../types';

type Props = {
  agent: AgentConfig;
  index: number;
  mode: InteractionMode;
  models: ModelSpec[];
  onChange: (next: AgentConfig) => void;
  onRemove?: () => void;
};

function ensureCustomColor(agent: AgentConfig): AgentConfig {
  if (agent.ui_colorClass) return agent;
  return { ...agent, ui_colorClass: pickRandomColorClass() };
}

export function AgentCard({ agent, index, mode, models, onChange, onRemove }: Props) {
  const persona = agent.persona ?? 'Custom';
  const isCustom = persona === 'Custom';
  const promptReadOnly = !isCustom;
  const personaInfo = !isCustom ? PERSONAS[persona] : undefined;
  const headerClass = personaInfo?.colorClass ?? agent.ui_colorClass ?? 'actorColor0';
  const headerIcon = personaInfo?.icon ?? '🧑‍🎭';

  return (
    <div className="actorCard">
      <div className={`actorHeader ${headerClass}`}>
        <div className="actorHeaderLeft">
          <span className="actorIcon">{headerIcon}</span>
          <div className="actorHeaderTitle">Actor {index + 1}</div>
        </div>
        {onRemove ? (
          <button className="linkButton" type="button" onClick={onRemove} aria-label="Remove agent">
            Remove
          </button>
        ) : null}
      </div>

      <div className="actorBody">
      <label className="field">
        <div className="label">Persona</div>
        <select
          value={persona}
          onChange={(e) => {
            const p = e.target.value;
            if (p === 'Custom') {
              onChange(ensureCustomColor({ ...agent, persona: 'Custom' }));
              return;
            }
            onChange({
              ...agent,
              persona: p,
              system_prompt: PERSONAS[p]?.systemPrompt ?? '',
            });
          }}
        >
          <option value="Custom">Custom</option>
          {Object.keys(PERSONAS).map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <div className="label">Actor name</div>
        <input
          value={agent.name}
          onChange={(e) => onChange({ ...agent, name: e.target.value })}
          placeholder={isCustom ? `e.g., Actor ${index + 1}` : 'Name'}
        />
      </label>

      <label className="field">
        <div className="label">Model</div>
        <select
          value={agent.model}
          onChange={(e) => {
            const modelId = e.target.value;
            const spec = models.find((m) => m.id === modelId);
            onChange({ ...agent, model: modelId, provider: spec?.provider ?? null });
          }}
        >
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.display_name} ({m.provider})
            </option>
          ))}
        </select>
        <div className="hint">Model list comes from the backend catalog.</div>
      </label>

      {mode === 'debate' ? (
        <label className="field">
          <div className="label">Debate side</div>
          <select
            value={agent.debate_side ?? ''}
            onChange={(e) => onChange({ ...agent, debate_side: (e.target.value as any) || null })}
          >
            <option value="">Auto</option>
            <option value="for">For the topic</option>
            <option value="against">Against the topic</option>
          </select>
          <div className="hint">Choose which side this actor argues. If Auto, the server alternates by actor index.</div>
        </label>
      ) : null}

      {mode === 'collaboration' ? (
        <label className="field">
          <div className="label">Collaboration responsibility (optional)</div>
          <input
            value={agent.responsibility ?? ''}
            onChange={(e) => onChange({ ...agent, responsibility: e.target.value })}
            placeholder="e.g., focus on risks, propose structure, give examples, sanity-check assumptions…"
          />
          <div className="hint">Used to guide this actor’s contribution in collaboration mode.</div>
        </label>
      ) : null}

      <label className="field">
        <div className="label">System prompt</div>
        <textarea
          className="promptTextarea"
          value={agent.system_prompt ?? ''}
          onChange={(e) => onChange({ ...agent, system_prompt: e.target.value })}
          placeholder={promptReadOnly ? 'Predefined persona prompt (read-only)' : 'Instructions for this actor…'}
          rows={5}
          readOnly={promptReadOnly}
        />
        <div className="hint">
          {promptReadOnly
            ? 'Predefined persona prompt (read-only). Choose Custom persona to edit.'
            : 'Editable. This prompt is combined with the Stage and sent to the backend.'}
        </div>
      </label>
      </div>
    </div>
  );
}


