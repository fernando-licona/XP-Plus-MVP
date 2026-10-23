import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import ReproduceList from "./xpplus/ReproduceList";
import ReproduceDetail from "./xpplus/ReproduceDetail";
export default function App() {
  return <BrowserRouter><header className="border-b bg-white px-6 py-4"><Link to="/reproduce" className="font-bold text-indigo-700 text-xl">XP Plus · Public MVP</Link></header>
    <div className="border-b border-amber-200 bg-amber-50 px-6 py-3 text-sm text-amber-950" role="note">Computational demo: paper metadata → gap checks → digital twin → comparison → Standard. No hardware is operated. The toy example uses synthetic observations; its verdict is a software demonstration, not physical reproduction.</div>
    <main><Routes><Route path="/reproduce" element={<ReproduceList />} /><Route path="/reproduce/:experimentId" element={<ReproduceDetail />} /><Route path="*" element={<Navigate to="/reproduce" replace />} /></Routes></main></BrowserRouter>;
}
