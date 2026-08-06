import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useObject, useObjectRuns, useTriggerRun, useCheckHistory } from '@/api/objects';
import { useRun } from '@/api/runs';
import { Button } from '@/components/ui/Button';
import { CheckStatusCell } from '@/components/ui/StatePill';
import { StatusPill } from '@/components/ui/StatusPill';
import { SparkCell } from '@/components/ui/SparkCell';
import { t } from '@/i18n/de';
import type { CheckResult } from '@/types';

interface AnchorPoint {
  x: number;
  y: number;
}

interface Props {
  objectId: string;
  anchor: AnchorPoint;
  onClose: () => void;
  onOpenOperations: () => void;
}

const POPOVER_WIDTH = 480;
const POPOVER_MAX_HEIGHT = 430;
const VIEWPORT_MARGIN = 12;
const VISIBLE_CHECKS = 10;

function clampPosition(anchor: AnchorPoint, width: number, height: number) {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const left = Math.min(
    Math.max(VIEWPORT_MARGIN, anchor.x + VIEWPORT_MARGIN),
    Math.max(VIEWPORT_MARGIN, viewportWidth - width - VIEWPORT_MARGIN),
  );
  const top = Math.min(
    Math.max(VIEWPORT_MARGIN, anchor.y + VIEWPORT_MARGIN),
    Math.max(VIEWPORT_MARGIN, viewportHeight - height - VIEWPORT_MARGIN),
  );
  return { left, top };
}

function checkRank(check: CheckResult) {
  if (!check.passed && check.severity === 'critical') return 0;
  if (!check.passed) return 1;
  if (check.state !== 'executed') return 2;
  return 3;
}

function orderedChecks(results: CheckResult[]) {
  return [...results].sort((a, b) => checkRank(a) - checkRank(b) || a.name.localeCompare(b.name));
}

function CheckPreviewRow({ objectId, check }: { objectId: string; check: CheckResult }) {
  const { data: history = [] } = useCheckHistory(objectId, check.name);
  const series = useMemo(
    () => [...history]
      .reverse()
      .map(h => Number(h.actual_value))
      .filter(n => Number.isFinite(n)),
    [history],
  );

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'minmax(0, 1fr) 116px auto',
      alignItems: 'center',
      gap: 'var(--s3)',
      padding: 'var(--s2) 0',
      borderBottom: '1px solid var(--line)',
    }}>
      <div style={{ minWidth: 0 }}>
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          color: 'var(--fg)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {check.name}
        </div>
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: 'var(--fg-3)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {check.expect || '-'}
        </div>
      </div>
      <SparkCell series={series} width={54} />
      <CheckStatusCell state={check.state} passed={check.passed} severity={check.severity} />
    </div>
  );
}

export function ObjectChecksPopover({ objectId, anchor, onClose, onOpenOperations }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [position, setPosition] = useState(() => clampPosition(anchor, POPOVER_WIDTH, POPOVER_MAX_HEIGHT));

  const { data: obj } = useObject(objectId);
  const { data: runs = [] } = useObjectRuns(objectId);
  const latest = runs[0];
  const { data: runDetail } = useRun(latest?.run_id ?? '');
  const trigger = useTriggerRun(objectId);
  const results = useMemo(() => runDetail?.results ?? [], [runDetail]);
  const isRunning = latest?.run_state === 'running' || runDetail?.run_state === 'running';

  const visibleChecks = useMemo(() => orderedChecks(results).slice(0, VISIBLE_CHECKS), [results]);
  const hiddenCount = Math.max(0, results.length - visibleChecks.length);

  useLayoutEffect(() => {
    const rect = panelRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPosition(clampPosition(anchor, rect.width, rect.height));
  }, [anchor]);

  useEffect(() => {
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const id = window.setTimeout(() => closeRef.current?.focus(), 0);
    return () => {
      window.clearTimeout(id);
      const previous = previousFocusRef.current;
      if (previous?.isConnected) previous.focus();
    };
  }, []);

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (!panelRef.current?.contains(event.target as Node)) onClose();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    const onResize = () => {
      const rect = panelRef.current?.getBoundingClientRect();
      setPosition(clampPosition(anchor, rect?.width ?? POPOVER_WIDTH, rect?.height ?? POPOVER_MAX_HEIGHT));
    };

    window.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('resize', onResize);
    };
  }, [anchor, onClose]);

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-label={t.peek.quickChecksTitle}
      style={{
        position: 'fixed',
        zIndex: 70,
        left: position.left,
        top: position.top,
        width: POPOVER_WIDTH,
        maxWidth: `calc(100vw - ${VIEWPORT_MARGIN * 2}px)`,
        maxHeight: POPOVER_MAX_HEIGHT,
        background: 'var(--bg-1)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-lg)',
        boxShadow: 'var(--shadow-2)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      <header style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--s2)',
        padding: '12px 14px',
        borderBottom: '1px solid var(--line)',
      }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', minWidth: 0 }}>
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              fontWeight: 700,
              color: 'var(--fg)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {obj?.name ?? objectId}
            </span>
            {obj ? <StatusPill status={obj.status ?? 'unknown'} size="sm" /> : null}
          </div>
          {obj ? (
            <div style={{ color: 'var(--fg-3)', fontSize: 11, marginTop: 3 }}>
              {obj.space} / {obj.layer}
            </div>
          ) : null}
        </div>
        <button
          ref={closeRef}
          onClick={onClose}
          aria-label={t.common.close}
          style={{
            width: 28,
            height: 28,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--bg-2)',
            border: '1px solid var(--line-2)',
            color: 'var(--fg-2)',
            borderRadius: 'var(--r-md)',
            fontSize: 13,
            fontWeight: 700,
            lineHeight: 1,
            cursor: 'pointer',
          }}
        >
          x
        </button>
      </header>

      <div style={{ padding: '10px 14px 4px', overflowY: 'auto', overscrollBehavior: 'contain' }}>
        <div style={{
          fontSize: 11,
          color: 'var(--fg-3)',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          marginBottom: 4,
        }}>
          {t.peek.checksLatestRun}
        </div>
        {results.length === 0 ? (
          <div style={{ color: 'var(--fg-3)', fontSize: 13, padding: 'var(--s3) 0' }}>
            {t.peek.noChecks}
          </div>
        ) : (
          <>
            {visibleChecks.map(check => (
              <CheckPreviewRow key={check.name} objectId={objectId} check={check} />
            ))}
            {hiddenCount > 0 ? (
              <div style={{ color: 'var(--fg-3)', fontSize: 11, padding: 'var(--s2) 0' }}>
                + {hiddenCount} {t.peek.moreChecks}
              </div>
            ) : null}
          </>
        )}
      </div>

      <footer style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--s2)',
        flexWrap: 'wrap',
        padding: '10px 14px',
        borderTop: '1px solid var(--line)',
      }}>
        <Button
          size="sm"
          variant="primary"
          onClick={() => trigger.mutate({})}
          disabled={trigger.isPending || isRunning}
        >
          {trigger.isPending || isRunning ? t.peek.running : t.peek.runChecks}
        </Button>
        <Button size="sm" variant="secondary" onClick={onOpenOperations}>
          {t.peek.openOperations}
        </Button>
        <Link
          to={`/objects/${encodeURIComponent(objectId)}`}
          onClick={onClose}
          style={{ color: 'var(--cont)', fontSize: 12, marginLeft: 'auto' }}
        >
          {t.peek.openFull}
        </Link>
      </footer>
    </div>
  );
}
