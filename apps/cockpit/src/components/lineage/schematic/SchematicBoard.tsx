/**
 * Präsentationaler SVG-Renderer fürs Schaltplan-Board.
 *
 * Kontrolliert: nimmt ein fertig berechnetes ELK-Layout plus Trace-/Auswahl-
 * State und Callbacks entgegen, hält selbst keinen Zustand und ruft kein ELK.
 * So bleibt das Rendering testbar; der stateful Container (ELK-Aufruf,
 * Trace-Berechnung, Inspector) kommt in Phase 4 obendrauf.
 */
import { useCallback, useEffect, useId, useMemo, useRef, useState, type MouseEvent, type PointerEvent } from 'react';
import { columnId, edgeTypeColor } from '@/lib/lineage';
import { t } from '@/i18n/de';
import type { PositionedChip, RoutedEdge, RoutedObjectEdge, SchematicLayout } from './layout';
import { GEO } from './layout';
import { dqStatusColor, laneColor, orthogonalPath } from './theme';

const T = t.lineage.schematic;

const ZOOM_MIN = 0.2;
const ZOOM_MAX = 2.5;
const DRAG_THRESHOLD = 4; // px in Screen-Koordinaten
const CHIP_INTERACTION_SELECTOR = '.schem-chip';
const VIEW_PAD_X = 72;
const VIEW_PAD_Y = 84;
const INITIAL_ZOOM = 0.48;

interface Viewport {
  x: number;
  y: number;
  k: number;
}

/** Client-Pixel → SVG-User-Koordinaten (berücksichtigt die viewBox-Skalierung). */
function clientToUser(svg: SVGSVGElement, clientX: number, clientY: number): { x: number; y: number } {
  const ctm = svg.getScreenCTM();
  if (!ctm) return { x: clientX, y: clientY };
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  const p = pt.matrixTransform(ctm.inverse());
  return { x: p.x, y: p.y };
}

function isChipInteractionTarget(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest(CHIP_INTERACTION_SELECTOR) !== null;
}

function defaultViewport(width: number, height: number): Viewport {
  const k = INITIAL_ZOOM;
  return { x: roundView((width / 2) * (1 - k)), y: roundView((height / 2) * (1 - k)), k };
}

function roundView(value: number): number {
  return Math.round(value * 1000) / 1000;
}

export interface SchematicBoardProps {
  layout: SchematicLayout;
  /** Pin-Keys (columnId) des aktiven Trace-Pfads. */
  tracePins?: Set<string>;
  /** Kanten-IDs des aktiven Trace-Pfads. */
  traceEdges?: Set<string>;
  /** Chips, die durch Filter/Suche ausgegraut sind. */
  dimmedChips?: Set<string>;
  selectedChip?: string | null;
  selectedPin?: { node: string; pin: string } | null;
  onSelectChip?: (nodeId: string) => void;
  onSelectPin?: (nodeId: string, pinId: string) => void;
  /** Spalten dieses Chips ein-/ausklappen (Chevron im Kopf). */
  onToggleColumns?: (nodeId: string) => void;
  onBackground?: () => void;
  fitKey?: string;
}

