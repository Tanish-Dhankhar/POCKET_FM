import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import * as studio from '../api/studio'
import GenerationLoader from '../components/GenerationLoader'

const stepProgress = {blueprint:24,analysis:58,episodes:84}

export default function Refining() {
  const {id} = useParams(); const [params] = useSearchParams(); const jobId = params.get('job')
  const navigate = useNavigate(); const queryClient = useQueryClient()
  const job = useQuery({queryKey:['job',jobId],queryFn:() => studio.getJob(jobId),enabled:Boolean(jobId),refetchInterval:(query) => ['done','error'].includes(query.state.data?.state) ? false : 1000})
  useEffect(() => { if (job.data?.state === 'done') { queryClient.invalidateQueries({queryKey:['series',id]}); navigate(`/series/${id}`,{replace:true}) } },[job.data?.state,id,navigate,queryClient])
  if (!jobId) return <GenerationLoader mode="refine" error="The refinement job is missing." onBack={() => navigate(`/series/${id}`)}/>
  return <GenerationLoader mode="refine" message={job.data?.message || 'Preparing your refinement…'} progress={job.data?.state === 'done' ? 100 : stepProgress[job.data?.step] || 8} error={job.data?.state === 'error' ? job.data.error : job.error?.message} onBack={() => navigate(`/series/${id}`)}/>
}
