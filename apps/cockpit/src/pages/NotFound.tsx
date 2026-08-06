import { useLocation } from 'react-router-dom';
import { NotFoundState } from '@/components/ui/NotFoundState';
import { t } from '@/i18n/de';

// Catch-all (`<Route path="*">`): fängt vertippte, veraltete oder halb-leere
// Deep-Links (z. B. /runs/ ohne ID) ab, die sonst einen leeren Inhaltsbereich in
// der Shell rendern würden. Zeigt die aufgerufene Adresse und einen Weg zurück.
export default function NotFound() {
  const { pathname } = useLocation();
  return (
    <div className="page-full">
      <NotFoundState
        title={t.notFound.title}
        message={`${t.notFound.message} (${pathname})`}
        actions={[
          { label: t.notFound.home, to: '/', primary: true },
          { label: t.notFound.objects, to: '/objects' },
        ]}
      />
    </div>
  );
}
