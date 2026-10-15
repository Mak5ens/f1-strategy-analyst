import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Info } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

/** Whether the API answers, and the version of the app behind it. */
export function ApiStatus({ info }: { info: Info | null }) {
  const t = getMessages().apiStatus;
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4">
        <CardTitle>{t.title}</CardTitle>
        {info ? (
          <Badge className="bg-success text-background">{t.up}</Badge>
        ) : (
          <Badge variant="destructive">{t.down}</Badge>
        )}
      </CardHeader>
      <CardContent className="text-muted-foreground text-sm">
        {info ? t.version(info.version) : t.unreachable}
      </CardContent>
    </Card>
  );
}
