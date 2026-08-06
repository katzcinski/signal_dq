import type { CSSProperties, ReactNode } from 'react';
import { useId } from 'react';

interface Props {
  children: ReactNode;
  content?: ReactNode;
  className?: string;
  focusable?: boolean;
  maxWidth?: number;
}

export function Tooltip({ children, content, className, focusable = false, maxWidth = 260 }: Props) {
  const id = useId();

  if (!content) return <>{children}</>;

  return (
    <span
      className={className ? `tooltip-root ${className}` : 'tooltip-root'}
      aria-describedby={id}
      tabIndex={focusable ? 0 : undefined}
      style={{ '--tooltip-max': `${maxWidth}px` } as CSSProperties}
    >
      {children}
      <span id={id} role="tooltip" className="tooltip-bubble">
        {content}
      </span>
    </span>
  );
}
