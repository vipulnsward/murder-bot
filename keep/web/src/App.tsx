import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { Nav } from './components/Nav'
import { StatusStrip } from './components/StatusStrip'
import { Config } from './pages/Config'
import { Dashboard } from './pages/Dashboard'
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
        <Route element={<Tasks />} path="tasks" />
        <Route element={<Config />} path="config" />
        <Route element={<Navigate replace to="/" />} path="*" />
      </Route>
    </Routes>
  )
}
