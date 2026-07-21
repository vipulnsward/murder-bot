import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { Nav } from './components/Nav'
import { StatusStrip } from './components/StatusStrip'
import { Config } from './pages/Config'
import { Dashboard } from './pages/Dashboard'
import { Generals } from './pages/Generals'
import { Knowledge } from './pages/Knowledge'
import { Live } from './pages/Live'
import { Logs } from './pages/Logs'
import { Safety } from './pages/Safety'
import { Schedule } from './pages/Schedule'
import { Tasks } from './pages/Tasks'

function AppShell() {
  return (
    <>
      <Nav />
      <StatusStrip />
      <main className="ml-rail mt-strip min-h-[calc(100vh-48px)] p-4 md:p-6"><Outlet /></main>
    </>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route element={<Dashboard />} index />
        <Route element={<Live />} path="live" />
        <Route element={<Tasks />} path="tasks" />
        <Route element={<Config />} path="config" />
        <Route element={<Schedule />} path="schedule" />
        <Route element={<Generals />} path="generals" />
        <Route element={<Knowledge />} path="knowledge" />
        <Route element={<Logs />} path="logs" />
        <Route element={<Safety />} path="safety" />
        <Route element={<Navigate replace to="/" />} path="*" />
      </Route>
    </Routes>
  )
}