export function SchematicBoard({
  layout,
  tracePins,
  traceEdges,
  dimmedChips,
  selectedChip,
  selectedPin,
  onSelectChip,
  onSelectPin,
  onToggleColumns,
  onBackground,
  fitKey,
}: SchematicBoardProps) {
  const gridId = useId();
  const shadowId = useId();
  const arrowId = useId();
  const tracing = !!tracePins && tracePins.size > 0;
  const isDimmedChip = (id: string) => !!dimmedChips && dimmedChips.has(id);

  const W = Math.max(layout.width, 1);
  const H = Math.max(layout.height, 1);
  const viewBox = `${-VIEW_PAD_X} ${-VIEW_PAD_Y} ${W + VIEW_PAD_X * 2} ${H + VIEW_PAD_Y * 2}`;
  const laneBands = useMemo(() => buildLaneBands(layout.chips), [layout.chips]);

  const svgRef = useRef<SVGSVGElement>(null);
  const [view, setView] = useState<Viewport>(() => defaultViewport(W, H));
  const lastFitKey = useRef(fitKey);
  // Pan-State: letzter Punkt (User-Koordinaten) + ob die Geste schon ein Zug ist.
  const panRef = useRef<{ lastX: number; lastY: number; startClientX: number; startClientY: number } | null>(null);
  const movedRef = useRef(false);

  // Drag wandert über einen Pin/Chip hinweg: Auswahl unterdrücken, wenn gerade
  // panned wurde (der Klick nach pointerup darf nicht selektieren/deselektieren).
  const guard = useCallback(
    <A extends unknown[]>(fn?: (...args: A) => void) =>
      (...args: A) => {
        if (movedRef.current) return;
        fn?.(...args);
      },
    [],
  );

  const zoomAt = useCallback((factor: number, cx: number, cy: number) => {
    setView(v => {
      const k = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, v.k * factor));
      if (k === v.k) return v;
      // Weltpunkt unter dem Cursor fixieren.
      const wx = (cx - v.x) / v.k;
      const wy = (cy - v.y) / v.k;
      return { k, x: cx - wx * k, y: cy - wy * k };
    });
  }, []);

  // Wheel-Zoom als non-passiver Listener, damit preventDefault das Seiten-
  // Scrollen unterbindet (React onWheel ist passiv).
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return undefined;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const p = clientToUser(svg, e.clientX, e.clientY);
      zoomAt(e.deltaY < 0 ? 1.12 : 1 / 1.12, p.x, p.y);
    };
    svg.addEventListener('wheel', onWheel, { passive: false });
    return () => svg.removeEventListener('wheel', onWheel);
  }, [zoomAt]);

  const onPointerDown = (e: PointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    movedRef.current = false;
    if (isChipInteractionTarget(e.target)) {
      panRef.current = null;
      return;
    }
    const svg = svgRef.current;
    if (!svg) return;
    const p = clientToUser(svg, e.clientX, e.clientY);
    panRef.current = { lastX: p.x, lastY: p.y, startClientX: e.clientX, startClientY: e.clientY };
    svg.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    const pan = panRef.current;
    const svg = svgRef.current;
    if (!pan || !svg) return;
    if (
      !movedRef.current &&
      Math.hypot(e.clientX - pan.startClientX, e.clientY - pan.startClientY) < DRAG_THRESHOLD
    ) {
      return;
    }
    movedRef.current = true;
    const p = clientToUser(svg, e.clientX, e.clientY);
    const dx = p.x - pan.lastX;
    const dy = p.y - pan.lastY;
    pan.lastX = p.x;
    pan.lastY = p.y;
    setView(v => ({ ...v, x: v.x + dx * v.k, y: v.y + dy * v.k }));
  };

  const endPan = (e: PointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (svg && svg.hasPointerCapture?.(e.pointerId)) svg.releasePointerCapture(e.pointerId);
    panRef.current = null;
  };

  const zoomIn = () => zoomAt(1.25, W / 2, H / 2);
  const zoomOut = () => zoomAt(1 / 1.25, W / 2, H / 2);
  const fit = () => setView(defaultViewport(W, H));

  useEffect(() => {
    if (lastFitKey.current === fitKey) return;
    lastFitKey.current = fitKey;
    setView(defaultViewport(W, H));
  }, [fitKey, W, H]);

  return (
    <div className="schem-stage">
      <svg
        ref={svgRef}
        className="schem-board"
        viewBox={viewBox}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Schematic lineage"
        style={{ touchAction: 'none' }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endPan}
        onPointerCancel={endPan}
      >
        <defs>
          <pattern id={gridId} width={26} height={26} patternUnits="userSpaceOnUse">
            <circle cx={1} cy={1} r={1} fill="var(--line)" opacity={0.32} />
          </pattern>
          {/* Weiche Schlagschatten geben den Chips Tiefe statt flacher Rechtecke. */}
          <filter id={shadowId} x="-20%" y="-20%" width="140%" height="160%">
            <feDropShadow dx={0} dy={3} stdDeviation={4} floodColor="#000" floodOpacity={0.42} />
          </filter>
          <marker
            id={arrowId}
            viewBox="0 0 8 8"
            refX={7}
            refY={4}
            markerWidth={8}
            markerHeight={8}
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 8 4 L 0 8 z" fill="context-stroke" />
          </marker>
        </defs>

        <g className="schem-viewport" transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
          {/* Großzügiges Raster, damit beim Pannen kein leerer Rand entsteht. */}
          <rect
            x={-W}
            y={-H}
            width={W * 3}
            height={H * 3}
            fill={`url(#${gridId})`}
            onClick={guard(onBackground)}
          />

          <g className="schem-lane-bands" aria-hidden="true">
            {laneBands.map(band => (
              <g key={band.key}>
                <rect
                  className="schem-lane-band"
                  x={band.x}
                  y={-VIEW_PAD_Y + 14}
                  width={band.width}
                  height={H + VIEW_PAD_Y * 2 - 28}
                  rx={12}
                  fill={laneColor(band.order)}
                />
                <text className="schem-lane-label" x={band.x + 14} y={-VIEW_PAD_Y + 38}>
                  {band.label}
                </text>
              </g>
            ))}
          </g>

          {/* Traces unter den Chips, damit Pin-Dots die Endpunkte überdecken.
              Hybrid: aggregierte Objekt-Kanten und Pin-zu-Pin-Traces koexistieren
              je nach Expansions-Zustand der Endknoten. */}
          <g className="schem-traces">
            {layout.objectEdges.map(edge => (
              <ObjectTrace
                key={edge.id}
                edge={edge}
                dimmed={isDimmedChip(edge.fromNode) || isDimmedChip(edge.toNode)}
                markerId={arrowId}
              />
            ))}
            {layout.edges.map(edge => (
              <ColumnTrace
                key={edge.id}
                edge={edge}
                active={!!traceEdges && traceEdges.has(edge.id)}
                dimmed={
                  isDimmedChip(edge.fromNode) ||
                  isDimmedChip(edge.toNode) ||
                  (tracing && !(traceEdges && traceEdges.has(edge.id)))
                }
                markerId={arrowId}
              />
            ))}
          </g>

          <g className="schem-chips">
            {layout.chips.map(chip => (
              <Chip
                key={chip.id}
                chip={chip}
                shadowId={shadowId}
                dimmed={isDimmedChip(chip.id)}
                selected={selectedChip === chip.id}
                tracePins={tracePins}
                selectedPin={selectedPin}
                onSelectChip={guard(onSelectChip)}
                onSelectPin={guard(onSelectPin)}
                onToggleColumns={guard(onToggleColumns)}
              />
            ))}
          </g>
        </g>
      </svg>

      <div className="schem-zoom" role="group" aria-label="Zoom">
        <button type="button" onClick={zoomIn} aria-label="Vergrößern">+</button>
        <button type="button" onClick={zoomOut} aria-label="Verkleinern">−</button>
        <button type="button" onClick={fit} aria-label="Ansicht zurücksetzen">⤢</button>
      </div>
    </div>
  );
}

