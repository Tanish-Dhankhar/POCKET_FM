import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer } from 'recharts'

const axes = [['Action','action'],['Drama','drama'],['Comedy','comedy'],['Sci-fi','sci_fi'],['Horror','horror'],['Thriller','thriller'],['Romance','romance']]

export default function GenreRadar({distribution={}}) {
  const data = axes.map(([category,key]) => ({category,value:Number(distribution[key] || distribution[category] || 0)}))
  return <div className="genre-radar" aria-label={data.map((item) => `${item.category} ${item.value}%`).join(', ')}><ResponsiveContainer width="100%" height="100%"><RadarChart data={data} cx="50%" cy="52%" outerRadius="67%"><PolarGrid stroke="#333" gridType="polygon"/><PolarAngleAxis dataKey="category" tick={{fill:'#dedede',fontSize:11}} tickLine={false}/><PolarRadiusAxis domain={[0,100]} tick={false} axisLine={false}/><Radar dataKey="value" stroke="#ff2d55" fill="#e61c38" fillOpacity={.13} strokeWidth={2.5} dot={{r:3,fill:'#fff',stroke:'#e61c38',strokeWidth:2}} isAnimationActive/></RadarChart></ResponsiveContainer></div>
}
