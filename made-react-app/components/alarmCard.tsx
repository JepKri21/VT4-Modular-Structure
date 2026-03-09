import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TriangleAlert } from "lucide-react";

interface AlarmCardProps {
  title: string;
  count: number;
  color: string;
}

export default function AlarmCard({ title, count, color }: AlarmCardProps) {
  return (
    <Card className="relative cursor-pointer flex flex-col bg-muted p-2 mt-10 justify-between w-full">
      <CardHeader>
        <CardTitle className="flex justify-start items-center text-sm uppercase font-medium text-primary gap-2">
          <TriangleAlert className="text-primary mb-1" size={24} />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent
        className={`flex text-3xl justify-center items-center font-bold mb-2 ${color}`}
      >
        <div>{count}</div>
      </CardContent>
    </Card>
  );
}