function statusLabel(status: string | undefined): string {
  switch ((status || '').toLowerCase()) {
    case 'pass':
    case 'ok':
      return 'OK';
    case 'warn':
    case 'warning':
      return 'WARN';
    case 'critical':
    case 'crit':
      return 'CRIT';
    case 'fail':
    case 'failing':
    case 'error':
      return 'FAIL';
    default:
      return (status || 'N/A').toUpperCase().slice(0, 4);
  }
}

interface LaneBand {
  key: string;
  label: string;
  order: number;
  x: number;
  width: number;
}

function buildLaneBands(chips: PositionedChip[]): LaneBand[] {
  const byLane = new Map<string, { key: string; label: string; order: number; minX: number; maxX: number }>();
  for (const chip of chips) {
    const existing = byLane.get(chip.laneKey);
    if (existing) {
      existing.minX = Math.min(existing.minX, chip.x);
      existing.maxX = Math.max(existing.maxX, chip.x + chip.width);
    } else {
      byLane.set(chip.laneKey, {
        key: chip.laneKey,
        label: chip.layer,
        order: chip.laneOrder,
        minX: chip.x,
        maxX: chip.x + chip.width,
      });
    }
  }
  return [...byLane.values()]
    .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label))
    .map(lane => ({
      key: lane.key,
      label: lane.label,
      order: lane.order,
      x: lane.minX - 34,
      width: lane.maxX - lane.minX + 68,
    }));
}

