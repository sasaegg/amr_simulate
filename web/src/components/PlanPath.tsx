import { pathData } from '../geometry'

export function PlanPath({ plan }: { plan: [number, number][] }) {
  if (plan.length < 2) return null
  return <path className="plan" d={pathData(plan)} />
}
