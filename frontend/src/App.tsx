import { Navigate, Route, Routes } from 'react-router-dom'

import Layout from '@/components/Layout'
import Activity from '@/pages/Activity'
import Agents from '@/pages/Agents'
import Engineering from '@/pages/Engineering'
import Hackathons from '@/pages/Hackathons'
import Integrations from '@/pages/Integrations'
import Overview from '@/pages/Overview'
import Projects from '@/pages/Projects'
import Research from '@/pages/Research'
import Settings from '@/pages/Settings'
import Studio from '@/pages/Studio'
import Workspace from '@/pages/Workspace'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="workspace" element={<Workspace />} />
        <Route path="agents" element={<Agents />} />
        <Route path="hackathons" element={<Hackathons />} />
        <Route path="research" element={<Research />} />
        <Route path="studio" element={<Studio />} />
        <Route path="engineering" element={<Engineering />} />
        <Route path="projects" element={<Projects />} />
        <Route path="projects/:projectId" element={<Projects />} />
        <Route path="integrations" element={<Integrations />} />
        <Route path="activity" element={<Activity />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
