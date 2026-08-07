import { LineChart, Line, ResponsiveContainer } from 'recharts';

interface Props { data: number[]; color?: string; width?: number; height?: number }

export function Spark({ data, color = 'var(--qual)', width = 60, height = 20 }: Props) {
  const points = data.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width={width} height={height}>
      <LineChart data={points}>
        <Line type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
