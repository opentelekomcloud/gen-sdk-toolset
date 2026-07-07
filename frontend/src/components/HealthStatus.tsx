import { useQuery } from '@tanstack/react-query'
import type { components } from '../shared/api/schema.gen'

type HealthResponse = components['schemas']['HealthResponse']

export function HealthStatus() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['health'],
    queryFn: async (): Promise<HealthResponse> => {
      const res = await fetch('/health')
      if (!res.ok) throw new Error('Health check failed')
      return res.json()
    },
  })

  if (isLoading) return <p>Checking backend…</p>
  if (isError) return <p className="text-red-600">Backend unreachable</p>
  return <p>Backend status: <span className="font-medium text-brand">{data?.status}</span></p>
}