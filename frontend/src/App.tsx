import React from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { AdhocComparePage } from './pages/AdhocComparePage';
import { ChangeDetailPage } from './pages/ChangeDetailPage';
import { ChangesPage } from './pages/ChangesPage';
import { ImportantRoutesPage } from './pages/ImportantRoutesPage';
import { RouteSummaryPage } from './pages/RouteSummaryPage';
import { SimulatorPage } from './pages/SimulatorPage';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<ChangesPage />} />
          <Route path="/changes/:id" element={<ChangeDetailPage />} />
          <Route path="/adhoc-compare" element={<AdhocComparePage />} />
          <Route path="/route-summary" element={<RouteSummaryPage />} />
          <Route path="/important-routes" element={<ImportantRoutesPage />} />
          <Route path="/simulator" element={<SimulatorPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
