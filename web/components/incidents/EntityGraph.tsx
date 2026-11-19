import type { GraphEdge, GraphNode } from "@/lib/incident/helpers";
import { layoutGraph } from "@/lib/incident/helpers";

export function EntityGraph({ nodes, edges }: { nodes: GraphNode[]; edges: GraphEdge[] }) {
  const laid = layoutGraph(nodes, edges);
  return (
    <div className="space-y-3">
      <svg viewBox="0 0 400 400" role="img" aria-label="Entities and relationships graph" className="h-80 w-full">
        {laid.edges.map((edge, index) => {
          const a = laid.nodes.find((node) => node.id === edge.a);
          const b = laid.nodes.find((node) => node.id === edge.b);
          if (!a || !b) return null;
          return (
            <line
              key={`${edge.a}-${edge.b}-${index}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={edge.strength === "strong" ? "#334155" : "#94a3b8"}
              strokeDasharray={edge.strength === "strong" ? undefined : "5 5"}
            />
          );
        })}
        {laid.nodes.map((node) => (
          <circle key={node.id} cx={node.x} cy={node.y} r={Math.min(24, 8 + (node.count ?? 1) * 3)} fill="#2563eb">
            <title>{`${node.kind}: ${node.value}`}</title>
          </circle>
        ))}
      </svg>
      <table className="w-full text-left text-sm">
        <caption>Entities and relationships</caption>
        <thead>
          <tr>
            <th scope="col">Entity</th>
            <th scope="col">Kind</th>
            <th scope="col">Events</th>
          </tr>
        </thead>
        <tbody>
          {laid.nodes.map((node) => (
            <tr key={node.id}>
              <td>{node.value}</td>
              <td>{node.kind}</td>
              <td>{node.count ?? 1}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="text-sm" aria-label="Relationships">
        {laid.edges.map((edge, index) => (
          <li key={index}>{edge.a} — {edge.b}: {edge.reason}</li>
        ))}
      </ul>
    </div>
  );
}
