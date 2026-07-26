import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import * as studio from '../api/studio'
import AILoadingScreen from '../components/AILoadingScreen'

export default function Refining() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const jobId = params.get('job')
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => studio.getJob(jobId),
    enabled: Boolean(jobId),
    refetchInterval: (query) => ['done', 'error'].includes(query.state.data?.state) ? false : 1000,
  })

  useEffect(() => {
    if (job.data?.state === 'done') {
      queryClient.invalidateQueries({ queryKey: ['series', id] })
      navigate(`/series/${id}`, { replace: true })
    }
  }, [job.data?.state, id, navigate, queryClient])

  const error = !jobId
    ? 'The refinement job is missing.'
    : job.data?.state === 'error'
      ? (job.data.error || job.error?.message)
      : null

  return (
    <div className="fixed inset-0 z-[150]">
      <AILoadingScreen />
      {error && (
        <div className="absolute bottom-8 left-1/2 flex -translate-x-1/2 flex-col items-center gap-3">
          <p className="error text-sm">{error}</p>
          <button className="button ghost" onClick={() => navigate(`/series/${id}`)}>Back</button>
        </div>
      )}
    </div>
  )
}
