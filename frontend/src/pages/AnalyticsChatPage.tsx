import ChatPanel from '../components/ChatPanel'
import TrendBackdrop from '../components/TrendBackdrop'

function AnalyticsChatPage() {
  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="header-top-row">
          <h1>Analytics Chat</h1>
        </div>
        <p className="subtitle">Ask business questions about demand, inventory, and supply in plain language</p>
        <TrendBackdrop />
      </header>

      <ChatPanel />
    </div>
  )
}

export default AnalyticsChatPage
