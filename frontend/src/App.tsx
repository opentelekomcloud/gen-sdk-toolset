import './App.css'
import { HealthStatus } from './components/HealthStatus'

const NAV = [
  { label: "Scan", enabled: true },
  { label: "Generation", enabled: false },
  { label: "Maintenance", enabled: false },
]

function App() {
  return (
    <div className="min-h-screen">
      <header className="bg-brand text-white px-6 py-4">
        <h1 className="text-lg font-medium">gen-sdk-tooling</h1>
      </header>
      <nav className="flex gap-1 border-b px-6">
        {NAV.map((item) => (
          <button
            key={item.label}
            disabled={!item.enabled}
            className={
              item.enabled
                ? "px-4 py-3 border-b-2 border-brand text-brand font-medium"
                : "px-4 py-3 text-gray-400 cursor-not-allowed"
            }
          >
            {item.label}
          </button>
        ))}
      </nav>
      <main className="p-6">
        <HealthStatus />
      </main>
    </div>
  )
}

export default App
