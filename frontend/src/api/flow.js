import * as pipeline from './series'

function requireStage(response, expected) {
  if (response?.stage !== expected) {
    throw new Error(`Expected pipeline stage “${expected}”, received “${response?.stage || 'unknown'}”.`)
  }
  return response
}

export async function startSeries({ idea, transcript = null }) {
  const extracted = requireStage(await pipeline.createSeries({ idea, transcript }), 'extract')
  const clarified = requireStage(await pipeline.approve(extracted.series_id), 'clarify')
  return { seriesId: extracted.series_id, questions: clarified.payload?.questions || [] }
}

export async function submitAnswers(seriesId, answers) {
  return requireStage(await pipeline.submit(seriesId, { clarification_answers: answers }), 'blueprint')
}

export async function buildSeries(seriesId, config) {
  requireStage(await pipeline.approve(seriesId, {
    include_narrator: config.include_narrator,
    genre: config.genre,
    setting: config.setting,
  }), 'ep_config')
  // Stop on the episode_plan review. Approving it would trigger the old
  // all-episodes script node, while the product generates episodes on demand.
  return requireStage(await pipeline.submit(seriesId, {
    ep_count: Number(config.ep_count),
    ep_minutes: Number(config.ep_minutes),
    include_narrator: Boolean(config.include_narrator),
  }), 'episode_plan')
}