function ColumnTrace({
  edge,
  active,
  dimmed,
  markerId,
}: {
  edge: RoutedEdge;
  active: boolean;
  dimmed: boolean;
  markerId: string;
}) {
  const cls =
    'schem-trace' +
    (edge.kind === 'derived' || edge.edgeType === 'computed' ? ' is-derived' : '') +
    (active ? ' is-active' : '') +
    (dimmed ? ' is-dimmed' : '');
  return (
    <path
      className={cls}
      d={orthogonalPath(edge.points)}
      stroke={edge.color || edgeTypeColor(edge.edgeType)}
      markerEnd={`url(#${markerId})`}
    >
      <title>
        {`${edge.fromNode}.${edge.fromPin} → ${edge.toNode}.${edge.toPin}`}
        {edge.expression ? ` · ${edge.expression}` : ''}
      </title>
    </path>
  );
}

function ObjectTrace({ edge, dimmed, markerId }: { edge: RoutedObjectEdge; dimmed: boolean; markerId: string }) {
  return (
    <path
      className={'schem-obj-trace' + (dimmed ? ' is-dimmed' : '')}
      d={orthogonalPath(edge.points)}
      markerEnd={`url(#${markerId})`}
    >
      <title>{`${edge.fromNode} → ${edge.toNode}`}</title>
    </path>
  );
}

interface ChipProps {
  chip: PositionedChip;
  shadowId: string;
  dimmed: boolean;
  selected: boolean;
  tracePins?: Set<string>;
  selectedPin?: { node: string; pin: string } | null;
  onSelectChip?: (nodeId: string) => void;
  onSelectPin?: (nodeId: string, pinId: string) => void;
  onToggleColumns?: (nodeId: string) => void;
}

