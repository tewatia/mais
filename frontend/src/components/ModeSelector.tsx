import type { InteractionMode } from '../types';

type Props = {
  mode: InteractionMode;
  onChange: (mode: InteractionMode) => void;
  stage: string;
  onStageChange: (stage: string) => void;
};

const DEFAULT_STAGES: Record<InteractionMode, string> = {
  debate:
    "This is a debate setting.\n\nParticipants must take a clear position (for or against the topic) and defend it with reasons and examples.\n- Respond directly to the last point made.\n- Challenge weak assumptions and propose counterarguments.\n- Stay respectful; keep it sharp but not rude.\n\nGoal: pressure-test ideas and expose trade-offs.",
  collaboration:
    "This is a collaborative setting.\n\nParticipants are working together to produce the best possible answer.\n- Build on what others say.\n- Make concrete improvements (clarify, structure, add missing details).\n- If you disagree, propose a better alternative (don’t just reject).\n\nGoal: converge on a high-quality outcome.",
  interaction:
    "This is an open conversation.\n\nParticipants should interact naturally.\n- Ask clarifying questions when helpful.\n- Respond directly and keep the conversation moving.\n- It’s okay to disagree, but don’t force debate or consensus.\n\nGoal: a useful, natural exchange.",
  custom:
    'Describe the setting and the rules of interaction.\n\nExample:\n“This is a job interview. The candidate should answer concisely and ask clarifying questions. The interviewer should probe for specifics.”',
};

export function ModeSelector({ mode, onChange, stage, onStageChange }: Props) {
  const stageReadOnly = mode !== 'custom';
  return (
    <div className="card">
      <div className="cardTitle">Interaction</div>
      <div className="modeGrid">
        <button
          type="button"
          className={mode === 'debate' ? 'modeTile active' : 'modeTile'}
          onClick={() => {
            onChange('debate');
            onStageChange(DEFAULT_STAGES.debate);
          }}
        >
          <div className="modeTitle">⚔️ Debate Arena</div>
          <div className="modeSubtitle">Adversarial critique</div>
        </button>
        <button
          type="button"
          className={mode === 'collaboration' ? 'modeTile active' : 'modeTile'}
          onClick={() => {
            onChange('collaboration');
            onStageChange(DEFAULT_STAGES.collaboration);
          }}
        >
          <div className="modeTitle">🤝 Collaboration Team</div>
          <div className="modeSubtitle">Consensus building</div>
        </button>
        <button
          type="button"
          className={mode === 'interaction' ? 'modeTile active' : 'modeTile'}
          onClick={() => {
            onChange('interaction');
            onStageChange(DEFAULT_STAGES.interaction);
          }}
        >
          <div className="modeTitle">💬 Interaction</div>
          <div className="modeSubtitle">Free-form conversation</div>
        </button>
        <button
          type="button"
          className={mode === 'custom' ? 'modeTile active' : 'modeTile'}
          onClick={() => {
            onChange('custom');
            onStageChange(DEFAULT_STAGES.custom);
          }}
        >
          <div className="modeTitle">🧩 Custom</div>
          <div className="modeSubtitle">Bring your own stage instruction</div>
        </button>
      </div>

      <label className="field" style={{ marginTop: 10 }}>
        <div className="label">Stage (prepended to system prompt)</div>
        <textarea
          aria-label="Stage (prepended to system prompt)"
          value={stage}
          onChange={(e) => onStageChange(e.target.value)}
          rows={5}
          className="stageTextarea"
          readOnly={stageReadOnly}
          placeholder={stageReadOnly ? 'Read-only (select Custom to edit)' : 'Describe the setting and the rules of interaction.\n\nExample:\n“This is a job interview. The candidate should answer concisely and ask clarifying questions. The interviewer should probe for specifics.”'}
        />
        <div className="hint">
          {stageReadOnly
            ? 'Read-only. Select Custom to edit; this stage is still sent to the backend and prepended to each actor system prompt.'
            : 'Editable. This stage is sent to the backend and prepended to each actor system prompt.'}
        </div>
      </label>
    </div>
  );
}


