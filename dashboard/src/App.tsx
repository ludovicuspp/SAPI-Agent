import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AdminRoute } from "@/components/AdminRoute";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import SummaryPage from "@/pages/Summary";
import Boletines from "@/pages/Boletines";
import BoletinDetail from "@/pages/BoletinDetail";
import Detections from "@/pages/Detections";
import WatchlistPage from "@/pages/Watchlist";
import PortfolioPage from "@/pages/Portfolio";
import UsersPage from "@/pages/Users";
import MonitoringPage from "@/pages/Monitoring";
import NotFound from "@/pages/NotFound";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<SummaryPage />} />
          <Route path="boletines" element={<Boletines />} />
          <Route path="boletines/:id" element={<BoletinDetail />} />
          <Route path="detections" element={<Detections />} />
          <Route path="watchlist" element={<WatchlistPage />} />
          <Route path="portfolio" element={<PortfolioPage />} />
          <Route
            path="users"
            element={
              <AdminRoute>
                <UsersPage />
              </AdminRoute>
            }
          />
          <Route
            path="monitoring"
            element={
              <AdminRoute>
                <MonitoringPage />
              </AdminRoute>
            }
          />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