function Chip({
  chip,
  shadowId,
  dimmed,
  selected,
  tracePins,
  selectedPin,
  onSelectChip,
  onSelectPin,
  onToggleColumns,
}: ChipProps) {
  const clipId = useId();
  const expanded = chip.expanded;
  const cls = 'schem-chip' + (selected ? ' is-selected' : '') + (dimmed ? ' is-dimmed' : '');
  const tagText = `${chip.layer.toUpperCase()}${chip.system ? ` · ${chip.system}` : ''}`;
  const dqColor = chip.dqStatus ? dqStatusColor(chip.dqStatus) : null;
  const contractX = chip.width - (dqColor ? 98 : 36);
  const statusX = chip.width - 70;
  const lane = laneColor(chip.laneOrder);
  // Expandierte Chips bekommen ein abgesetztes Kopfband + Pin-Reihen; eingeklappte
  // sind reine Objekt-Karten (Kopf == ganzer Chip).
  const headerH = expanded ? GEO.headerH : chip.height;
  const hasPins = chip.pins.length > 0;
  const selectChip = () => onSelectChip?.(chip.id);
  const selectPin = (event: MouseEvent<SVGElement>, pinId: string) => {
    event.stopPropagation();
    onSelectPin?.(chip.id, pinId);
  };
  const toggleColumns = (event: MouseEvent<SVGElement>) => {
    event.stopPropagation();
    onToggleColumns?.(chip.id);
  };
  const toggleLabel = `${expanded ? T.collapseColumns : T.expandColumns} – ${chip.label}`;

  return (
    <g className={cls} transform={`translate(${chip.x}, ${chip.y})`} onClick={selectChip} style={{ cursor: 'pointer' }}>
      <clipPath id={clipId}>
        <rect x={0} y={0} width={chip.width} height={chip.height} rx={7} />
      </clipPath>
      <rect
        className="schem-chip-body"
        x={0}
        y={0}
        width={chip.width}
        height={chip.height}
        rx={7}
        filter={`url(#${shadowId})`}
      />
      {/* Kopfband, Lane-Akzent und Trennlinie, an die gerundeten Ecken geklippt. */}
      <g clipPath={`url(#${clipId})`}>
        <rect className="schem-chip-header" x={0} y={0} width={chip.width} height={headerH} />
        <rect className="schem-lane" x={0} y={0} width={chip.width} height={3} fill={lane} />
        {expanded && (
          <line className="schem-divider" x1={0} y1={headerH} x2={chip.width} y2={headerH} />
        )}
      </g>

      <text className="schem-tag" x={13} y={20}>
        {tagText}
      </text>
      <text
        className="schem-title"
        x={13}
        y={38}
        style={{ fontFamily: 'var(--font-mono)' }}
      >
        {chip.label}
      </text>
      {!expanded && (
        <text className="schem-sub" x={13} y={53}>
          {`${chip.pins.length} cols`}
        </text>
      )}

      {/* Compact state badges keep DQ and contract state readable on collapsed cards. */}
      {dqColor && (
        <g className="schem-status-badge" transform={`translate(${statusX}, 10)`}>
          <title>{`DQ: ${chip.dqStatus}`}</title>
          <rect width={56} height={19} rx={9.5} fill={dqColor} />
          <circle cx={9} cy={9.5} r={3} fill={dqColor} />
          <text className="schem-status-text" x={17} y={13}>
            {statusLabel(chip.dqStatus)}
          </text>
        </g>
      )}
      {chip.hasContract && (
        <g className="schem-contract-badge" transform={`translate(${contractX}, 10)`}>
          <title>Contract bound</title>
          <rect width={22} height={19} rx={6} />
          <text x={11} y={13} textAnchor="middle">C</text>
        </g>
      )}

      {/* Spalten-Expander: eigene Affordance im Kopf, klar getrennt vom
          Nachbar-Expand-Handle. Nur sichtbar, wenn der Chip Spalten hat. */}
      {hasPins && (
        <g
          className={'schem-col-toggle' + (expanded ? ' is-open' : '')}
          role="button"
          aria-label={toggleLabel}
          onClick={toggleColumns}
          style={{ cursor: 'pointer' }}
        >
          <title>{toggleLabel}</title>
          <rect
            className="schem-col-toggle-hit"
            x={chip.width - 30}
            y={28}
            width={24}
            height={20}
            rx={5}
          />
          <path
            className="schem-col-toggle-icon"
            d="M -3.5 -2.5 L 0 1.5 L 3.5 -2.5"
            transform={`translate(${chip.width - 18}, 38)${expanded ? '' : ' rotate(-90)'}`}
          />
        </g>
      )}

      {expanded &&
        chip.pins.map(pin => {
          const key = columnId(chip.id, pin.id);
          const active =
            (!!tracePins && tracePins.has(key)) ||
            (!!selectedPin && selectedPin.node === chip.id && selectedPin.pin === pin.id);
          return (
            <g key={pin.id}>
              <rect
                className="schem-pin-rowbg"
                x={1}
                y={pin.rowY - 13}
                width={chip.width - 2}
                height={GEO.pinRowH}
                style={{ cursor: 'pointer' }}
                onClick={(event) => selectPin(event, pin.id)}
              >
                <title>{`${chip.label}.${pin.id}`}</title>
              </rect>
              <text
                className={'schem-pin-label' + (active ? ' is-active' : '')}
                x={22}
                y={pin.rowY + 3.5}
                style={{ fontFamily: 'var(--font-mono)', cursor: 'pointer' }}
                onClick={(event) => selectPin(event, pin.id)}
              >
                {pin.label}
              </text>
              {pin.dataType && (
                <text className="schem-pin-type" x={chip.width - 10} y={pin.rowY + 3.5} textAnchor="end">
                  {pin.dataType}
                </text>
              )}
              {pin.hasIncoming && (
                <circle
                  className={'schem-pin-dot' + (active ? ' is-active' : '')}
                  cx={0}
                  cy={pin.rowY}
                  r={3.4}
                  fill={active ? 'var(--cont)' : 'var(--fg-3)'}
                />
              )}
              {pin.hasOutgoing && (
                <circle
                  className={'schem-pin-dot' + (active ? ' is-active' : '')}
                  cx={chip.width}
                  cy={pin.rowY}
                  r={3.4}
                  fill={active ? 'var(--cont)' : 'var(--fg-3)'}
                />
              )}
            </g>
          );
        })}
    </g>
  );
}
