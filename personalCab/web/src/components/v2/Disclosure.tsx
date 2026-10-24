import { useId, useState, type ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
export function Disclosure({
  title,
  description,
  icon,
  children,
  initialOpen = false,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  children: ReactNode;
  initialOpen?: boolean;
}) {
  const [open, setOpen] = useState(initialOpen);
  const id = useId();
  return (
    <section className={`disclosure ${open ? 'is-open' : ''}`}>
      <button
        type="button"
        className="disclosure-trigger"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        {icon && <span className="document-icon">{icon}</span>}
        <span className="disclosure-label">
          <strong>{title}</strong>
          {description && <span className="small muted">{description}</span>}
        </span>
        <ChevronDown aria-hidden size={19} />
      </button>
      <div id={id} hidden={!open} className="disclosure-content">
        {children}
      </div>
    </section>
  );
}
