import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import DashboardPage from './pages/DashboardPage'
import AnalyticsChatPage from './pages/AnalyticsChatPage'
import AgentWorkflowPage from './pages/AgentWorkflowPage'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/analytics" element={<AnalyticsChatPage />} />
          <Route path="/agent" element={<AgentWorkflowPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
