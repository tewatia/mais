import { useEffect, useRef } from 'react';
import type { ChatItem, StreamStatus } from '../hooks/useSimulationStream';
import { MarkdownText } from './MarkdownText';

type Props = {
  status: StreamStatus;
  typingName: string | null;
  items: ChatItem[];
  palette: Record<string, string>;
  onDownload: () => void;
  canDownload: boolean;
  onStop: () => void;
  canStop: boolean;
};

function bubbleClass(item: ChatItem, palette: Record<string, string>): string {
  if (item.role === 'system') return 'bubble system';
  if (item.role === 'moderator') return 'bubble moderator';
  if (item.role === 'synthesizer') return 'bubble synthesizer';
  const cls = palette[item.name] ?? 'actorColor0';
  return `bubble ${cls}`;
}

export function LiveStage({
  status,
  typingName,
  items,
  onDownload,
  canDownload,
  onStop,
  canStop,
  palette,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [items]);

  const isStarting = (status === 'connecting' || status === 'connected' || status === 'started') && items.length === 0;
  return (
    <div className="panel panelColumn liveStagePanel">
      <div className="panelHeader">
        <div>
          <div className="panelTitle">3. Live Stage</div>
          <div className="panelSubtitle">Status: {status}</div>
        </div>
      </div>

      {typingName ? <div className="typing">{typingName} is typing…</div> : null}

      <div className="panelScroll chatStream" aria-live="polite">
        {items.length === 0 ? (
          <div className="empty">
            {isStarting ? 'Starting… Connecting to the live stream.' : 'Start a simulation to see messages stream here.'}
          </div>
        ) : null}
        {items.map((item) => (
          <div key={item.id} className={bubbleClass(item, palette)}>
            <div className="bubbleMeta">
              <span className="bubbleName">{item.name}</span>
              {typeof item.turn === 'number' ? <span className="bubbleTurn">Turn {item.turn}</span> : null}
              {item.model ? <span className="bubbleModel">{item.model}</span> : null}
              {item.streaming ? <span className="bubbleStreaming">streaming…</span> : null}
            </div>
            <div className="bubbleText">
              {item.streaming ? <span style={{ whiteSpace: 'pre-wrap' }}>{item.content}</span> : <MarkdownText content={item.content} />}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="panelFooter">
        <div className="footerRow">
          <button type="button" className="secondaryButton" onClick={onDownload} disabled={!canDownload}>
            ⬇️ Download
          </button>
          <button type="button" className="primaryButton danger fullWidth" onClick={onStop} disabled={!canStop}>
            Stop
          </button>
        </div>
      </div>
    </div>
  );
}


