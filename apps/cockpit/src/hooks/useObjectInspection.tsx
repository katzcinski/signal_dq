import { useCallback, useMemo, useState, type MouseEvent, type ReactNode } from 'react';
import { ObjectPeek } from '@/components/ObjectPeek';
import { ObjectChecksPopover } from '@/components/ObjectChecksPopover';

/**
 * Zwei-Ebenen-Inspektion als wiederverwendbare Verdrahtung: `openChecks` öffnet
 * das kompakte Quick-Checks-Popover am Zeiger, `openPeek` das rechte Betriebs-
 * Panel. `overlays` rendert beide Ebenen — genau eine Instanz je Aufrufer, damit
 * nie zwei Panels übereinander liegen. So bekommt jede objektbezogene Fläche die
 * Interaktion mit ~3 Zeilen statt kopierter State-Logik.
 */
export interface ObjectInspection {
  /** Öffnet das Quick-Checks-Popover am Klickpunkt (stoppt die Zeilen-Propagation). */
  openChecks: (objectId: string, event: MouseEvent<HTMLElement>) => void;
  /** Öffnet das rechte Betriebs-Panel (ObjectPeek). */
  openPeek: (objectId: string) => void;
  /** Popover + Panel — einmal pro Aufrufer rendern. */
  overlays: ReactNode;
}

export function useObjectInspection(): ObjectInspection {
  const [peekId, setPeekId] = useState<string | null>(null);
  const [checksPopover, setChecksPopover] = useState<{
    objectId: string;
    anchor: { x: number; y: number };
  } | null>(null);

  const openChecks = useCallback((objectId: string, event: MouseEvent<HTMLElement>) => {
    event.stopPropagation();
    setChecksPopover({ objectId, anchor: { x: event.clientX, y: event.clientY } });
  }, []);

  const openPeek = useCallback((objectId: string) => {
    setChecksPopover(null);
    setPeekId(objectId);
  }, []);

  const overlays = useMemo(() => (
    <>
      {checksPopover && (
        <ObjectChecksPopover
          objectId={checksPopover.objectId}
          anchor={checksPopover.anchor}
          onClose={() => setChecksPopover(null)}
          onOpenOperations={() => {
            setPeekId(checksPopover.objectId);
            setChecksPopover(null);
          }}
        />
      )}
      {peekId && <ObjectPeek objectId={peekId} onClose={() => setPeekId(null)} />}
    </>
  ), [checksPopover, peekId]);

  return { openChecks, openPeek, overlays };
}
