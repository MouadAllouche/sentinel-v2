import { Skeleton } from "@/components/ui/primitives";

export default function Loading() {
  return (
    <div className="p-6">
      <Skeleton rows={5} />
    </div>
  );
}
