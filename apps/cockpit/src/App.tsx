import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { Shell } from './components/layout/Shell';

const Cockpit           = lazy(() => import('./pages/Cockpit'));
const MyWork            = lazy(() => import('./pages/MyWork'));
const ObjectCatalog     = lazy(() => import('./pages/ObjectCatalog'));
const ObjectDetail      = lazy(() => import('./pages/ObjectDetail'));
const Products          = lazy(() => import('./pages/Products'));
const ProductDetail     = lazy(() => import('./pages/ProductDetail'));
const ContractWorkbench = lazy(() => import('./pages/ContractWorkbench'));
const Lineage           = lazy(() => import('./pages/LineagePage'));
const SchemaDrift       = lazy(() => import('./pages/SchemaDrift'));
const Incidents         = lazy(() => import('./pages/Incidents'));
const Quarantine        = lazy(() => import('./pages/Quarantine'));
const Healing           = lazy(() => import('./pages/Healing'));
const Enforcement       = lazy(() => import('./pages/Enforcement'));
const Proposals         = lazy(() => import('./pages/Proposals'));
const RunDetail         = lazy(() => import('./pages/RunDetail'));
const RunCompare        = lazy(() => import('./pages/RunCompare'));
const Schedules         = lazy(() => import('./pages/Schedules'));
const Compliance        = lazy(() => import('./pages/Compliance'));
const CheckLibrary      = lazy(() => import('./pages/CheckLibrary'));
const Notifications     = lazy(() => import('./pages/Notifications'));
const Settings          = lazy(() => import('./pages/Settings'));
const Environments      = lazy(() => import('./pages/Environments'));
const InventoryAdmin    = lazy(() => import('./pages/InventoryAdmin'));
const NotFound          = lazy(() => import('./pages/NotFound'));

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

function LoadingFallback() {
  return <div style={{ color: 'var(--fg-3)', padding: 40, textAlign: 'center' }}>Loading…</div>;
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Shell>
          <Suspense fallback={<LoadingFallback />}>
            <Routes>
              <Route path="/"            element={<Cockpit />} />
              <Route path="/my"          element={<MyWork />} />
              <Route path="/objects"     element={<ObjectCatalog />} />
              <Route path="/objects/:id" element={<ObjectDetail />} />
              <Route path="/products"    element={<Products />} />
              <Route path="/products/:name" element={<ProductDetail />} />
              <Route path="/contracts"   element={<ContractWorkbench />} />
              <Route path="/lineage"     element={<Lineage />} />
              {/* Route alias (WS4): /coverage rendert dieselbe Lineage-Ansicht */}
              <Route path="/coverage"    element={<Lineage />} />
              <Route path="/schema-drift" element={<SchemaDrift />} />
              <Route path="/schedules"   element={<Schedules />} />
              <Route path="/incidents"   element={<Incidents />} />
              <Route path="/quarantine"  element={<Quarantine />} />
              <Route path="/healing"     element={<Healing />} />
              <Route path="/enforcement" element={<Enforcement />} />
              <Route path="/proposals"   element={<Proposals />} />
              <Route path="/runs/compare" element={<RunCompare />} />
              <Route path="/runs/:id"    element={<RunDetail />} />
              <Route path="/compliance"  element={<Compliance />} />
              <Route path="/governance"  element={<Navigate to="/compliance" replace />} />
              <Route path="/library"    element={<CheckLibrary />} />
              <Route path="/notifications" element={<Notifications />} />
              <Route path="/settings"    element={<Settings />} />
              <Route path="/environments" element={<Environments />} />
              <Route path="/inventory-admin" element={<InventoryAdmin />} />
              {/* Catch-all: vertippte / veraltete Deep-Links landen nicht im Leeren */}
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </Shell>
      </BrowserRouter>
      <Toaster
        theme="dark"
        position="bottom-right"
        toastOptions={{
          style: { background: 'var(--bg-2)', border: '1px solid var(--line-2)', color: 'var(--fg)' },
        }}
      />
    </QueryClientProvider>
  );
}
